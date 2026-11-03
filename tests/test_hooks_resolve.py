"""Every hook command in the repo's Claude Code settings and in the kit's settings resolves to a real script, and every
hook wrapper fails closed (exit 2) when its Python module cannot import."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kb_distillery.config.resources import require_repo_root

REPO = require_repo_root("tests/test_hooks_resolve.py")
HOOKS_PY = REPO / "scripts" / "hooks-python.sh"
# kit settings name `$CLAUDE_PROJECT_DIR/.claude/hooks/<x>.sh`, installed from this folder
KIT_HOOKS = REPO / "src" / "kb_distillery" / "kits" / "base" / "hooks"
OWNER_SETTINGS = REPO / ".claude" / "settings.json"
SETTINGS = [pytest.param(OWNER_SETTINGS, REPO, id="repo", marks=pytest.mark.skipif(
                not OWNER_SETTINGS.is_file(), reason="owner tooling: .claude/ is export-ignored, so the public checkout has none")),
            pytest.param(KIT_HOOKS / "claude-settings.json", KIT_HOOKS, id="kit")]


def _commands(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for groups in data.get("hooks", {}).values():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") == "command":
                    yield hook["command"]


def _script_of(command: str, base: Path) -> Path:
    m = re.search(r'\$CLAUDE_PROJECT_DIR/(\S+?)"?(?:\s|$)', command)
    assert m, f"no script path in hook command: {command}"
    rel = m.group(1).rstrip('"')
    rel = rel[len(".claude/hooks/"):] if rel.startswith(".claude/hooks/") and base == KIT_HOOKS else rel
    return base / rel


@pytest.mark.parametrize("settings,base", SETTINGS)
def test_every_hook_command_resolves(settings, base):
    commands = list(_commands(settings))
    assert commands, f"{settings} has no hook commands"
    for command in commands:
        script = _script_of(command, base)
        assert script.is_file(), f"{settings.name}: {command} -> {script} does not exist"
        if script.name == "hooks-python.sh":
            module = command.split("hooks-python.sh", 1)[1].split('"')[-1].split()[0]
            cp = subprocess.run([sys.executable, "-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)", module])
            assert cp.returncode == 0, f"{command}: module {module} does not import"


def test_the_wrappers_name_no_pythonpath_and_go_through_hooks_python():
    for rel in ("scripts/hooks/block-git-write.sh", "scripts/githooks/commit-msg", "scripts/githooks/pre-push",
                "scripts/githooks/pre-commit"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "hooks-python.sh" in text, rel
        assert "PYTHONPATH" not in text, rel


def _run(root: Path, *args, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(extra_env or {})
    return subprocess.run(["bash", str(root / "scripts" / "hooks-python.sh"), *args], capture_output=True, text=True, env=env)


def _tmp_root(tmp_path: Path, with_module: bool, module_body="print('hook ran')\n") -> Path:
    (tmp_path / "scripts").mkdir()
    shutil.copy(HOOKS_PY, tmp_path / "scripts" / "hooks-python.sh")
    if with_module:
        pkg = tmp_path / "src" / "kb_distillery"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "run.py").write_text(module_body)
    return tmp_path


def test_import_failure_exits_2_and_says_it_failed_closed(tmp_path):
    root = _tmp_root(tmp_path, with_module=False)
    cp = _run(root, "kb_distillery.run")
    assert cp.returncode == 2 and "fail closed" in cp.stderr


def test_a_module_in_the_checkout_runs_with_no_pythonpath_set(tmp_path):
    """No env PYTHONPATH: the wrapper puts <checkout>/src on the path itself."""
    root = _tmp_root(tmp_path, with_module=True)
    cp = _run(root, "kb_distillery.run")
    assert cp.returncode == 0 and cp.stdout.strip() == "hook ran", cp.stderr


def test_the_checkouts_code_wins_over_an_installed_copy(tmp_path):
    """An editable/installed kb_distillery elsewhere (here a user-site .pth) must not shadow the checkout's own src/:
    a worktree's hooks enforce the worktree's rules."""
    (tmp_path / "co").mkdir()
    root = _tmp_root(tmp_path / "co", with_module=True, module_body="print('checkout')\n")
    inst = tmp_path / "inst" / "kb_distillery"
    inst.mkdir(parents=True)
    (inst / "__init__.py").write_text("")
    (inst / "run.py").write_text("print('installed')\n")
    base = tmp_path / "ubase"
    site = subprocess.run(["python3", "-c", "import site; print(site.getusersitepackages())"], capture_output=True, text=True,
                          env={**os.environ, "PYTHONUSERBASE": str(base)}).stdout.strip()
    Path(site).mkdir(parents=True)
    (Path(site) / "inst.pth").write_text(str(tmp_path / "inst") + "\n")
    cp = _run(root, "kb_distillery.run", extra_env={"PYTHONUSERBASE": str(base)})
    assert cp.returncode == 0 and cp.stdout.strip() == "checkout", cp.stdout + cp.stderr


def test_the_modules_exit_code_comes_through(tmp_path):
    root = _tmp_root(tmp_path, with_module=True, module_body="import sys; sys.exit(2)\n")
    assert _run(root, "kb_distillery.run").returncode == 2


def test_a_real_module_runs_through_the_wrapper():
    cp = _run(REPO, "kb_distillery.config.resources")
    assert cp.returncode == 0, cp.stderr


def test_every_kit_hook_calls_a_distill_hook_that_exists_and_imports():
    """The kit hooks (git and Claude Code) are `distill hook <name>`; each name is a command whose module imports, and the
    hook file is executable (git and the installer rely on it)."""
    import importlib.util
    from kb_distillery.cli import tree

    seen = set()
    for hook in sorted(p for p in KIT_HOOKS.iterdir() if p.name != "claude-settings.json"):
        assert os.access(hook, os.X_OK), f"{hook.name} is not executable"
        names = re.findall(r"distill hook ([\w-]+)", hook.read_text(encoding="utf-8"))
        assert names, f"{hook.name} does not call `distill hook <name>`"
        for name in names:
            cmd = tree.COMMANDS["hook"].sub[name]
            assert cmd.fail_closed, name
            assert importlib.util.find_spec(cmd.target), f"{hook.name}: {cmd.target} does not import"
            seen.add(name)
    assert seen == set(tree.COMMANDS["hook"].sub), "every `distill hook <name>` is called by some kit hook"

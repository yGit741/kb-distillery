"""Build the wheel, install it into an empty venv away from the checkout, and run the installed commands.

Slow (builds a wheel, resolves and installs every dependency from the network), so it only runs when asked:
`pixi run test-wheel` (KB_TEST_WHEEL=1); CI job `wheel` runs exactly that. The default suite and its
`test_fast_and_offline` 60 s limit never include it.

What it proves: `distill doctor`, `distill init` and `distill init --refresh` work with no repository anywhere
(skills, docs, hooks, settings and AGENTS.md come out of the wheel's kits and the installed git hooks run),
`import kb_distillery` resolves inside the venv (not the checkout), the packaged templates are found, and the
root-level folders reach `_data/`."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from kb_distillery.config.resources import require_repo_root

pytestmark = [pytest.mark.wheel,
              pytest.mark.skipif(os.environ.get("KB_TEST_WHEEL") != "1", reason="slow: run `pixi run test-wheel` (CI job `wheel`)")]

REPO = require_repo_root("tests/cli/test_install_wheel.py")


def _uv() -> str:
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is not installed (needed to build and install quickly)")
    return uv


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    cp = subprocess.run([_uv(), "build", "--wheel", "--out-dir", str(out), str(REPO)], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr[-2000:]
    wheels = list(out.glob("kb_distillery-*.whl"))
    assert len(wheels) == 1, list(out.iterdir())
    return wheels[0]


@pytest.fixture(scope="module")
def venv(tmp_path_factory, wheel) -> Path:
    env_dir = tmp_path_factory.mktemp("venv") / "v"
    uv = _uv()
    subprocess.run([uv, "venv", "-q", str(env_dir), "--python", sys.executable], check=True, capture_output=True)
    cp = subprocess.run([uv, "pip", "install", "-q", "--python", str(env_dir / "bin" / "python"), str(wheel)],
                        capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr[-2000:]
    return env_dir


@pytest.fixture
def clean_env(tmp_path):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "KB", "KB_ROOT", "KB_BASES_DIR", "PIXI_PROJECT_ROOT", "VIRTUAL_ENV", "CONDA_PREFIX")}
    home = tmp_path / "knowledge"
    env.update(KB_DISTILLERY_HOME=str(home), HOME=str(tmp_path), KB_APP_CONFIG=os.path.join(os.sep, "nonexistent", "app.toml"),
               KB_SHARE_AUTODEPLOY="0")
    return env, home


def _run(venv: Path, args, env, cwd):
    return subprocess.run([str(venv / "bin" / args[0]), *args[1:]], capture_output=True, text=True, env=env, cwd=cwd)


def test_the_wheel_carries_the_root_level_folders_under_data(wheel):
    names = zipfile.ZipFile(wheel).namelist()
    for want in ("kb_distillery/publish/cloudflare/worker/auth.js", "kb_distillery/publish/cloudflare/worker/wrangler.template.jsonc",
                 "kb_distillery/publish/cloudflare/share.toml",):
        assert any(n.startswith(want) for n in names), want
    assert not any(n.startswith("kb/") or "backend" in n.split("/")[0] for n in names)


def test_the_wheel_carries_the_kits_as_package_data(wheel):
    names = zipfile.ZipFile(wheel).namelist()
    for want in ("kb_distillery/kits/base/AGENTS.template.md", "kb_distillery/kits/base/README.template.md",
                 "kb_distillery/kits/research/AGENTS.template.md", "kb_distillery/kits/base/kit.toml", "kb_distillery/kits/research/kit.toml",
                 "kb_distillery/kits/base/defaults/flags.toml", "kb_distillery/kits/base/defaults/docs/",
                 "kb_distillery/kits/base/defaults/templates/", "kb_distillery/kits/base/defaults/digest/",
                 "kb_distillery/kits/base/skills/query-knowledge/SKILL.md", "kb_distillery/kits/base/skills/README.md",
                 "kb_distillery/kits/research/skills/build-researcher-profile/SKILL.md"):
        assert any(n.startswith(want) for n in names), want
    packed = {n.split("/")[2] for n in names if n.startswith("kb_distillery/_data/") and n.count("/") > 2}
    assert not packed, packed                               # nothing is force-included into _data any more (the Worker is package data)


def test_the_wheel_carries_the_kit_hooks_executable(wheel):
    zf = zipfile.ZipFile(wheel)
    hooks = {n: zf.getinfo(n) for n in zf.namelist() if n.startswith("kb_distillery/kits/base/hooks/")}
    names = {n.rsplit("/", 1)[1] for n in hooks}
    assert {"pre-commit", "commit-msg", "pre-push", "kb-guard.sh", "kb-git-guard.sh", "claude-settings.json"} <= names, names
    for n, info in hooks.items():
        if not n.endswith(".json"):
            assert (info.external_attr >> 16) & 0o111, f"{n} lost its executable bit in the wheel"
    assert not any("kb-hooks" in n or n.endswith("/env.sh") for n in zf.namelist())


def test_the_installed_package_is_the_one_in_the_venv_and_has_no_checkout(venv, clean_env, tmp_path):
    env, _ = clean_env
    code = ("import kb_distillery, sys; from kb_distillery.config import resources as r; "
            "print(kb_distillery.__file__); print(r.repo_root()); print(r.resource('kits/base/kit.toml').is_file())")
    cp = subprocess.run([str(venv / "bin" / "python"), "-c", code], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert cp.returncode == 0, cp.stderr
    where, repo, templates = cp.stdout.split("\n")[:3]
    assert Path(where).is_relative_to(venv) and repo == "None" and templates == "True"


def test_distill_help_and_doctor_run_in_a_clean_venv(venv, clean_env, tmp_path):
    env, _ = clean_env
    assert _run(venv, ["distill", "--help"], env, tmp_path).returncode == 0
    doctor = _run(venv, ["distill", "doctor"], env, tmp_path)
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "python" in doctor.stdout


def test_distill_init_creates_a_kb_under_the_home_folder_and_finds_it_from_inside(venv, clean_env, tmp_path):
    env, home = clean_env
    cp = _run(venv, ["distill", "init", "--kb-id", "wheel-kb", "--yes"], env, tmp_path)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert (home / "wheel-kb" / "kb.toml").is_file() and (home / "wheel-kb" / ".git").exists()
    assert 'kit = "base"' in (home / "wheel-kb" / "kb.toml").read_text()          # the kit resolved from the wheel's package data
    listed = _run(venv, ["distill", "kb", "list"], env, tmp_path)
    assert listed.returncode == 0 and "wheel-kb" in listed.stdout, listed.stdout + listed.stderr
    inside = _run(venv, ["distill", "kb", "show"], env, home / "wheel-kb")           # no KB, no --kb: found from the folder
    assert inside.returncode == 0 and "wheel-kb" in inside.stdout, inside.stdout + inside.stderr


def test_distill_init_writes_the_kits_files_from_the_wheel_and_refresh_resyncs_them(venv, clean_env, tmp_path):
    env, home = clean_env
    cp = _run(venv, ["distill", "init", "--kb-id", "full-kb", "--kit", "research", "--name", "Full KB", "--yes"], env, tmp_path)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    kb = home / "full-kb"
    for rel in (".claude/skills/query-knowledge/SKILL.md", ".claude/skills/build-researcher-profile/SKILL.md",   # parent + child
                ".claude/skills/ingest-to-catalog/mail/SKILL.md", ".claude/skills/README.md", ".claude/docs/page-model.md",
                ".claude/hooks/kb-guard.sh", ".claude/hooks/kb-git-guard.sh", ".claude/settings.json", "AGENTS.md", "README.md"):
        assert (kb / rel).is_file(), rel
    agents = (kb / "AGENTS.md").read_text()
    assert "# Full KB" in agents and "Research kit additions" in agents and "{{" not in agents
    settings = (kb / ".claude/settings.json").read_text()
    assert "kb-guard.sh" in settings and "src/kb_distillery" not in settings and "pixi" not in settings
    assert os.access(kb / ".claude/hooks/kb-guard.sh", os.X_OK)
    git = lambda *a: subprocess.run(["git", "-C", str(kb), *a], capture_output=True, text=True, env=env)       # noqa: E731
    assert git("status", "--porcelain").stdout == ""                                      # all of it in the first commit
    hooks_path = git("config", "core.hooksPath").stdout.strip()
    assert Path(hooks_path).is_absolute() and Path(hooks_path).is_relative_to(venv)       # the installed kit, not a checkout
    assert os.access(Path(hooks_path) / "pre-commit", os.X_OK), "the wheel lost the git hooks' executable bit"
    # the installed git hooks are live: with `distill` on PATH a commit that breaks the policy is refused by the commit-msg hook
    live = dict(env, PATH=f"{venv / 'bin'}{os.pathsep}{env['PATH']}", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x",
                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
    refused = subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-q", "-m", "not a kb commit"],
                             capture_output=True, text=True, env=live)
    assert refused.returncode != 0 and "not found" not in refused.stderr, refused.stdout + refused.stderr
    # refresh: nothing to do on a fresh kb, then drift is repaired and reported, knowledge and AGENTS.md untouched
    again = _run(venv, ["distill", "init", "--refresh", "--kb", str(kb)], env, tmp_path)
    assert again.returncode == 0 and "already up to date" in again.stdout, again.stdout + again.stderr
    (kb / ".claude/skills/query-knowledge/SKILL.md").write_text("drifted\n")
    (kb / ".claude/settings.json").write_text("{}\n")
    (kb / "AGENTS.md").write_text(agents + "\nMine.\n")
    (kb / "wiki" / "keep.md").write_text("keep\n")
    fixed = _run(venv, ["distill", "init", "--refresh", "--kb", str(kb)], env, tmp_path)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert "updated .claude/skills/query-knowledge/SKILL.md" in fixed.stdout and "updated .claude/settings.json" in fixed.stdout
    assert "AGENTS.md: yours" in fixed.stdout and (kb / "AGENTS.md").read_text().endswith("Mine.\n")
    assert (kb / "wiki" / "keep.md").read_text() == "keep\n" and (kb / ".claude/skills/query-knowledge/SKILL.md").read_text() != "drifted\n"
    again = _run(venv, ["distill", "init", "--refresh", "--kb", str(kb)], env, tmp_path)
    assert "already up to date" in again.stdout, again.stdout
    inside = _run(venv, ["distill", "init", "--refresh"], env, kb)                         # no --kb: found from inside the folder
    assert inside.returncode == 0 and "already up to date" in inside.stdout, inside.stdout + inside.stderr

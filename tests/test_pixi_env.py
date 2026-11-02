"""The shared pixi env holds no path into any checkout.

Every worktree symlinks the primary's `.pixi`. `kb-distillery = { path = ".", editable = true }` in pixi.toml made a
`pixi run` in a worktree that did not skip the install re-point the shared editable install (the `.pth` file and the
`distill`/`kbd` scripts) at the worktree; removing the worktree then broke the env. `[activation.env] PYTHONPATH`
resolves imports per checkout instead, so the package must stay out of the env. These tests fail if it comes back, if a
runtime dependency of pyproject.toml is no longer declared directly, or if the `distill` / `kbd` tasks go.
"""
import os
import re
import subprocess
import sys
import tomllib

from kb_distillery.config.resources import require_repo_root

REPO = require_repo_root("tests/test_pixi_env.py")
PKG = {"kb-distillery", "kb_distillery", "kb.distillery"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", re.split(r"[\[<>=!~; ]", name.strip(), maxsplit=1)[0]).lower()


def _pixi() -> dict:
    return tomllib.loads((REPO / "pixi.toml").read_text(encoding="utf-8"))


def _dependency_tables(manifest: dict):
    """Every table of dependencies in the manifest: root, per-feature, per-target, per-environment."""
    keys = ("dependencies", "pypi-dependencies", "host-dependencies", "build-dependencies")

    def walk(node):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if k in keys and isinstance(v, dict):
                yield k, v
            else:
                yield from walk(v)

    yield from walk(manifest)


def test_pixi_toml_has_no_path_or_editable_dependency_on_this_package():
    manifest = _pixi()
    tables = list(_dependency_tables(manifest))
    assert tables, "no dependency tables found: the walker is broken"
    for kind, table in tables:
        for name, spec in table.items():
            assert _norm(name) not in {_norm(p) for p in PKG}, (
                f"pixi.toml [{kind}] names {name!r}: the shared env must hold no install of this package (see tests/test_pixi_env.py)")
            if isinstance(spec, dict):
                assert "path" not in spec and not spec.get("editable"), (
                    f"pixi.toml [{kind}] {name!r} is a path/editable dependency {spec}: in a worktree it re-points the shared env")


def test_the_lock_has_no_path_package_either():
    lock = (REPO / "pixi.lock").read_text(encoding="utf-8")
    assert not re.search(r"^\s*- pypi: \./?\s*$", lock, re.M), "pixi.lock installs a package from a local path"
    assert not re.search(r"^  name: kb-distillery$", lock, re.M), "pixi.lock still holds kb-distillery"


def test_imports_resolve_per_checkout_through_pythonpath():
    env = _pixi()["activation"]["env"]
    assert env["PYTHONPATH"] == "$PIXI_PROJECT_ROOT/src"


def test_every_runtime_dependency_of_pyproject_is_declared_in_pixi_toml():
    """The editable install used to supply them transitively; without it each must be declared directly."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wanted = {_norm(d) for d in project["dependencies"]}
    wanted |= {_norm(d) for d in project["optional-dependencies"]["ingest-heavy"]}
    wanted |= {_norm(d) for d in project["optional-dependencies"]["dev"] if _norm(d) in {"pytest", "pytest-xdist"}}
    declared = set()
    manifest = _pixi()
    for _, table in _dependency_tables(manifest):
        declared |= {_norm(n) for n in table}
    missing = sorted(wanted - declared)
    assert not missing, f"declare these in pixi.toml (the env no longer gets them from the package): {missing}"


def test_distill_and_kbd_are_pixi_tasks_that_call_the_cli_package():
    tasks = _pixi()["tasks"]
    assert tasks["distill"] == "python -m kb_distillery.cli"
    assert tasks["kbd"] == "python -m kb_distillery.cli.legacy"


def test_python_dash_m_kb_distillery_is_distill():
    cp = subprocess.run([sys.executable, "-m", "kb_distillery", "--help"], capture_output=True, text=True, cwd=REPO,
                        env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.startswith("usage: distill <command>")

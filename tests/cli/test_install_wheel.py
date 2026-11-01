"""Build the wheel, install it into an empty venv away from the checkout, and run the installed commands.

Slow (builds a wheel, resolves and installs every dependency from the network), so it only runs when asked:
`pixi run test-wheel` (KB_TEST_WHEEL=1); CI job `wheel` runs exactly that. The default suite and its
`test_fast_and_offline` 60 s limit never include it.

What it proves: `distill doctor` and `distill init` work with no repository anywhere, `import kb_distillery` resolves
inside the venv (not the checkout), the packaged templates are found, and the root-level folders reach `_data/`."""
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
    for want in ("kb_distillery/_data/share/auth.js",):
        assert any(n.startswith(want) for n in names), want
    assert not any(n.startswith("kb/") or "backend" in n.split("/")[0] for n in names)


def test_the_wheel_carries_the_kits_as_package_data(wheel):
    names = zipfile.ZipFile(wheel).namelist()
    for want in ("kb_distillery/kits/base/kit.toml", "kb_distillery/kits/research/kit.toml",
                 "kb_distillery/kits/base/defaults/flags.toml", "kb_distillery/kits/base/defaults/docs/",
                 "kb_distillery/kits/base/defaults/templates/", "kb_distillery/kits/base/defaults/digest/",
                 "kb_distillery/kits/base/skills/query-knowledge/SKILL.md", "kb_distillery/kits/base/skills/README.md",
                 "kb_distillery/kits/research/skills/build-researcher-profile/SKILL.md"):
        assert any(n.startswith(want) for n in names), want
    packed = {n.split("/")[2] for n in names if n.startswith("kb_distillery/_data/") and n.count("/") > 2}
    assert packed <= {"share"}, packed                      # only the folder Lane F still moves


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

"""install.sh: syntax and the dry-run command sequence, with fake pixi/curl/uname so nothing is installed."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.sh"


def _fake(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def _run(tmp_path: Path, *args: str, pixi: bool, uname: str = "Linux") -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _fake(bin_dir, "uname", f'echo {uname}')
    _fake(bin_dir, "curl", "echo 'curl must not run in a dry run' >&2; exit 99")
    if pixi:
        _fake(bin_dir, "pixi", "echo 'pixi must not run in a dry run' >&2; exit 99")
    # System tools only (bash, grep, sed, basename, dirname); the fakes come first. The real pixi is hidden.
    sys_bin = tmp_path / "sysbin"
    sys_bin.mkdir(exist_ok=True)
    for tool in ("bash", "grep", "sed", "basename", "dirname", "cat", "env"):
        real = shutil.which(tool)
        if real and not (sys_bin / tool).exists():
            (sys_bin / tool).symlink_to(real)
    env = {
        "HOME": str(home),
        "PATH": f"{bin_dir}:{sys_bin}",
        "LC_ALL": "C",
    }
    return subprocess.run(
        [str(SCRIPT), "--dry-run", *args], env=env, capture_output=True, text=True, timeout=30, cwd=ROOT
    )


def _commands(out: str) -> list[str]:
    return [line[2:] for line in out.splitlines() if line.startswith("+ ")]


def test_syntax() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    assert os.access(SCRIPT, os.X_OK)


def test_fresh_machine_installs_pixi_and_creates_kb(tmp_path: Path) -> None:
    r = _run(tmp_path, pixi=False)
    assert r.returncode == 0, r.stderr
    assert _commands(r.stdout) == [
        "curl -fsSL https://pixi.sh/install.sh | bash",
        "pixi install",
        "pixi run distill doctor",
        f"pixi run distill init --kb-id my-kb --name My knowledge base --kit base --dir {tmp_path}/home/knowledge --yes",
        "pixi run distill doctor --kb my-kb",
        "pixi run distill launch --kb my-kb",
    ]
    assert ".pixi/bin" in r.stdout


def test_existing_kb_is_kept_and_no_open(tmp_path: Path) -> None:
    kb = tmp_path / "home" / "knowledge" / "notes"
    kb.mkdir(parents=True)
    (kb / "kb.toml").write_text('id = "notes"\n')
    r = _run(tmp_path, "--no-open", pixi=True)
    assert r.returncode == 0, r.stderr
    cmds = _commands(r.stdout)
    assert cmds == ["pixi install", "pixi run distill doctor", "pixi run distill doctor --kb notes"]


def test_unsupported_system_refused(tmp_path: Path) -> None:
    r = _run(tmp_path, pixi=True, uname="MINGW64_NT-10.0")
    assert r.returncode == 2
    assert "WSL2" in r.stderr
    assert _commands(r.stdout) == []

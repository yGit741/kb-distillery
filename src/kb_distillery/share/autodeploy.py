"""Background autodeploy: knowledge commits and merges kick `share deploy-main` without waiting.

`trigger(reason, root=REPO)` never raises and never blocks:
  - `KB_SHARE_AUTODEPLOY=0`            → nothing (opt-out)
  - `root` is not a share-capable repo → nothing (test repos, bare clones)
  - a deploy is already running        → write the `pending` marker; `deploy-main` reruns once
                                         when it finishes (debounce: N triggers → one rerun)
  - otherwise                          → `pixi run share -- deploy-main` in its own session,
                                         stdout/stderr appended to LOG_PATH

`run_foreground(reason, root)` is the nightly backstop used by `ops sync`: same checks, but waits.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from kb_distillery.share.contracts import LOG_PATH, REPO

def _pixi() -> str:
    """launchd runs with a bare PATH, so fall back to pixi's install location."""
    return shutil.which("pixi") or str(Path.home() / ".pixi" / "bin" / "pixi")


COMMAND = [_pixi(), "run", "share", "--", "deploy-main"]


def enabled(root=REPO) -> bool:
    if os.environ.get("KB_SHARE_AUTODEPLOY") == "0":
        return False
    root = Path(root)
    return (root / "pixi.toml").is_file() and (root / "src" / "kb_distillery" / "share" / "deploy.py").is_file()


def _log(line: str) -> None:
    try:
        from kb_distillery.share.deploy import log
        log(line)
    except Exception:  # noqa: BLE001
        pass


def spawn(root=REPO) -> subprocess.Popen:
    """Detached `pixi run share -- deploy-main`; output goes to the share log."""
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    out = open(LOG_PATH, "a", encoding="utf-8")  # the child keeps the handle; closed on exit
    try:
        return subprocess.Popen(COMMAND, cwd=str(root), stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        out.close()


def trigger(reason: str, root=REPO) -> str:
    """Returns what happened: disabled | pending | spawned | error. Never raises."""
    try:
        if not enabled(root):
            return "disabled"
        from kb_distillery.share import deploy
        if deploy.lock_owner():
            deploy.pending_path().parent.mkdir(parents=True, exist_ok=True)
            deploy.pending_path().touch()
            _log(f"autodeploy ({reason}): deploy running — pending")
            return "pending"
        spawn(root)
        _log(f"autodeploy ({reason}): spawned deploy-main")
        return "spawned"
    except Exception as e:  # noqa: BLE001 — a failed trigger must never break the commit
        _log(f"autodeploy ({reason}): trigger failed — {type(e).__name__}: {e}")
        return "error"


def run_foreground(reason: str, root=REPO, timeout: int = 900) -> int:
    """Blocking deploy-main for the nightly sync; returns the exit code, -1 when skipped or broken."""
    try:
        if not enabled(root):
            return -1
        proc = subprocess.run(COMMAND, cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
        _log(f"autodeploy ({reason}, foreground): exit {proc.returncode}")
        if proc.stdout.strip():
            print(proc.stdout.strip().splitlines()[-1])
        return proc.returncode
    except Exception as e:  # noqa: BLE001
        _log(f"autodeploy ({reason}, foreground): failed — {type(e).__name__}: {e}")
        print(f"note: share deploy skipped — {e}", file=sys.stderr)
        return -1

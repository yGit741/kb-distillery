"""Per-worktree ship lock: one `ship commit|pr|merge` at a time inside the same worktree.

A second invocation in a worktree whose first run is still in its gates used to collide with it (both staged and
committed the same tree). The lock is an `fcntl.flock` on `kb-ship.lock` in that worktree's own git dir
(`git rev-parse --git-dir`: separate for every linked worktree), so different worktrees never block each other and
the machine-wide gate slot / merge queue (`gate_slot`, `queue`) stay a separate mechanism. The kernel drops the lock
when the holder dies, so a stale lock is reclaimed by the next run. `kb-ship.holder` (pid, start time, command) only
names the holder in the refusal message. It fails fast instead of waiting: a second run is almost always a mistake.

Re-entrant: while held, `KB_SHIP_LOCK_HELD` names the git dir and holder pid, so nested ship calls (and gate subprocesses) of the
same worktree do not ask again.
"""
import contextlib
import fcntl
import json
import os
import socket
import subprocess
import time

from kb_distillery.git.queue import _pid_alive, fmt_age

LOCK_NAME = "kb-ship.lock"
HOLDER_NAME = "kb-ship.holder"
HELD_ENV = "KB_SHIP_LOCK_HELD"


class ShipLockBusy(Exception):
    pass


def git_dir(root):
    cp = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-dir"], cwd=root,
                        capture_output=True, text=True, check=False)
    path = (cp.stdout or "").strip()
    if cp.returncode != 0 or not path:
        raise ShipLockBusy(f"cannot find the git dir of {root}: {(cp.stderr or '').strip()}")
    return path


def _holder(gdir):
    try:
        with open(os.path.join(gdir, HOLDER_NAME)) as f:
            h = json.load(f)
    except (OSError, ValueError):
        return {}
    return h if isinstance(h, dict) else {}


def _describe(h):
    if not h:
        return "another ship run (holder unknown)"
    age = fmt_age(time.time() - float(h.get("ts", time.time())))
    state = "" if h.get("host") != socket.gethostname() or _pid_alive(h.get("pid")) else ", process gone"
    return f"ship {h.get('cmd') or '?'} (pid {h.get('pid')}, started {age} ago{state})"


@contextlib.contextmanager
def hold(root, cmd):
    gdir = git_dir(root)
    env_gdir, _, env_pid = os.environ.get(HELD_ENV, "").rpartition("|")
    if env_gdir == gdir and _pid_alive(env_pid):      # a nested call of the live run that holds it
        yield
        return
    os.makedirs(gdir, exist_ok=True)
    fd = os.open(os.path.join(gdir, LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ShipLockBusy(f"another run is already active in this worktree: {_describe(_holder(gdir))}. "
                           f"Wait for it to finish (a crashed run frees the lock by itself) instead of starting a second.")
    except BaseException:
        os.close(fd)
        raise
    holder_path = os.path.join(gdir, HOLDER_NAME)
    with contextlib.suppress(OSError):
        with open(holder_path, "w") as f:
            json.dump({"pid": os.getpid(), "host": socket.gethostname(), "cmd": cmd, "ts": time.time()}, f)
    prev = os.environ.get(HELD_ENV)
    os.environ[HELD_ENV] = f"{gdir}|{os.getpid()}"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(HELD_ENV, None)
        else:
            os.environ[HELD_ENV] = prev
        with contextlib.suppress(OSError):
            os.unlink(holder_path)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

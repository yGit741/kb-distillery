"""Machine-wide gate slot: only one real gate run at a time across every worktree of the repo.

Parallel lanes (`ship commit|pr|merge` in several worktrees) used to run their pytest/vitest gates at once and
overload the cores, which made the timing tests fail. The slot is an `fcntl.flock` on `kb-gate.lock` in the git
*common* dir (shared by all worktrees, like the merge queue in `queue.py`); the kernel drops it when the holder
dies, so a crashed run never blocks anyone. `kb-gate.holder` is informational only (who to name while waiting).

Lock order: the merge slot (`queue.merge_slot`) is always taken BEFORE the gate slot, never after, and nothing
that holds the gate slot ever asks for the merge slot, so the two cannot deadlock.

A `sequence` is one `ship` invocation's gates and checks. The slot is taken lazily, the first time something
really runs, held until the outermost sequence ends and never taken for a fully reused run. Child processes of a
gate inherit `KB_GATE_SLOT_HELD`; with it set no slot is taken, which is what keeps the test suite (a gate itself)
from asking for the lock its own parent holds.
"""
import contextlib
import fcntl
import json
import os
import socket
import subprocess
import time

from kb_distillery.git.queue import _env_seconds, _pid_alive, common_dir, fmt_age

LOCK_NAME = "kb-gate.lock"
HOLDER_NAME = "kb-gate.holder"
HELD_ENV = "KB_GATE_SLOT_HELD"
DEFAULT_WAIT = 45 * 60
POLL = 0.2

_open = {}   # common dir -> the sequence open in this process


class GateSlotTimeout(Exception):
    pass


def child_env():
    """Environment for a gate subprocess: marks the slot as held so nothing below it asks for the lock again."""
    return {**os.environ, HELD_ENV: "1"}


def _holder(qdir):
    try:
        with open(os.path.join(qdir, HOLDER_NAME)) as f:
            h = json.load(f)
    except (OSError, ValueError):
        return None
    if h.get("host") == socket.gethostname() and not _pid_alive(h.get("pid")):
        return None
    return h


def _describe(h):
    if not h:
        return "another run"
    return f"{h.get('branch') or '?'} (pid {h.get('pid')}, {fmt_age(time.time() - float(h.get('ts', time.time())))})"


def _branch(root):
    cp = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=root, capture_output=True, text=True,
                        check=False)
    return (cp.stdout or "").strip() or os.path.basename(os.path.abspath(root))


class Sequence:
    def __init__(self, root, wait=None, log=print):
        self.root = root
        self.qdir = None            # resolved on first use: a reused run runs no git at all
        self.wait = _env_seconds("KB_GATE_WAIT", DEFAULT_WAIT) if wait is None else wait
        self.log = log
        self.fd = None

    def ensure(self):
        """Hold the slot (wait for it if another run has it). Idempotent; a no-op inside a gate."""
        if self.fd is not None or os.environ.get(HELD_ENV):
            return
        self.qdir = common_dir(self.root)
        os.makedirs(self.qdir, exist_ok=True)
        fd = os.open(os.path.join(self.qdir, LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o644)
        started = time.monotonic()
        announced = False
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    pass
                if not announced:
                    self.log(f"gate slot: waiting for {_describe(_holder(self.qdir))} "
                             f"(one gate run at a time on this machine; give up after {fmt_age(self.wait)})")
                    announced = True
                if time.monotonic() - started > self.wait:
                    raise GateSlotTimeout(f"gate slot: gave up after {fmt_age(self.wait)} waiting for "
                                          f"{_describe(_holder(self.qdir))} — raise KB_GATE_WAIT or check "
                                          f"{os.path.join(self.qdir, HOLDER_NAME)}")
                time.sleep(POLL)
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        waited = int(time.monotonic() - started)
        self.log(f"gate slot: taken (waited {waited}s)")
        with contextlib.suppress(OSError):
            with open(os.path.join(self.qdir, HOLDER_NAME), "w") as f:
                json.dump({"pid": os.getpid(), "host": socket.gethostname(), "branch": _branch(self.root),
                           "ts": time.time()}, f)

    def release(self):
        if self.fd is None:
            return
        with contextlib.suppress(OSError, TypeError):
            os.unlink(os.path.join(self.qdir, HOLDER_NAME))
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        self.fd = None


@contextlib.contextmanager
def sequence(root, wait=None, log=print):
    """One ship invocation's gates and checks. Nested use shares the outermost sequence (and its slot)."""
    key = os.path.realpath(root)
    seq = _open.get(key)
    outer = seq is None
    if outer:
        seq = _open[key] = Sequence(root, wait=wait, log=log)
    try:
        yield seq
    finally:
        if outer:
            _open.pop(key, None)
            seq.release()

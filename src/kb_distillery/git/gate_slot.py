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
import shutil
import signal
import socket
import subprocess
import sys
import time

from kb_distillery.git import night
from kb_distillery.git.queue import _env_seconds, _pid_alive, common_dir, fmt_age

LOCK_NAME = "kb-gate.lock"
HOLDER_NAME = "kb-gate.holder"
HELD_ENV = "KB_GATE_SLOT_HELD"
DEFAULT_WAIT = 45 * 60
COMMIT_WAIT = 10 * 60  # KB_COMMIT_GATE_WAIT: how long `ship commit` waits for the slot (its gates take about two minutes)
WORKERS = 4            # KB_GATE_WORKERS: pytest-xdist workers of a local tests gate (a number, or `auto` = one per core)
NICE = ("nice", "-n", "10")                        # a daytime gate yields to whoever is at the keyboard
# macOS: the utility scheduler class. Not `-b` (background), which pins a process to the efficiency cores and
# throttles its disk access.
UTILITY = ("taskpolicy", "-c", "utility")
POLL = 0.2
IDLE_MIN = 10          # KB_GATE_IDLE_MIN: no log output for this long AND ~0% CPU = hung
STEP_MAX_MIN = 45      # KB_GATE_STEP_MAX_MIN: hard cap for one gate step
IDLE_CPU = 1.0         # percent of the whole process tree under which it counts as not working
HEAVY = ("vitest", "web-tests", "web-check", "test-e2e", "test-ui-principles", "playwright")   # steps load-gated

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
                                          f"{_describe(_holder(self.qdir))} — raise KB_GATE_WAIT "
                                          f"(KB_COMMIT_GATE_WAIT for `ship commit`) or check "
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


def _env_minutes(name, default):
    try:
        v = float(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def _group_cpu_seconds(pgid):
    """Cumulative CPU seconds of every process in the process group (ps TIME is [[dd-]hh:]mm:ss.cc)."""
    cp = subprocess.run(["ps", "-A", "-o", "pgid=,time="], capture_output=True, text=True, check=False)
    total = 0.0
    for line in cp.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] != str(pgid):
            continue
        with contextlib.suppress(ValueError):
            days, _, rest = parts[1].rpartition("-")
            secs = 0.0
            for f in rest.split(":"):
                secs = secs * 60 + float(f)
            total += secs + (int(days) * 86400 if days else 0)
    return total


def tree_cpu(pgid, window=1.5, sleep=time.sleep):
    """Instantaneous %CPU of the process group: the CPU-time delta over `window` seconds (ps %cpu is a lifetime
    average and would stay high long after a tree hung)."""
    before = _group_cpu_seconds(pgid)
    sleep(window)
    return max(0.0, _group_cpu_seconds(pgid) - before) / window * 100.0


def commit_wait():
    """Seconds `ship commit` waits for the slot before it gives up (KB_COMMIT_GATE_WAIT)."""
    return _env_seconds("KB_COMMIT_GATE_WAIT", COMMIT_WAIT)


def is_night(root):
    """True while the night window of the repository at `root` is open (`ship night start`): nobody is at the
    keyboard, so gates may use the whole machine. False when there is no root or the window cannot be read."""
    if not root:
        return False
    try:
        return night.active(root)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def workers(root=None):
    """The `-n` value of a local tests gate: KB_GATE_WORKERS (a number, or `auto`); else one per core while the
    night window is open, and WORKERS capped by the core count by day. One worker per core in every lane at once is
    what overloaded the machine; CI calls pytest itself with `-n auto` and never reads this."""
    v = os.environ.get("KB_GATE_WORKERS", "").strip().lower()
    if v == "auto":
        return "auto"
    with contextlib.suppress(ValueError):
        if int(v) > 0:
            return str(int(v))
    if is_night(root):
        return "auto"
    return str(min(WORKERS, os.cpu_count() or 1))


def with_workers(cmd, root=None):
    """`cmd` with the value after pytest's `-n` replaced by `workers(root)`; unchanged when it has no `-n`."""
    cmd = list(cmd)
    if "-n" in cmd[:-1]:
        cmd[cmd.index("-n") + 1] = workers(root)
    return cmd


def priority_prefix(root=None, night_open=None):
    """What a real gate command is started through so it does not slow the desktop: by day `nice`, plus the utility
    scheduler class on macOS; nothing while the night window is open (`night_open`, read from `root` when not
    given). KB_GATE_PRIORITY=normal turns it off, KB_GATE_PRIORITY=low keeps it on at night too. Measured cost:
    about 3% on one test file."""
    choice = os.environ.get("KB_GATE_PRIORITY", "").strip().lower()
    if choice == "normal":
        return []
    if choice != "low" and (is_night(root) if night_open is None else night_open):
        return []
    prefix = []
    if sys.platform == "darwin" and shutil.which(UTILITY[0]):
        prefix += UTILITY
    if shutil.which(NICE[0]):
        prefix += NICE
    return prefix


def load_limit():
    try:
        v = float(os.environ["KB_GATE_MAX_LOAD"])
    except (KeyError, ValueError):
        v = 0.0
    return v if v > 0 else 2.0 * (os.cpu_count() or 1)


def is_heavy(name, cmd):
    text = f"{name} {' '.join(map(str, cmd))}"
    return any(h in text for h in HEAVY)


def wait_for_load(wait, log=print, load=lambda: os.getloadavg()[0], limit=None, sleep=time.sleep,
                  clock=time.monotonic, poll=5.0):
    """Hold a vitest/e2e step back (still inside the slot, so it is the queue) while the 1-minute load average is above
    the limit; bounded by `wait`, then GateSlotTimeout."""
    limit = load_limit() if limit is None else limit
    started = clock()
    announced = False
    while load() > limit:
        if not announced:
            log(f"gate slot: waiting for load {load():.1f} below {limit:.1f}")
            announced = True
        if clock() - started > wait:
            raise GateSlotTimeout(f"gate slot: gave up after {fmt_age(wait)} waiting for load {load():.1f} below "
                                  f"{limit:.1f} — raise KB_GATE_MAX_LOAD or KB_GATE_WAIT")
        sleep(poll)


def _kill_tree(proc):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, sig)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
    with contextlib.suppress(OSError):
        os.killpg(proc.pid, signal.SIGKILL)       # grandchildren that outlived the leader or ignored SIGTERM


def supervise(cmd, cwd, log_path, env=None, idle_min=None, max_min=None, cpu=tree_cpu, clock=time.monotonic,
              sleep=time.sleep, poll=2.0):
    """Run `cmd` writing to `log_path`; kill its whole process tree when the log has been silent for idle_min AND the
    tree uses ~0% CPU, or after max_min in all. Returns (returncode, reason) with reason None, "idle" or "cap"."""
    idle = (_env_minutes("KB_GATE_IDLE_MIN", IDLE_MIN) if idle_min is None else idle_min) * 60
    cap = (_env_minutes("KB_GATE_STEP_MAX_MIN", STEP_MAX_MIN) if max_min is None else max_min) * 60
    with open(log_path, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        started = last_move = clock()
        last_size = 0
        try:
            while proc.poll() is None:
                sleep(poll)
                now = clock()
                size = os.path.getsize(log_path)
                if size != last_size:
                    last_size, last_move = size, now
                if now - started > cap:
                    _kill_tree(proc)
                    return proc.returncode, "cap"
                if now - last_move > idle and cpu(proc.pid) < IDLE_CPU:
                    _kill_tree(proc)
                    return proc.returncode, "idle"
        except BaseException:
            _kill_tree(proc)
            raise
    return proc.returncode, None


def hung_message(name, reason, log_rel, idle_min=None, max_min=None):
    if reason == "idle":
        n = _env_minutes("KB_GATE_IDLE_MIN", IDLE_MIN) if idle_min is None else idle_min
        return f"hung gate, stopped after {n:g} idle minutes: {name} (see {log_rel})"
    n = _env_minutes("KB_GATE_STEP_MAX_MIN", STEP_MAX_MIN) if max_min is None else max_min
    return f"gate step over its cap, stopped after {n:g} minutes: {name} (see {log_rel})"

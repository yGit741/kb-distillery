"""Merge queue: serialize `ship merge` across every worktree of the repo.

State lives in the git *common* dir, so all worktrees share it:

    kb-merge.lock          fcntl.flock target (held by the merging process)
    kb-merge-queue.jsonl   FIFO of {pr, branch, pid, host, ts}

A merger appends its entry, waits until it is at the head of the queue *and* holds the lock,
runs the merge, and always removes its entry on exit. Entries whose pid is dead (same host) or
older than KB_MERGE_STALE seconds (default 20 min) are reclaimed with a warning. Waiting gives
up after KB_MERGE_WAIT seconds (default 30 min).
"""
import contextlib
import fcntl
import json
import os
import socket
import subprocess
import sys
import time

LOCK_NAME = "kb-merge.lock"
QUEUE_NAME = "kb-merge-queue.jsonl"
DEFAULT_WAIT = 30 * 60
DEFAULT_STALE = 20 * 60
POLL = 0.2


class QueueTimeout(Exception):
    pass


def common_dir(root):
    cp = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                        capture_output=True, text=True, check=False)
    path = (cp.stdout or "").strip()
    return path or os.path.join(root, ".git")


def _env_seconds(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, ValueError, TypeError, OverflowError):
        return True
    return True


def is_stale(entry, now=None, stale=None):
    now = time.time() if now is None else now
    stale = _env_seconds("KB_MERGE_STALE", DEFAULT_STALE) if stale is None else stale
    # waiters refresh `hb` every poll; the holder's `hb` is its lock time, so age = time holding
    if now - float(entry.get("hb", entry.get("ts", 0))) > stale:
        return True
    return entry.get("host") == socket.gethostname() and not _pid_alive(entry.get("pid"))


@contextlib.contextmanager
def _meta_lock(qdir):
    """Short exclusive lock guarding read-modify-write of the queue file."""
    fd = os.open(os.path.join(qdir, QUEUE_NAME + ".lock"), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read(qdir):
    try:
        with open(os.path.join(qdir, QUEUE_NAME)) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _write(qdir, entries):
    path = os.path.join(qdir, QUEUE_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)
    os.replace(tmp, path)


def entries(qdir):
    with _meta_lock(qdir):
        return _read(qdir)


def _reclaim(qdir, log=print):
    """Drop stale entries (dead pid / too old); returns the remaining queue."""
    q = _read(qdir)
    keep = []
    for e in q:
        if is_stale(e):
            log(f"warning: merge queue: reclaiming stale entry {describe(e)}")
        else:
            keep.append(e)
    if len(keep) != len(q):
        _write(qdir, keep)
    return keep


def _touch(qdir, me, now):
    """Refresh our heartbeat in the file (re-append at the tail if we were dropped)."""
    q = _read(qdir)
    me["hb"] = now
    for i, e in enumerate(q):
        if _same(e, me):
            q[i] = dict(me)
            break
    else:
        q.append(dict(me))
    _write(qdir, q)
    return q


def _same(a, b):
    return a.get("pid") == b.get("pid") and a.get("host") == b.get("host") and a.get("ts") == b.get("ts")


def remove(qdir, entry):
    with _meta_lock(qdir):
        _write(qdir, [e for e in _read(qdir) if not _same(e, entry)])


def describe(e, now=None):
    now = time.time() if now is None else now
    age = int(now - float(e.get("ts", now)))
    pr = f"#{e['pr']} " if e.get("pr") else ""
    return f"{pr}{e.get('branch', '?')} (pid {e.get('pid')}@{e.get('host')}, {fmt_age(age)})"


def fmt_age(sec):
    sec = max(0, int(sec))
    return f"{sec}s" if sec < 120 else f"{sec // 60}m" if sec < 7200 else f"{sec // 3600}h"


@contextlib.contextmanager
def merge_slot(root, branch, pr=None, wait=None, log=print):
    """Enqueue, wait for head-of-queue + flock, yield; always dequeue and unlock."""
    qdir = common_dir(root)
    wait = _env_seconds("KB_MERGE_WAIT", DEFAULT_WAIT) if wait is None else wait
    now = time.time()
    me = {"pr": pr, "branch": branch, "pid": os.getpid(), "host": socket.gethostname(), "ts": now, "hb": now}
    with _meta_lock(qdir):
        q = _read(qdir)
        q.append(me)
        _write(qdir, q)
    lock_fd = os.open(os.path.join(qdir, LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o644)
    locked, announced = False, False
    try:
        deadline = time.time() + wait
        while True:
            with _meta_lock(qdir):
                _reclaim(qdir, log)
                q = _touch(qdir, me, time.time())
                head = q[0]
                if _same(head, me):
                    try:
                        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        _touch(qdir, me, time.time())   # holder age counts from lock time
                    except BlockingIOError:
                        pass   # a reclaimed-but-alive holder still has the lock: keep waiting
            if locked:
                break
            if not announced and head is not None:
                log(f"merge queue: waiting behind {describe(head)}")
                announced = True
            if time.time() > deadline:
                raise QueueTimeout(f"merge queue: gave up after {fmt_age(wait)} waiting "
                                   f"(head: {describe(head) if head else 'none'}) — see `ship queue`")
            time.sleep(POLL)
        yield me
    finally:
        if locked:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        remove(qdir, me)


def summary(root):
    """One line for status output, or '' when the queue is empty."""
    q = entries(common_dir(root))
    if not q:
        return ""
    head, rest = q[0], q[1:]
    return f"merge queue: {describe(head)} merging" + (f", {len(rest)} waiting" if rest else "")


def cmd_queue(root, drop=None, out=sys.stdout):
    qdir = common_dir(root)
    if drop is not None:
        with _meta_lock(qdir):
            q = _read(qdir)
            match = [e for e in q if str(e.get("pr")) == str(drop) or e.get("pid") == drop]
            mine = [e for e in match if e.get("pid") == os.getpid() or is_stale(e)
                    or e.get("host") != socket.gethostname()]
            if not match:
                print(f"no queue entry for #{drop}", file=out)
                return 1
            if not mine:
                print(f"refusing: entry #{drop} belongs to a live process (pid {match[0].get('pid')})", file=out)
                return 1
            _write(qdir, [e for e in q if not any(_same(e, m) for m in mine)])
        print(f"dropped {len(mine)} entry for #{drop}", file=out)
        return 0
    q = entries(qdir)
    if not q:
        print("merge queue: empty", file=out)
        return 0
    for i, e in enumerate(q):
        role = "holder" if i == 0 else f"waiter {i}"
        flag = " [stale]" if is_stale(e) else ""
        print(f"{role}: {describe(e)}{flag}", file=out)
    return 0

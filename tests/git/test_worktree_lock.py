"""Per-worktree ship lock (kb_distillery.git.worktree_lock): second run refused naming the holder pid, stale lock
reclaimed, separate worktrees independent, re-entrant inside one run."""
import json
import os
import subprocess
import sys
import threading
import tempfile
import unittest
import unittest.mock

from kb_distillery.git import ship, worktree_lock



def _g(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


HOLDER = (
    "import os,sys;from kb_distillery.git import worktree_lock as w\n"
    "os.environ.pop(w.HELD_ENV, None)\n"
    "with w.hold(sys.argv[1], 'commit'):\n"
    "    print('ready', flush=True); sys.stdin.read()\n")


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = os.path.realpath(self.tmp.name)
        self.main = os.path.join(t, "repo")
        os.makedirs(self.main)
        _g(self.main, "init", "-q", "-b", "main")
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            _g(self.main, "config", k, v)
        _g(self.main, "commit", "-q", "--allow-empty", "-m", "init")
        self.wt = os.path.join(t, "wt")
        _g(self.main, "worktree", "add", "-q", "-b", "infra/x", self.wt)
        # Each test starts with no lock held, whatever the caller's environment says: `ship commit` holds this
        # worktree's lock while it runs the tests and exports HELD_ENV, and the lock restores that value on release.
        env = unittest.mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(worktree_lock.HELD_ENV, None)

    def _child(self, root):
        """A separate python process holding the lock; ends when its stdin closes (bounded, killed in teardown)."""
        p = subprocess.Popen([sys.executable, "-c", HOLDER, root], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             text=True)

        def stop():
            p.kill()
            p.wait(10)
            p.stdin.close()
            p.stdout.close()
        self.addCleanup(stop)
        timer = threading.Timer(30, p.kill)       # a child that never gets ready cannot hang the test
        timer.start()
        self.addCleanup(timer.cancel)
        self.assertEqual(p.stdout.readline().strip(), "ready")
        return p

    def test_second_run_refused_with_holder_pid(self):
        p = self._child(self.wt)
        with self.assertRaises(worktree_lock.ShipLockBusy) as cm:
            with worktree_lock.hold(self.wt, "commit"):
                self.fail("lock must not be granted")
        self.assertIn(f"pid {p.pid}", str(cm.exception))
        p.stdin.close()
        p.wait(10)
        with worktree_lock.hold(self.wt, "commit"):     # free again after the holder ends
            pass

    def test_worktrees_do_not_block_each_other(self):
        self._child(self.wt)
        with worktree_lock.hold(self.main, "commit"):
            pass

    def test_stale_holder_file_is_reclaimed(self):
        gdir = worktree_lock.git_dir(self.wt)
        with open(os.path.join(gdir, worktree_lock.HOLDER_NAME), "w") as f:
            json.dump({"pid": 2 ** 22 + 12345, "host": "x", "cmd": "commit", "ts": 1}, f)
        with worktree_lock.hold(self.wt, "pr"):
            self.assertEqual(worktree_lock._holder(gdir)["pid"], os.getpid())
        self.assertFalse(os.path.exists(os.path.join(gdir, worktree_lock.HOLDER_NAME)))

    def test_killed_holder_frees_lock(self):
        p = self._child(self.wt)
        p.kill()
        p.wait(10)
        with worktree_lock.hold(self.wt, "commit"):
            pass

    def test_reentrant_in_one_run(self):
        # run under `ship commit`, the gate itself holds a lock and exports HELD_ENV: start from a clean slate
        saved = os.environ.pop(worktree_lock.HELD_ENV, None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, worktree_lock.HELD_ENV, saved)
        with worktree_lock.hold(self.wt, "merge"):
            with worktree_lock.hold(self.wt, "commit"):
                pass
            self.assertIn(worktree_lock.HELD_ENV, os.environ)
        self.assertNotIn(worktree_lock.HELD_ENV, os.environ)

    def test_ship_locked_prints_refusal(self):
        p = self._child(self.wt)
        calls = []
        old = ship.ROOT
        ship.ROOT = self.wt
        try:
            with unittest.mock.patch("builtins.print") as pr:
                rc = ship._locked("commit", lambda: calls.append(1) or 0)
        finally:
            ship.ROOT = old
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])
        self.assertIn(f"pid {p.pid}", pr.call_args[0][0])


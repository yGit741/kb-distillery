"""Merge queue (kb.git.queue): FIFO serialization, stale reclaim, dequeue on failure, --drop."""
import io
import json
import multiprocessing as mp
import os
import socket
import subprocess
import tempfile
import time
import unittest

from kb.git import queue as mq


def _git_repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    return d


def _worker(root, name, start_at, log_path, hold):
    while time.time() < start_at:
        time.sleep(0.005)
    with mq.merge_slot(root, name, log=lambda *_: None):
        with open(log_path, "a") as f:
            f.write(f"start {name}\n")
        time.sleep(hold)
        with open(log_path, "a") as f:
            f.write(f"end {name}\n")


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.root = _git_repo()
        self.qdir = mq.common_dir(self.root)

    def test_common_dir_is_shared_git_dir(self):
        self.assertEqual(os.path.realpath(self.qdir), os.path.realpath(os.path.join(self.root, ".git")))

    def test_processes_serialized_fifo(self):
        log = os.path.join(self.root, "log.txt")
        ctx = mp.get_context("spawn")
        procs = []
        t0 = time.time() + 1.5
        for i, name in enumerate(["a", "b", "c"]):
            p = ctx.Process(target=_worker, args=(self.root, name, t0 + i * 0.3, log, 0.4))
            p.start()
            procs.append(p)
        for p in procs:
            p.join(30)
            self.assertEqual(p.exitcode, 0)
        lines = open(log).read().split()
        self.assertEqual(lines, ["start", "a", "end", "a", "start", "b", "end", "b", "start", "c", "end", "c"])
        self.assertEqual(mq.entries(self.qdir), [])

    def _seed(self, **kw):
        e = {"pr": 7, "branch": "infra/x", "pid": 999999, "host": socket.gethostname(), "ts": time.time()}
        e.update(kw)
        with open(os.path.join(self.qdir, mq.QUEUE_NAME), "a") as f:
            f.write(json.dumps(e) + "\n")
        return e

    def test_dead_pid_reclaimed(self):
        self._seed(pid=999999)   # not running
        logs = []
        with mq.merge_slot(self.root, "infra/me", wait=5, log=logs.append):
            self.assertEqual([e["branch"] for e in mq.entries(self.qdir)], ["infra/me"])
        self.assertTrue(any("reclaiming stale" in l for l in logs))

    def test_old_live_entry_reclaimed(self):
        self._seed(pid=os.getppid(), ts=time.time() - 3600, hb=time.time() - 3600)
        with mq.merge_slot(self.root, "infra/me", wait=5, log=lambda *_: None):
            pass
        self.assertEqual(mq.entries(self.qdir), [])

    def test_long_waiter_survives_stale_limit(self):
        """A waiter older than the stale limit still gets the slot once a slow holder finishes."""
        import threading
        os.environ["KB_MERGE_STALE"] = "0.5"
        try:
            got = threading.Event()
            def holder():
                with mq.merge_slot(self.root, "infra/slow", wait=5, log=lambda *_: None):
                    got.set()
                    time.sleep(1.5)
            th = threading.Thread(target=holder)
            th.start()
            got.wait(5)
            t0 = time.time()
            with mq.merge_slot(self.root, "infra/me", wait=5, log=lambda *_: None):
                self.assertGreater(time.time() - t0, 0.8)   # waited for the flock
            th.join()
        finally:
            del os.environ["KB_MERGE_STALE"]
        self.assertEqual(mq.entries(self.qdir), [])

    def test_live_head_blocks_until_timeout(self):
        self._seed(pid=os.getppid())
        with self.assertRaises(mq.QueueTimeout):
            with mq.merge_slot(self.root, "infra/me", wait=0.5, log=lambda *_: None):
                self.fail("should not get the slot")
        self.assertEqual([e["branch"] for e in mq.entries(self.qdir)], ["infra/x"])

    def test_failure_dequeues(self):
        with self.assertRaises(RuntimeError):
            with mq.merge_slot(self.root, "infra/me", log=lambda *_: None):
                raise RuntimeError("gate failed")
        self.assertEqual(mq.entries(self.qdir), [])
        with mq.merge_slot(self.root, "infra/next", wait=1, log=lambda *_: None):
            pass   # lock was released

    def test_drop_dead_entry_and_refuse_live(self):
        self._seed(pr=5, pid=999999)
        self._seed(pr=6, pid=os.getppid())
        out = io.StringIO()
        self.assertEqual(mq.cmd_queue(self.root, out=out), 0)
        self.assertIn("holder: #5", out.getvalue())
        self.assertIn("[stale]", out.getvalue())
        self.assertEqual(mq.cmd_queue(self.root, drop=5, out=io.StringIO()), 0)
        self.assertEqual(mq.cmd_queue(self.root, drop=6, out=io.StringIO()), 1)
        self.assertEqual(mq.cmd_queue(self.root, drop=42, out=io.StringIO()), 1)
        self.assertEqual([e["pr"] for e in mq.entries(self.qdir)], [6])
        self.assertIn("#6", mq.summary(self.root))


class ShipMergeQueueTest(unittest.TestCase):
    def test_ship_merge_failure_dequeues(self):
        from kb.git import ship
        root = _git_repo()
        subprocess.run(["git", "-C", root, "commit", "-q", "--allow-empty", "-m", "init"], check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", root, "checkout", "-q", "-b", "infra/q"], check=True)
        # no PR, no remote: fails inside the slot (--local without --pr)
        self.assertEqual(ship.cmd_merge(local=True, root=root, gates=False), 1)
        self.assertEqual(mq.entries(mq.common_dir(root)), [])


if __name__ == "__main__":
    unittest.main()

"""Machine-wide gate slot (kb_distillery.git.gate_slot): serialised runs, lazy/reused = no lock, per common dir,
released on failure and holder death, timeout, and no real lock from the test suite."""
import contextlib
import fcntl
import io
import multiprocessing as mp

mp = mp.get_context("fork")   # no re-import of ship in the child: start-up time cannot skew the timings
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_slot, queue, ship
from tests.git.test_gate_reuse import RepoCase, _g, _write


def _repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    return d


def _lock_free(qdir):
    fd = os.open(os.path.join(qdir, gate_slot.LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def _worker(root, name, go, release, log_path):
    """Take the slot when told (`go`), hold it until told (`release`): arrival and hold are driven, never timed."""
    os.environ.pop(gate_slot.HELD_ENV, None)
    go.wait(30)
    with gate_slot.sequence(root, log=lambda *_: None) as s:
        s.ensure()
        with open(log_path, "a") as f:
            f.write(f"start {name}\n")
        release.wait(30)
        with open(log_path, "a") as f:
            f.write(f"end {name}\n")


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return f.read().split("\n")[:-1]


def _release_all(events, procs):
    for ev in events:
        ev.set()
    for p in procs:
        p.join(5)
        if p.is_alive():
            p.terminate()


def _die_holding(root, ready):
    os.environ.pop(gate_slot.HELD_ENV, None)
    s = gate_slot.Sequence(root, log=lambda *_: None)
    s.ensure()
    open(ready, "w").close()
    time.sleep(60)


class SlotCase(unittest.TestCase):
    def setUp(self):
        self.root = _repo()
        self.qdir = queue.common_dir(self.root)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(gate_slot.HELD_ENV, None)    # these tests exercise the real lock, in tmp repos only

    def _wait_for(self, cond, what, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cond():
                return
            time.sleep(0.02)
        self.fail(f"timed out waiting for {what}")

    def run_two(self, roots):
        """p0 takes the slot and holds it; p1 asks for it meanwhile and may only start once p0 has ended."""
        log = os.path.join(tempfile.mkdtemp(), "log")
        go, release = [mp.Event() for _ in roots], [mp.Event() for _ in roots]
        ps = [mp.Process(target=_worker, args=(r, f"p{i}", go[i], release[i], log)) for i, r in enumerate(roots)]
        self.addCleanup(_release_all, go + release, ps)       # a failed assertion leaves no waiter behind
        for p in ps:
            p.start()
        go[0].set()
        self._wait_for(lambda: _lines(log) == ["start p0"], "p0 to take the slot")
        go[1].set()
        time.sleep(0.3)
        self.assertEqual(_lines(log), ["start p0"])          # p1 waits while p0 holds
        release[0].set()
        self._wait_for(lambda: _lines(log) == ["start p0", "end p0", "start p1"], "p1 to take the slot after p0")
        release[1].set()
        for p in ps:
            p.join(20)
        return _lines(log)

    def assert_serial(self, lines):
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0].split()[0], "start")
        self.assertEqual(lines[1], "end " + lines[0].split()[1])   # holder ends before the next one starts
        self.assertEqual(lines[2].split()[0], "start")

    def test_two_processes_are_serialised(self):
        self.assert_serial(self.run_two([self.root, self.root]))

    def test_lock_is_per_common_dir_shared_by_worktrees(self):
        wt = os.path.join(tempfile.mkdtemp(), "wt")
        _g(self.root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "--allow-empty", "-qm", "x")
        _g(self.root, "worktree", "add", "-q", "-b", "other", wt)
        self.assertEqual(os.path.realpath(queue.common_dir(wt)), os.path.realpath(self.qdir))
        self.assert_serial(self.run_two([self.root, wt]))
        # a different repo has its own slot: no wait
        other = _repo()
        with gate_slot.sequence(self.root, log=lambda *_: None) as a:
            a.ensure()
            with gate_slot.sequence(other, log=lambda *_: None) as b:
                b.ensure()
                self.assertIsNotNone(b.fd)

    def test_released_on_failure(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = ship.run_gate("boom", [sys.executable, "-c", "raise SystemExit(3)"], self.root)
        self.assertFalse(ok)
        self.assertIn("gate slot: taken", out.getvalue())
        self.assertTrue(_lock_free(self.qdir))
        with self.assertRaises(RuntimeError), gate_slot.sequence(self.root, log=lambda *_: None) as s:
            s.ensure()
            raise RuntimeError
        self.assertTrue(_lock_free(self.qdir))

    def test_holder_death_frees_the_slot(self):
        ready = os.path.join(tempfile.mkdtemp(), "ready")
        p = mp.Process(target=_die_holding, args=(self.root, ready))
        p.start()
        for _ in range(400):
            if os.path.exists(ready):
                break
            time.sleep(0.05)
        self.assertFalse(_lock_free(self.qdir))
        os.kill(p.pid, signal.SIGKILL)
        p.join(5)
        logs = []
        with gate_slot.sequence(self.root, wait=5, log=logs.append) as s:
            s.ensure()
        self.assertEqual([l for l in logs if "waiting" in l], [])   # stale holder file named nobody, no wait

    def test_waiting_names_the_holder_and_timeout_is_a_clear_error(self):
        logs = []
        with gate_slot.sequence(self.root, log=lambda *_: None) as holder:
            holder.ensure()
            other = gate_slot.Sequence(self.root, wait=0.5, log=logs.append)
            with self.assertRaises(gate_slot.GateSlotTimeout) as cm:
                other.ensure()
        self.assertIn("waiting for", logs[0])
        self.assertIn(str(os.getpid()), logs[0])
        self.assertIn("gave up", str(cm.exception))
        self.assertIn("KB_GATE_WAIT", str(cm.exception))

    def test_run_gate_reports_timeout_as_failure(self):
        os.environ["KB_GATE_WAIT"] = "0.3"
        out = io.StringIO()
        with gate_slot.sequence(self.root, log=lambda *_: None) as holder:
            holder.ensure()
            # the same process shares its own sequence; hold the lock from a second fd to simulate another run
        fd = os.open(os.path.join(self.qdir, gate_slot.LOCK_NAME), os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            with contextlib.redirect_stdout(out), patch.object(gate_slot, "DEFAULT_WAIT", 0.3):
                ok = ship.run_gate("x", [sys.executable, "-c", "pass"], self.root)
        finally:
            os.close(fd)
        self.assertFalse(ok)
        self.assertIn("error: gate slot: gave up", out.getvalue())

    def test_nested_sequences_share_one_slot(self):
        logs = []
        with gate_slot.sequence(self.root, log=logs.append) as outer:
            outer.ensure()
            with gate_slot.sequence(self.root, log=logs.append) as inner:
                self.assertIs(inner, outer)
                inner.ensure()
            self.assertIsNotNone(outer.fd)       # inner exit does not release
        self.assertIsNone(outer.fd)
        self.assertEqual(len([l for l in logs if "taken" in l]), 1)

    def test_child_env_marks_the_slot_held(self):
        self.assertEqual(gate_slot.child_env()[gate_slot.HELD_ENV], "1")


class NoRealLockTests(unittest.TestCase):
    """The suite runs inside a gate that holds the slot: nothing here may ask for the real one."""

    def test_suite_env_makes_the_slot_a_no_op_even_on_the_real_repo(self):
        self.assertEqual(os.environ.get(gate_slot.HELD_ENV), "1")      # set by tests/git/conftest.py
        real = queue.common_dir(ship.ROOT)
        with gate_slot.sequence(ship.ROOT, log=lambda *_: None) as s:
            s.ensure()
            self.assertIsNone(s.fd)
        self.assertFalse(os.path.exists(os.path.join(real, gate_slot.HOLDER_NAME)) and
                         _holder_is_me(real))

    def test_gate_children_run_marked(self):
        d = tempfile.mkdtemp()
        out = io.StringIO()
        with patch.dict(os.environ), contextlib.redirect_stdout(out):
            os.environ.pop(gate_slot.HELD_ENV, None)
            ok = ship.run_gate("env", [sys.executable, "-c",
                                       f"import os,sys; sys.exit(0 if os.environ.get('{gate_slot.HELD_ENV}')=='1' else 9)"],
                               _repo())
        self.assertTrue(ok, out.getvalue())


def _holder_is_me(qdir):
    return (gate_slot._holder(qdir) or {}).get("pid") == os.getpid()


class ReuseTakesNoSlot(RepoCase):
    def test_fully_reused_run_never_touches_the_lock(self):
        with patch.dict(os.environ):
            os.environ.pop(gate_slot.HELD_ENV, None)
            self.gates()                                   # real run: takes the slot
            qdir = queue.common_dir(self.root)
            os.unlink(os.path.join(qdir, gate_slot.LOCK_NAME))
            out = self.gates()                             # all reused
            self.assertIn("reused", out)
            self.assertNotIn("gate slot", out)
            self.assertFalse(os.path.exists(os.path.join(qdir, gate_slot.LOCK_NAME)))

    def test_real_run_prints_the_slot_line_once_for_the_whole_sequence(self):
        with patch.dict(os.environ):
            os.environ.pop(gate_slot.HELD_ENV, None)
            out = self.gates()
        self.assertEqual(out.count("gate slot: taken"), 1)


class CommitTakesTheSlot(RepoCase):
    """`ship commit` used to run its gates outside the slot: several lanes committing at once piled their gates up."""

    def commit(self):
        _write(self.root, "src/kb_distillery/git/a.py", "mine")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ship.cmd_commit("feat(git): thing", root=self.root)
        return rc, out.getvalue()

    def test_commit_gates_run_in_the_slot_with_the_short_wait(self):
        os.environ["KB_COMMIT_GATE_WAIT"] = "7"
        with patch.object(ship, "run_gates", return_value=False) as gates:
            rc, _ = self.commit()
        self.assertEqual(rc, 1)
        kw = gates.call_args.kwargs
        self.assertEqual(kw["wait"], 7.0)
        self.assertEqual(kw["only"], ship.COMMIT_GATES)
        self.assertIsNot(kw.get("slot", True), False)

    def test_local_gates_mode_keeps_the_long_wait(self):
        os.environ[ship.LOCAL_GATES_ENV] = "1"
        with patch.object(ship, "run_gates", return_value=False) as gates:
            self.commit()
        self.assertIsNone(gates.call_args.kwargs["wait"])
        self.assertIsNone(gates.call_args.kwargs["only"])

    def test_the_default_wait_is_ten_minutes(self):
        os.environ.pop("KB_COMMIT_GATE_WAIT", None)
        self.assertEqual(gate_slot.commit_wait(), 600.0)

    def test_a_second_commit_waits_for_the_first_and_says_so(self):
        os.environ.pop(gate_slot.HELD_ENV, None)
        os.environ["KB_COMMIT_GATE_WAIT"] = "0.3"
        qdir = queue.common_dir(self.root)
        fd = os.open(os.path.join(qdir, gate_slot.LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o644)   # another lane's gate run
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            rc, out = self.commit()
        finally:
            os.close(fd)
        self.assertEqual(rc, 1)
        self.assertIn("gate slot: waiting for", out)
        self.assertIn("error: gate slot: gave up", out)
        self.assertIn("KB_COMMIT_GATE_WAIT", out)
        self.assertIn("nothing committed", out)
        self.assertEqual(self.runs(), [])                               # no gate ran while the other lane held the slot

    def test_a_commit_alone_takes_the_slot_and_frees_it(self):
        os.environ.pop(gate_slot.HELD_ENV, None)
        with patch.object(ship.gate_cache, "test_subset", return_value=None):     # unmapped: the (fake) full tests gate
            rc, out = self.commit()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.runs(), ["tests"])                        # of the fake gates only the commit gate ran
        self.assertEqual(out.count("gate slot: taken"), 1)
        self.assertTrue(_lock_free(queue.common_dir(self.root)))


class OrderTests(unittest.TestCase):
    def test_merge_slot_is_taken_before_the_gate_slot_never_after(self):
        from kb_distillery.git import queue as mq
        root = _repo()
        subprocess.run(["git", "-C", root, "commit", "-q", "--allow-empty", "-m", "i"], check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", root, "checkout", "-q", "-b", "infra/o"], check=True)
        events = []

        @contextlib.contextmanager
        def fake_merge_slot(*a, **k):
            events.append(("merge-slot", "gate sequence open" if gate_slot._open else "no gate sequence"))
            yield

        def fake_locked(*a, **k):
            events.append(("merge-body", "inside merge slot"))
            with patch.dict(os.environ):
                os.environ.pop(gate_slot.HELD_ENV, None)
                with gate_slot.sequence(root, log=lambda *_: None) as s:
                    s.ensure()
                    events.append(("gate-slot", "taken"))
            return 0

        with patch.object(mq, "merge_slot", fake_merge_slot), patch.object(ship, "_merge_locked", fake_locked):
            self.assertEqual(ship.cmd_merge(local=True, root=root, gates=False), 0)
        self.assertEqual(events, [("merge-slot", "no gate sequence"), ("merge-body", "inside merge slot"),
                                  ("gate-slot", "taken")])


if __name__ == "__main__":
    unittest.main()

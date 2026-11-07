"""Gate budget (gate_slot.supervise / wait_for_load): hung steps are killed, load holds heavy steps back.
Fake clocks and load readers; the real subprocesses used here are bounded and short."""
import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_slot, ship


def _log():
    return os.path.join(tempfile.mkdtemp(), "step.log")


class SuperviseCase(unittest.TestCase):
    def test_normal_step_passes_through(self):
        rc, why = gate_slot.supervise([sys.executable, "-c", "print('hi')"], ".", _log(), poll=0.02)
        self.assertEqual((rc, why), (0, None))

    def test_failing_step_keeps_its_code(self):
        rc, why = gate_slot.supervise([sys.executable, "-c", "raise SystemExit(3)"], ".", _log(), poll=0.02)
        self.assertEqual((rc, why), (3, None))

    def test_silent_idle_step_is_killed(self):
        t0 = time.monotonic()
        rc, why = gate_slot.supervise([sys.executable, "-c", "import time; time.sleep(30)"], ".", _log(),
                                      idle_min=0.01, cpu=lambda pgid: 0.0, poll=0.05)
        self.assertEqual(why, "idle")
        self.assertLess(time.monotonic() - t0, 10)

    def test_silent_but_busy_step_is_not_killed(self):
        rc, why = gate_slot.supervise([sys.executable, "-c", "import time; time.sleep(1.2)"], ".", _log(),
                                      idle_min=0.01, cpu=lambda pgid: 99.0, poll=0.05)
        self.assertEqual((rc, why), (0, None))

    def test_chatty_step_is_not_idle(self):
        code = "import time\nfor i in range(12):\n print(i, flush=True); time.sleep(0.1)"
        rc, why = gate_slot.supervise([sys.executable, "-c", code], ".", _log(), idle_min=0.01,
                                      cpu=lambda pgid: 0.0, poll=0.05)
        self.assertEqual((rc, why), (0, None))

    def test_hard_cap_kills_even_a_busy_step(self):
        rc, why = gate_slot.supervise([sys.executable, "-c", "import time; time.sleep(30)"], ".", _log(),
                                      max_min=0.01, cpu=lambda pgid: 99.0, poll=0.05)
        self.assertEqual(why, "cap")

    def test_env_overrides(self):
        with patch.dict(os.environ, {"KB_GATE_IDLE_MIN": "0.01"}):
            rc, why = gate_slot.supervise([sys.executable, "-c", "import time; time.sleep(30)"], ".", _log(),
                                          cpu=lambda pgid: 0.0, poll=0.05)
        self.assertEqual(why, "idle")

    def test_message_names_log_and_minutes(self):
        m = gate_slot.hung_message("tests", "idle", ".cache/ship-gates/x-tests.log", idle_min=10)
        self.assertIn("hung gate, stopped after 10 idle minutes", m)
        self.assertIn(".cache/ship-gates/x-tests.log", m)

    def test_run_gate_reports_a_hung_step_and_frees_the_slot(self):
        root = tempfile.mkdtemp()
        os.system(f"git init -q {root}")
        real = gate_slot.supervise
        with patch.dict(os.environ, {"KB_GATE_IDLE_MIN": "0.01"}), \
                patch.object(gate_slot, "supervise", lambda *a, **k: real(*a, cpu=lambda p: 0.0, poll=0.05, **k)), \
                patch.object(gate_slot, "child_env", lambda: dict(os.environ)), \
                patch.object(ship, "_REAL_RUN", ship.subprocess.run), \
                patch.object(gate_slot, "Sequence") as seq:
            seq.return_value.ensure = lambda: None
            seq.return_value.release = lambda: None
            seq.return_value.wait = 1
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ok = ship.run_gate("tests", [sys.executable, "-c", "import time; time.sleep(30)"], root)
        self.assertFalse(ok)
        self.assertIn("hung gate, stopped after 0.01 idle minutes", out.getvalue())
        self.assertIn("tests.log", out.getvalue())


class LoadCase(unittest.TestCase):
    def clock(self):
        t = [0.0]
        return t, lambda: t[0], lambda s: t.__setitem__(0, t[0] + s)

    def test_low_load_starts_at_once(self):
        gate_slot.wait_for_load(60, log=lambda m: self.fail(m), load=lambda: 1.0, limit=4.0)

    def test_waits_then_starts_and_logs_once(self):
        t, clock, sleep = self.clock()
        loads = iter([9.0, 9.0, 8.0, 3.0] + [3.0] * 5)
        lines = []
        gate_slot.wait_for_load(600, log=lines.append, load=lambda: next(loads), limit=4.0, sleep=sleep, clock=clock)
        self.assertEqual(len(lines), 1)
        self.assertIn("waiting for load 9.0 below 4.0", lines[0])

    def test_bounded_by_the_wait_limit(self):
        t, clock, sleep = self.clock()
        with self.assertRaises(gate_slot.GateSlotTimeout):
            gate_slot.wait_for_load(30, log=lambda m: None, load=lambda: 99.0, limit=4.0, sleep=sleep, clock=clock)

    def test_limit_defaults_and_env(self):
        with patch.dict(os.environ, {"KB_GATE_MAX_LOAD": "7"}):
            self.assertEqual(gate_slot.load_limit(), 7.0)
        with patch.dict(os.environ):
            os.environ.pop("KB_GATE_MAX_LOAD", None)
            self.assertEqual(gate_slot.load_limit(), 2.0 * (os.cpu_count() or 1))

    def test_nonpositive_limit_falls_back(self):
        with patch.dict(os.environ, {"KB_GATE_MAX_LOAD": "0"}):
            self.assertEqual(gate_slot.load_limit(), 2.0 * (os.cpu_count() or 1))

    def test_heavy_detection(self):
        self.assertTrue(gate_slot.is_heavy("web-vitest", ["npm", "run"]))
        self.assertTrue(gate_slot.is_heavy("x", ["pixi", "run", "test-e2e"]))
        self.assertFalse(gate_slot.is_heavy("lint", ["python", "-m", "lint"]))


if __name__ == "__main__":
    unittest.main()


class CpuCase(unittest.TestCase):
    def test_tree_cpu_is_a_time_delta(self):
        reads = iter([10.0, 10.0, 10.0, 11.5])
        with patch.object(gate_slot, "_group_cpu_seconds", lambda pgid: next(reads)):
            self.assertAlmostEqual(gate_slot.tree_cpu(1, window=1.5, sleep=lambda s: None), 0.0)
            self.assertAlmostEqual(gate_slot.tree_cpu(1, window=1.5, sleep=lambda s: None), 100.0)

    def test_kill_reaches_a_grandchild_that_ignores_sigterm(self):
        pidfile = _log() + ".pid"
        child = ("import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                 f"open({pidfile!r},'w').write(str(os.getpid()));time.sleep(30)")
        code = f"import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c',{child!r}])\ntime.sleep(30)"
        rc, why = gate_slot.supervise([sys.executable, "-c", code], ".", _log(), idle_min=0.03,
                                      cpu=lambda p: 0.0, poll=0.05)
        self.assertEqual(why, "idle")
        pid = int(open(pidfile).read())
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.05)
        self.fail("grandchild survived the kill")

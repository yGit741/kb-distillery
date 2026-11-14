"""Daytime gates run below the desktop and on a few workers; while the night window is open they get the whole
machine (kb_distillery.git.gate_slot: priority_prefix, workers, is_night)."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_slot, night, ship

EVERYTHING = lambda name: f"/usr/bin/{name}"       # noqa: E731  (shutil.which that finds every tool)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in ("KB_GATE_PRIORITY", "KB_GATE_WORKERS"):
            os.environ.pop(name, None)

    def prefix(self, platform="darwin", which=EVERYTHING, root=None):
        with patch.object(sys, "platform", platform), patch.object(shutil, "which", side_effect=which):
            return gate_slot.priority_prefix(self.root if root is None else root)


class NightWindow(Case):
    def test_is_night_follows_the_window(self):
        self.assertFalse(gate_slot.is_night(self.root))
        night.start(self.root, hours=1)
        self.assertTrue(gate_slot.is_night(self.root))
        night.stop(self.root)
        self.assertFalse(gate_slot.is_night(self.root))

    def test_no_root_or_an_unreadable_window_is_day(self):
        self.assertFalse(gate_slot.is_night(None))
        self.assertFalse(gate_slot.is_night(""))
        with patch.object(night, "active", side_effect=OSError("no git")):
            self.assertFalse(gate_slot.is_night(self.root))


class Priority(Case):
    def test_by_day_on_macos_a_gate_is_started_in_the_utility_class_and_niced(self):
        self.assertEqual(self.prefix(), ["taskpolicy", "-c", "utility", "nice", "-n", "10"])

    def test_it_is_never_the_background_class(self):
        """`taskpolicy -b` pins a process to the efficiency cores and throttles its disk access."""
        self.assertNotIn("-b", self.prefix())

    def test_elsewhere_it_is_nice_alone(self):
        self.assertEqual(self.prefix(platform="linux"), ["nice", "-n", "10"])

    def test_a_missing_tool_is_left_out(self):
        self.assertEqual(self.prefix(which=lambda name: None), [])
        self.assertEqual(self.prefix(which=lambda name: "/usr/bin/nice" if name == "nice" else None), ["nice", "-n", "10"])

    def test_at_night_gates_run_at_normal_priority(self):
        night.start(self.root, hours=1)
        self.assertEqual(self.prefix(), [])

    def test_the_environment_decides_either_way(self):
        os.environ["KB_GATE_PRIORITY"] = "normal"
        self.assertEqual(self.prefix(), [])
        night.start(self.root, hours=1)
        os.environ["KB_GATE_PRIORITY"] = "low"
        self.assertEqual(self.prefix(), ["taskpolicy", "-c", "utility", "nice", "-n", "10"])

    def test_the_prefix_really_starts_the_command(self):
        """On this machine, whatever it is: the prefix plus a command exits like the command alone."""
        cmd = gate_slot.priority_prefix(self.root) + [sys.executable, "-c", "import sys; sys.exit(7)"]
        self.assertEqual(subprocess.run(cmd, check=False).returncode, 7)


class ShipUsesIt(Case):
    def supervised(self, run):
        seen = []

        def fake(cmd, cwd, log, env=None, **kw):
            seen.append(list(cmd))
            open(log, "w").close()
            return 0, None

        with patch.object(gate_slot, "supervise", side_effect=fake), contextlib.redirect_stdout(io.StringIO()), \
                patch.object(sys, "platform", "darwin"), patch.object(shutil, "which", side_effect=EVERYTHING):
            run()
        return seen[0]

    def test_a_real_gate_is_started_through_the_prefix(self):
        cmd = self.supervised(lambda: ship.run_gate("ruff", ["ruff", "check"], self.root))
        self.assertEqual(cmd, ["taskpolicy", "-c", "utility", "nice", "-n", "10", "ruff", "check"])

    def test_a_lane_check_is_too(self):
        cmd = self.supervised(lambda: ship._supervised_check("api-schema-check", ["pixi", "run", "api-schema-check"], self.root))
        self.assertEqual(cmd[:6], ["taskpolicy", "-c", "utility", "nice", "-n", "10"])
        self.assertEqual(cmd[6:], ["pixi", "run", "api-schema-check"])

    def test_at_night_the_command_is_started_as_it_is(self):
        night.start(self.root, hours=1)
        cmd = self.supervised(lambda: ship.run_gate("ruff", ["ruff", "check"], self.root))
        self.assertEqual(cmd, ["ruff", "check"])


class NightWorkers(Case):
    def test_by_day_the_cap_holds(self):
        self.assertEqual(gate_slot.workers(self.root), str(min(4, os.cpu_count() or 1)))

    def test_at_night_one_worker_per_core(self):
        night.start(self.root, hours=1)
        self.assertEqual(gate_slot.workers(self.root), "auto")
        self.assertEqual(gate_slot.with_workers(["pytest", "-n", "auto", "tests"], self.root), ["pytest", "-n", "auto", "tests"])
        night.stop(self.root)
        self.assertEqual(gate_slot.with_workers(["pytest", "-n", "auto", "tests"], self.root)[2], str(min(4, os.cpu_count() or 1)))

    def test_an_explicit_number_wins_at_night_too(self):
        night.start(self.root, hours=1)
        os.environ["KB_GATE_WORKERS"] = "3"
        self.assertEqual(gate_slot.workers(self.root), "3")

    def test_without_a_root_it_is_the_day_value(self):
        self.assertEqual(gate_slot.workers(), str(min(4, os.cpu_count() or 1)))


if __name__ == "__main__":
    unittest.main()

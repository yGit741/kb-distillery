"""Load against throughput (kb_distillery.git.gate_timings): one line per real gate run, and `ship night report`."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_timings, night, queue, ship

NOW = 1_800_000_000.0


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        subprocess.run(["git", "init", "-q", self.root], check=True)

    def add(self, gate, secs, load, minutes_ago=10, rc=0, mode="day", times=1):
        for _ in range(times):
            gate_timings.record(self.root, gate, secs, rc, load, 60.0, workers="4", mode=mode, branch="infra/x",
                                now=NOW - minutes_ago * 60)

    def report(self, **kw):
        return gate_timings.report(self.root, now=NOW, cores=10, **kw)

    def bands(self, out):
        """{band label: its cells} from the table rows of a report."""
        rows = {}
        for line in out.split("\n")[2:]:
            if line.startswith("load "):
                rows[line[:22].strip()] = line[22:].split()
        return rows


class RecordAndRead(Case):
    def test_a_run_is_one_line_in_the_common_dir(self):
        self.add("tests", 91.26, 3.14)
        path = os.path.join(queue.common_dir(self.root), gate_timings.FILE)
        with open(path) as f:
            line = f.read()
        self.assertEqual(line.count("\n"), 1)
        self.assertEqual(len(line.rstrip("\n").split("\t")), len(gate_timings.FIELDS))
        (row,) = gate_timings.read(self.root)
        self.assertEqual((row["gate"], row["secs"], row["load"], row["rc"], row["workers"], row["mode"], row["branch"]),
                         ("tests", 91.3, 3.1, 0, "4", "day", "infra/x"))

    def test_read_skips_broken_lines_and_honours_since(self):
        self.add("ruff", 2.0, 1.0, minutes_ago=120)
        self.add("ruff", 2.0, 1.0, minutes_ago=5)
        with open(os.path.join(queue.common_dir(self.root), gate_timings.FILE), "a") as f:
            f.write("garbage\n1\t2\t3\n" + "\t".join(["x"] * len(gate_timings.FIELDS)) + "\n")
        self.assertEqual(len(gate_timings.read(self.root)), 2)
        self.assertEqual(len(gate_timings.read(self.root, since=NOW - 3600)), 1)

    def test_no_file_reads_as_no_runs(self):
        self.assertEqual(gate_timings.read(self.root), [])

    def test_a_missing_memory_reading_is_an_empty_cell(self):
        gate_timings.record(self.root, "ruff", 2.0, 0, 1.0, None, now=NOW)
        self.assertEqual(gate_timings.read(self.root)[0]["mem"], "")

    def test_the_file_rolls_over_and_the_old_part_is_still_read(self):
        with patch.object(gate_timings, "MAX_BYTES", 200):
            for i in range(8):
                self.add("ruff", 2.0, 1.0, minutes_ago=100 - i)
        qdir = queue.common_dir(self.root)
        self.assertTrue(os.path.exists(os.path.join(qdir, gate_timings.FILE + ".1")))
        rows = gate_timings.read(self.root)
        self.assertGreater(len(rows), 4)                                 # more than the new file alone holds
        self.assertEqual([r["ts"] for r in rows], sorted(r["ts"] for r in rows))

    def test_record_never_raises(self):
        gate_timings.record(os.path.join(self.root, "missing", "dir"), "ruff", 2.0, 0, 1.0, 60.0)
        with patch.object(gate_timings, "_path", side_effect=OSError("no git")):
            gate_timings.record(self.root, "ruff", 2.0, 0, 1.0, 60.0)
            self.assertEqual(gate_timings.read(self.root), [])

    def test_outside_a_repository_nothing_is_written_and_no_git_dir_appears(self):
        with tempfile.TemporaryDirectory() as plain:
            gate_timings.record(plain, "ruff", 2.0, 0, 1.0, 60.0)
            self.assertEqual(os.listdir(plain), [])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertTrue(ship.run_gate("ruff", [sys.executable, "-c", "pass"], plain), out.getvalue())
            self.assertFalse(os.path.exists(os.path.join(plain, ".git")))

    def test_machine_reads_a_load_and_a_percentage(self):
        load, mem = gate_timings.machine()
        self.assertGreaterEqual(load, 0.0)
        if mem is not None:
            self.assertTrue(0 <= mem <= 100, mem)

    def test_snapshot_never_raises(self):
        load, mem, branch = gate_timings.snapshot(self.root)
        self.assertGreaterEqual(load, 0.0)
        self.assertIsInstance(branch, str)
        with patch.object(gate_timings, "machine", side_effect=RuntimeError("boom")), \
                patch.object(subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertEqual(gate_timings.snapshot(self.root), (0.0, None, ""))


class Bands(unittest.TestCase):
    def test_bands_follow_the_core_count(self):
        self.assertEqual([gate_timings.band_of(load, 10) for load in (0, 4.9, 5, 9.9, 10, 19.9, 20, 340)],
                         [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertEqual([gate_timings.band_label(i, 10) for i in range(4)],
                         ["load under 5", "load 5 to 10", "load 10 to 20", "load 20 and over"])
        self.assertEqual(gate_timings.band_of(3, 4), 1)


class Report(Case):
    def test_no_runs(self):
        self.assertIn("no successful gate run in the last 16 hours", self.report())

    def test_slowdown_is_measured_on_constant_work_against_the_quietest_band(self):
        self.add("ruff", 2.0, 3.0, minutes_ago=300, times=3)
        self.add("ruff", 2.4, 8.0, minutes_ago=200, times=3)
        self.add("ruff", 1.6, 3.0, minutes_ago=150, mode="night", times=3)
        self.add("ruff", 4.8, 30.0, minutes_ago=100, mode="night", times=3)
        self.add("tests", 90.0, 3.0, minutes_ago=290)
        self.add("tests", 400.0, 30.0, minutes_ago=90, mode="night")
        out = self.report()
        rows = self.bands(out)
        self.assertEqual(rows["load under 5"], ["7", "3", "1.0x", "90", "s"])            # runs, night runs, slowdown, tests
        self.assertEqual(rows["load 5 to 10"], ["3", "0", "1.2x", "-"])                 # 2.4 / 2.0
        self.assertEqual(rows["load 20 and over"], ["4", "4", "3.0x", "400", "s"])      # 4.8 / 1.6, night against night
        self.assertIn("saturation: from load 20 and over the same work took 3.0x as long", out)
        self.assertIn("14 gate runs over 3.5 h, 4.0 per hour", out)

    def test_day_and_night_runs_are_each_compared_with_their_own_kind(self):
        """Day gates are niced and night gates are not: a faster night run in a busier band is not a 0.5x speed-up."""
        self.add("ruff", 2.0, 3.0, times=3)
        self.add("ruff", 1.0, 8.0, mode="night", times=3)
        out = self.report()
        self.assertEqual(self.bands(out)["load 5 to 10"][2], "1.0x")
        self.assertNotIn("0.5x", out)
        self.assertIn("day runs: load under 5, night runs: load 5 to 10", out)

    def test_one_slow_run_is_not_a_verdict(self):
        self.add("ruff", 2.0, 3.0, times=3)
        self.add("ruff", 50.0, 30.0)
        out = self.report()
        self.assertEqual(self.bands(out)["load 20 and over"][2:4], ["few", "runs"])
        self.assertNotIn("saturation", out)
        self.assertIn("not enough spread", out)

    def test_no_saturation_when_the_busiest_band_is_still_quick(self):
        self.add("ruff", 2.0, 3.0, times=3)
        self.add("ruff", 2.6, 12.0, times=3)
        out = self.report()
        self.assertIn("no saturation seen", out)
        self.assertIn("(load 10 to 20) ran the same work at 1.3x", out)

    def test_one_band_is_not_enough_to_judge(self):
        self.add("ruff", 2.0, 3.0, times=2)
        self.add("lint-imports", 2.0, 4.0, times=2)
        self.assertIn("one load band with 3 such runs: not enough spread", self.report())

    def test_without_constant_work_there_is_no_baseline_and_it_says_so(self):
        self.add("tests", 90.0, 3.0)
        self.add("tests", 300.0, 30.0)
        out = self.report()
        self.assertIn("no baseline yet", out)
        self.assertNotIn("one load band", out)                           # two bands were seen: the old wording was wrong
        self.assertEqual(self.bands(out)["load 20 and over"][-2:], ["300", "s"])

    def test_a_rate_needs_an_hour_of_data(self):
        self.add("ruff", 2.0, 3.0, minutes_ago=12)
        self.add("tests", 120.0, 3.0, minutes_ago=10)
        self.add("lint-imports", 2.0, 3.0, minutes_ago=10)
        out = self.report()
        self.assertIn("3 gate runs over 2 min, 10 cores", out)
        self.assertNotIn("per hour", out)
        self.add("ruff", 2.0, 3.0, minutes_ago=132)
        self.assertIn("4 gate runs over 2.0 h, 2.0 per hour", self.report())

    def test_failed_runs_and_old_runs_are_left_out(self):
        self.add("ruff", 2.0, 3.0)
        self.add("ruff", 50.0, 3.0, rc=1)
        self.add("ruff", 50.0, 30.0, minutes_ago=60 * 30)
        out = self.report()
        self.assertIn("1 gate runs", out)
        self.assertNotIn("load 20 and over", out)
        self.assertIn("2 gate runs", self.report(hours=48))


class ShipRecordsRealRuns(Case):
    def gate(self, code="pass", name="ruff"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = ship.run_gate(name, [sys.executable, "-c", code], self.root)
        return ok, out.getvalue()

    def test_a_real_gate_run_leaves_one_line(self):
        ok, out = self.gate()
        self.assertTrue(ok, out)
        (row,) = gate_timings.read(self.root)
        self.assertEqual((row["gate"], row["rc"], row["mode"]), ("ruff", 0, "day"))
        self.assertGreaterEqual(row["secs"], 0.0)

    def test_a_failed_gate_is_recorded_with_its_exit_code(self):
        ok, _ = self.gate("import sys; sys.exit(3)")
        self.assertFalse(ok)
        self.assertEqual(gate_timings.read(self.root)[0]["rc"], 3)

    def test_night_runs_are_marked_and_carry_the_worker_count(self):
        night.start(self.root, hours=1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ship.run_gate("tests", [sys.executable, "-c", "pass", "-n", "7"], self.root)
        (row,) = gate_timings.read(self.root)
        self.assertEqual((row["mode"], row["workers"]), ("night", "7"))

    def test_the_night_window_is_read_once_per_gate(self):
        """The priority a gate starts with and the mode recorded for it come from the same reading."""
        with patch.object(ship.gate_slot, "is_night", return_value=True) as is_night:
            self.gate()
        self.assertEqual(is_night.call_count, 1)
        self.assertEqual(gate_timings.read(self.root)[0]["mode"], "night")

    def test_a_mocked_run_records_nothing(self):
        with patch.object(subprocess, "run", wraps=subprocess.run):
            self.gate()
        self.assertEqual(gate_timings.read(self.root), [])

    def test_ship_night_report_prints_the_table(self):
        self.gate()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ship.cmd_night("report", root=self.root)
        self.assertEqual(rc, 0)
        self.assertIn("gate timings, last 16 hours: 1 gate runs", out.getvalue())
        self.assertNotIn("night window", out.getvalue())                # report does not touch or describe the window
        self.assertFalse(night.active(self.root))


if __name__ == "__main__":
    unittest.main()

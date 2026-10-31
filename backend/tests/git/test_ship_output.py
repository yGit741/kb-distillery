"""ship keeps long gate output out of the terminal and always ends on an unmissable RESULT line."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from kb.git import ship


def run_gate(name, script, root):
    out = io.StringIO()
    with redirect_stdout(out):
        ok = ship.run_gate(name, [sys.executable, "-c", script], root)
    return ok, out.getvalue()


class GateOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)

    def test_a_passing_gate_prints_one_line_and_keeps_the_output_in_a_log(self):
        ok, out = run_gate("tests", "for i in range(500): print('line', i)", self.root)
        self.assertTrue(ok)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("gate: tests ok", out)
        self.assertNotIn("line 499", out)
        log = os.path.join(self.root, out.split("log ")[1].split(")")[0])
        with open(log) as f:
            self.assertIn("line 499", f.read())                       # nothing is lost, it is just not in the terminal

    def test_a_failing_gate_shows_the_tail_and_the_log_path(self):
        ok, out = run_gate("lint", "import sys\nfor i in range(100): print('row', i)\nsys.exit(3)", self.root)
        self.assertFalse(ok)
        lines = out.strip().splitlines()
        self.assertIn("gate: lint FAILED", lines[0])
        self.assertIn("row 99", out)
        self.assertNotIn("row 10\n", out)                              # only the last GATE_TAIL_LINES lines
        self.assertEqual(lines[-1], "error: lint failed")

    def test_stderr_is_captured_too(self):
        ok, out = run_gate("tests", "import sys\nprint('boom', file=sys.stderr)\nsys.exit(1)", self.root)
        self.assertFalse(ok)
        self.assertIn("boom", out)


class ResultLine(unittest.TestCase):
    def last_line(self, argv, code):
        out = io.StringIO()
        with patch.object(ship, "_main", return_value=code), redirect_stdout(out):
            rc = ship.main(argv)
        return rc, out.getvalue().strip().splitlines()[-1]

    def test_a_failure_ends_on_failed(self):
        rc, last = self.last_line(["commit", "feat(x): y"], 1)
        self.assertEqual(rc, 1)
        self.assertEqual(last, "RESULT: FAILED (ship commit, exit 1)")

    def test_a_success_ends_on_ok_even_when_the_command_returns_none(self):
        rc, last = self.last_line(["merge"], None)
        self.assertEqual(last, "RESULT: ok (ship merge, exit 0)")

    def test_read_only_commands_print_no_result_line(self):
        out = io.StringIO()
        with patch.object(ship, "_main", return_value=0), redirect_stdout(out):
            ship.main(["queue"])
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

"""The tests gate runs the suite in parallel on a capped number of workers, and the dev environment declares the
plugin that provides `-n`."""
import os
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_slot, ship
from tests.git.test_gate_reuse import RepoCase, _write

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYTEST = ["python", "-m", "pytest", "-q", "-n", "auto", "-m", "not serial", "tests"]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _n(cmd):
    return cmd[cmd.index("-n") + 1]


class TestsGateParallel(unittest.TestCase):
    def test_tests_gate_is_declared_parallel(self):
        self.assertIn("-n", dict(ship.GATES)["tests"])

    def test_pytest_xdist_is_declared(self):
        if not os.path.isfile(os.path.join(ROOT, "pixi.toml")):
            self.skipTest("not a source checkout")
        self.assertRegex(_read("pixi.toml"), r"(?m)^pytest-xdist\s*=")
        self.assertRegex(_read("pyproject.toml"), r'"pytest-xdist[^"]*"')
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("xdist"))


class LocalWorkerCap(unittest.TestCase):
    """One worker per core in every lane at once overloaded the machine: a local gate starts at most 4."""

    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("KB_GATE_WORKERS", None)

    def test_default_is_four_or_the_core_count_when_smaller(self):
        self.assertEqual(gate_slot.workers(), str(min(4, os.cpu_count() or 1)))
        with patch.object(os, "cpu_count", return_value=2):
            self.assertEqual(gate_slot.workers(), "2")
        with patch.object(os, "cpu_count", return_value=64):
            self.assertEqual(gate_slot.workers(), "4")

    def test_the_environment_overrides_it(self):
        for value, want in (("2", "2"), ("12", "12"), ("auto", "auto"), (" AUTO ", "auto")):
            os.environ["KB_GATE_WORKERS"] = value
            self.assertEqual(gate_slot.workers(), want, value)

    def test_a_bad_value_falls_back_to_the_default(self):
        default = str(min(4, os.cpu_count() or 1))
        for value in ("", "0", "-3", "many", "2.5"):
            os.environ["KB_GATE_WORKERS"] = value
            self.assertEqual(gate_slot.workers(), default, value)

    def test_with_workers_rewrites_only_the_value_after_n(self):
        os.environ["KB_GATE_WORKERS"] = "3"
        self.assertEqual(gate_slot.with_workers(PYTEST), ["python", "-m", "pytest", "-q", "-n", "3", "-m", "not serial", "tests"])
        self.assertEqual(_n(PYTEST), "auto")                                   # the declared command is not edited in place
        self.assertEqual(gate_slot.with_workers(["ruff", "check"]), ["ruff", "check"])
        self.assertEqual(gate_slot.with_workers(["x", "-n"]), ["x", "-n"])     # a trailing -n has no value to replace


class GateRunsCapped(RepoCase):
    """What `ship` really starts: the full tests gate and the commit subset both carry the capped worker count."""

    def started(self, **kw):
        seen = {}

        def fake(name, cmd, root=None, slot=True):
            seen[name] = list(cmd)
            return True

        with patch.dict(os.environ), patch.object(ship, "GATES", [("tests", PYTEST)]), \
                patch.object(ship, "run_gate", side_effect=fake), patch.object(ship, "_xdist_ok", return_value=True):
            os.environ.pop("KB_GATE_WORKERS", None)
            os.environ.update(kw.pop("env", {}))
            self.gates(**kw)
        return seen["tests"]

    def test_full_run_is_capped(self):
        self.assertEqual(_n(self.started()), str(min(4, os.cpu_count() or 1)))

    def test_commit_subset_is_capped(self):
        _write(self.root, "src/kb_distillery/git/a.py", "changed")
        cmd = self.started(scope="subset", only=ship.COMMIT_GATES)
        self.assertEqual(_n(cmd), str(min(4, os.cpu_count() or 1)))
        self.assertIn("tests/git", cmd)                                        # it is the subset command, not the full one

    def test_the_override_reaches_the_command(self):
        self.assertEqual(_n(self.started(env={"KB_GATE_WORKERS": "auto"})), "auto")
        _write(self.root, "src/kb_distillery/git/a.py", "changed")
        self.assertEqual(_n(self.started(scope="subset", env={"KB_GATE_WORKERS": "2"})), "2")


class CommitGatesAreLight(RepoCase):
    def test_typecheck_is_not_a_commit_gate(self):
        self.assertEqual(ship.COMMIT_GATES, ("ruff", "lint-imports", "tests"))
        self.assertFalse({n for n, _ in ship.FRONTEND_GATES} & set(ship.COMMIT_GATES))

    def test_a_commit_that_touches_the_app_installs_nothing(self):
        """The app gates were built (npm ci in a fresh worktree) and then dropped by the `only` filter."""
        with patch.object(ship, "frontend_changed", return_value=True), \
                patch.object(ship, "frontend_gates", side_effect=AssertionError("npm install for a commit")), \
                patch.object(ship, "run_gate", return_value=True), patch.object(ship, "_xdist_ok", return_value=True):
            self.gates(scope="subset", only=ship.COMMIT_GATES)

    def test_a_full_run_still_gets_the_app_gates(self):
        ran = []
        with patch.object(ship, "frontend_changed", return_value=True), \
                patch.object(ship, "frontend_gates", return_value=[("web-typecheck", ["true"])]), \
                patch.object(ship, "run_gate", side_effect=lambda name, *a, **k: ran.append(name) or True), \
                patch.object(ship, "_xdist_ok", return_value=True):
            self.gates()
        self.assertIn("web-typecheck", ran)


if __name__ == "__main__":
    unittest.main()

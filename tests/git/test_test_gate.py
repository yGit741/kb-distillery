"""The tests gate runs the suite in parallel, and the dev environment declares the plugin that provides `-n`."""
import os
import unittest

from kb_distillery.git import ship

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestsGateParallel(unittest.TestCase):
    def test_tests_gate_carries_n6(self):
        cmd = dict(ship.GATES)["tests"]
        self.assertIn("-n", cmd)
        self.assertEqual(cmd[cmd.index("-n") + 1], "6")

    def test_pytest_xdist_is_declared(self):
        if not os.path.isfile(os.path.join(ROOT, "pixi.toml")):
            self.skipTest("not a source checkout")
        self.assertRegex(_read("pixi.toml"), r"(?m)^pytest-xdist\s*=")
        self.assertRegex(_read("pyproject.toml"), r'"pytest-xdist[^"]*"')
        self.assertIn("pytest-xdist", _read("pixi.lock"))


if __name__ == "__main__":
    unittest.main()

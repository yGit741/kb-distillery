"""Root names of the OSS layout are known to the schema, and ship's gate prefixes cannot go quiet."""
import tomllib
import unittest
from pathlib import Path

from kb_distillery.vault import schema

REPO = Path(__file__).resolve().parents[2]
NEW_DIRS = ("src", "tests", "web", "examples", "scripts")
NEW_FILES = ("pyproject.toml", "CHANGELOG.md", "CONTRIBUTING.md")


class RootNamesTests(unittest.TestCase):
    def test_new_dirs_known_everywhere(self):
        for d in NEW_DIRS:
            self.assertIn(d, schema.CODE_TOP_DIRS)
            self.assertIn(d, schema.ROOT_DIRS)
            self.assertEqual(schema.lane_of(f"{d}/x.py"), "tooling", d)

    def test_new_files_known_everywhere(self):
        for f in NEW_FILES:
            self.assertIn(f, schema.ROOT_FILES)
            self.assertEqual(schema.lane_of(f), "tooling", f)
        for f in ("CHANGELOG.md", "CONTRIBUTING.md"):
            self.assertIn(f, schema.ROOT_MD)

    def test_gate_prefixes_are_known_roots(self):
        roots = set(schema.ROOT_DIRS) | set(schema.ROOT_FILES)
        for name, prefixes in schema.GATE_PREFIXES.items():
            for p in prefixes:
                self.assertIn(p.split("/")[0], roots, f"{name}: {p}")
                self.assertEqual(schema.lane_of(p if "/" in p else p), "tooling", f"{name}: {p}")

    def test_every_gate_group_matches_something_real(self):
        for name, prefixes in schema.GATE_PREFIXES.items():
            self.assertTrue(any((REPO / p).exists() for p in prefixes), f"gate group {name} matches no path: {prefixes}")


class AutodeployOffTests(unittest.TestCase):
    def test_pixi_activation_env_disables_autodeploy(self):
        env = tomllib.loads((REPO / "pixi.toml").read_text())["activation"]["env"]
        self.assertEqual(env["KB_SHARE_AUTODEPLOY"], "0")

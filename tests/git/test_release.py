"""Tests for src/kb_distillery/git/release.py on a temp copy: version bump, changelog move, refusals. No git, no network."""
import os
import tempfile
import unittest
from datetime import date

from kb_distillery.git import release

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- A thing.

## [0.1.0]

Initial.

### Added

- Old.
"""
PYPROJECT = '[project]\nname = "x"\nversion = "0.1.0"\n\n[tool.other]\nversion = "9"\n'


class ReleaseHelper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for name, text in (("CHANGELOG.md", CHANGELOG), ("pyproject.toml", PYPROJECT)):
            with open(os.path.join(self.root, name), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8") as f:
            return f.read()

    def test_bump_and_changelog_move(self):
        cmds = release.prepare("0.2.0", self.root, branch="infra/release-v0.2.0", today=date(2026, 12, 1))
        self.assertIn('version = "0.2.0"', self.read("pyproject.toml"))
        self.assertIn('version = "9"', self.read("pyproject.toml"))        # only the project version moves
        cl = self.read("CHANGELOG.md")
        self.assertIn("## [Unreleased]\n\n## [0.2.0] - 2026-12-01\n\n### Added\n\n- A thing.\n\n## [0.1.0]", cl)
        self.assertEqual(release.changelog_section("0.2.0", self.root), "### Added\n\n- A thing.")
        self.assertIn("pixi run ship -- tag v0.2.0", cmds)
        self.assertTrue(cmds[-1].endswith("origin v0.2.0"))

    def test_refuses_on_main_or_without_a_branch(self):
        for branch in ("main", "", None):
            with self.assertRaises(release.ReleaseError):
                release.prepare("0.2.0", self.root, branch=branch)
        self.assertIn('version = "0.1.0"', self.read("pyproject.toml"))

    def test_refuses_bad_old_or_duplicate_versions_and_empty_unreleased(self):
        for bad in ("v0.2.0", "0.2", "0.1.0", "0.0.9"):
            with self.assertRaises(release.ReleaseError, msg=bad):
                release.prepare(bad, self.root, branch="infra/x")
        release.prepare("0.2.0", self.root, branch="infra/x")
        with self.assertRaises(release.ReleaseError):        # [Unreleased] is empty now
            release.prepare("0.3.0", self.root, branch="infra/x")

    def test_notes_section_stops_at_the_next_heading(self):
        body = release.changelog_section("0.1.0", self.root)
        self.assertTrue(body.startswith("Initial."))
        self.assertNotIn("A thing", body)
        with self.assertRaises(release.ReleaseError):
            release.changelog_section("0.9.0", self.root)

    def test_main_prints_notes_and_refuses_a_bad_version(self):
        self.assertEqual(release.main(["--notes", "0.1.0"], root=self.root), 0)
        self.assertEqual(release.main(["v1"], root=self.root), 1)


if __name__ == "__main__":
    unittest.main()

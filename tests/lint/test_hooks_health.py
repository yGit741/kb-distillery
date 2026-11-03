#!/usr/bin/env python3
"""hooks_health in src/kb_distillery/lint/lint.py: the repo's own hook configs must read as wired.

Runs against the real `.claude/settings.json`, so a move of the guard
(as in the meta/ → backend/ restructure) that the health check does not follow fails here."""
import os
import unittest

from kb_distillery.lint import lint

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HooksHealthTests(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, ".claude", "settings.json")),
                         "owner tooling: .claude/ is export-ignored, so the public checkout has no hook config")
    def test_repo_hook_configs_name_the_guard(self):
        status, ok = lint.hooks_health()
        self.assertTrue(ok, status)
        self.assertEqual(status, "claude ok")

    def test_module_path_and_legacy_script_both_count(self):
        self.assertTrue(lint._names_guard('PYTHONPATH=src python3 -m kb_distillery.git.guard'))
        self.assertTrue(lint._names_guard('python3 meta/guard.py'))
        self.assertFalse(lint._names_guard('bash scripts/hooks/block-git-write.sh'))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""hooks_health in backend/src/kb/lint/lint.py: the repo's own hook configs must read as wired.

Runs against the real `.cursor/hooks.json` and `.claude/settings.json`, so a move of the guard
(as in the meta/ → backend/ restructure) that the health check does not follow fails here."""
import unittest

from kb.lint import lint


class HooksHealthTests(unittest.TestCase):
    def test_repo_hook_configs_name_the_guard(self):
        status, ok = lint.hooks_health()
        self.assertTrue(ok, status)
        self.assertEqual(status, "cursor ok, claude ok")

    def test_module_path_and_legacy_script_both_count(self):
        self.assertTrue(lint._names_guard('PYTHONPATH=backend/src python3 -m kb.git.guard'))
        self.assertTrue(lint._names_guard('python3 meta/guard.py'))
        self.assertFalse(lint._names_guard('bash .cursor/hooks/block-git-write.sh'))


if __name__ == "__main__":
    unittest.main()

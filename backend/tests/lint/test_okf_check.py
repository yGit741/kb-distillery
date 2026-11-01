#!/usr/bin/env python3
"""okf-check reports OKF v0.2 gaps per rule and never fails the run."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb.lint import okf_check


class OkfCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-okf-")
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "raw"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def page(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def rules(self, rel):
        findings, _ = okf_check.check(self.root)
        return sorted(rule for rule, _ in findings.get(rel, []))

    def test_clean_page_has_no_findings(self):
        self.page("wiki/b.md", "---\ntype: idea\n---\n\n# Beta\n")
        self.page("wiki/a.md", "---\ntype: idea\nstatus: stable\ncreated: 2026-10-12T09:00:00+00:00\n"
                  "sources:\n  - resource: /wiki/b.md\n---\n\nSee [B](/wiki/b.md#beta).\n")
        self.assertEqual(okf_check.check(self.root)[0], {})

    def test_frontmatter_rules(self):
        self.page("wiki/a.md", "---\nstatus: digested\ncreated: 2026-10-12\nsources:\n  - title: x\n---\n\nbody\n")
        self.assertEqual(self.rules("wiki/a.md"), ["sources", "status", "timestamp", "type"])

    def test_no_frontmatter_is_a_type_finding(self):
        self.page("wiki/a.md", "just text\n")
        self.assertEqual(self.rules("wiki/a.md"), ["type"])

    def test_body_rules(self):
        self.page("wiki/b.md", "---\ntype: idea\n---\n\n# Beta\n")
        self.page("wiki/a.md", "---\ntype: idea\n---\n\n[[b]] `[[in code]]` [gone](/wiki/nope.md) "
                  "[bad](/wiki/b.md#nope) [raw](/raw/x.pdf) [web](https://example.com)\n")
        self.assertEqual(self.rules("wiki/a.md"), ["boundary", "link", "link", "wikilink"])

    def test_reserved_pages_need_no_type(self):
        self.page("index.md", "# Index\n")
        self.assertEqual(okf_check.check(self.root)[0], {})

    def test_main_is_report_only(self):
        self.page("wiki/a.md", "[[x]]\n")
        with mock.patch("kb.paths.vault_root", return_value=self.root):
            self.assertEqual(okf_check.main([]), 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Smoke tests for the dashboard Start tab: route, nav entry, and that every skill it names exists."""
import os
import re
import sys
import unittest

from kb_distillery.kbconfig import checkout_root
ROOT = checkout_root()   # code, not vault content

from kb_distillery.dashboard.shell import TABS, inject_nav

START = os.path.join(ROOT, "src", "kb_distillery", "dashboard", "start.html")


class StartPageTests(unittest.TestCase):
    def setUp(self):
        with open(START, encoding="utf-8") as f:
            self.html = f.read()

    def test_first_tab(self):
        self.assertEqual(TABS[0], ("start", "/start", "Start"))
        self.assertIn('href="/start" class="active"', inject_nav(self.html, "start"))

    def test_named_skills_exist(self):
        skills = set()
        for where in (("src", "kb_distillery", "kits", "base", "skills"), ("src", "kb_distillery", "kits", "research", "skills"),
                      (".claude", "skills")):
            skills |= set(os.listdir(os.path.join(ROOT, *where)))
        named = set(re.findall(r"<code>([a-z][a-z0-9-]+)</code></td>", self.html))
        named |= set(re.findall(r"skill <code>([a-z][a-z0-9-]+)</code>", self.html))
        missing = sorted(n for n in named if n not in skills and "-" in n)
        self.assertEqual(missing, [])

    def test_assets_exist(self):
        for asset in re.findall(r'/static/([\w.-]+)', self.html):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "src", "kb_distillery", "dashboard", "static", asset)), asset)


if __name__ == "__main__":
    unittest.main()

"""Light checks for the scopes frontend (there is no JS test runner)."""
import os
import re
import sys
import unittest
from pathlib import Path

from kb_distillery.paths import CODE_DIR

DASH = Path(CODE_DIR) / "dashboard"
STATIC = DASH / "static"
NEW_JS = ["scopes.js", "selection.js"]
DIALOG = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")


class ScopesUiTests(unittest.TestCase):
    def test_scopes_page_references_its_assets(self):
        html = (DASH / "scopes.html").read_text(encoding="utf-8")
        self.assertIn("/static/scopes.js", html)
        self.assertIn("/static/scopes.css", html)
        self.assertIn("{{NAV}}", html)

    def test_graph_page_loads_selection(self):
        html = (DASH / "graph.html").read_text(encoding="utf-8")
        self.assertIn("/static/selection.js", html)
        self.assertIn("/static/selection.css", html)

    def test_no_browser_dialogs(self):
        for name in NEW_JS:
            text = (STATIC / name).read_text(encoding="utf-8")
            self.assertIsNone(DIALOG.search(text), f"{name} uses a browser dialog")

    def test_nav_has_scopes_tab(self):
        from kb_distillery.dashboard import shell
        self.assertIn(("scopes", "/scopes", "Scopes"), shell.TABS)


if __name__ == "__main__":
    unittest.main()

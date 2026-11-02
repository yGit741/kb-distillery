#!/usr/bin/env python3
"""wiki/index.md is generated (OKF reserved file): bulleted relative links, no Meta rows, not a page; lint checks its links."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb_distillery.lint import lint


class IndexLinks(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-index-")
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "meta"))
        self.patches = [mock.patch.object(lint, "ROOT", self.root),
                        mock.patch.object(lint, "errors", []), mock.patch.object(lint, "warnings", [])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def touch(self, rel, text="x"):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(text)

    def pages(self):
        return {"alpha": ("wiki/alpha.md", {"type": "idea", "maturity": "seed", "description": "About | alpha."},
                          "# Alpha [one]\n\nBody.\n"),
                "beta": ("wiki/beta.md", {"type": "idea", "description": "[Alpha one](alpha.md) in a summary"}, "# Beta\n")}

    def index(self, pages=None):
        lint.write_index(pages if pages is not None else self.pages(), quiet=True)
        return open(os.path.join(self.root, "wiki", "index.md"), encoding="utf-8").read()

    def test_the_index_lives_in_the_bundle_root_and_the_root_stays_clean(self):
        self.index()
        self.assertTrue(os.path.isfile(os.path.join(self.root, "wiki", "index.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "index.md")))

    def test_okf_shape_frontmatter_has_only_okf_version_and_rows_are_relative_links(self):
        text = self.index()
        self.assertTrue(text.startswith("---\nokf_version: 0.2\n---\n"))
        self.assertNotIn("type: meta", text)
        self.assertIn("- [Alpha one](alpha.md) (seed) — About | alpha.", text)      # title the app shows, maturity, summary
        self.assertIn("- [Beta](beta.md) — Alpha one in a summary", text)           # a link inside a summary is plain text
        self.assertNotIn("[[", text)

    def test_there_is_no_meta_section_and_no_meta_rows(self):
        self.touch("meta/log.md")
        self.touch("meta/thesis.md")
        self.touch("AGENTS.md")
        text = self.index()
        for needle in ("## Meta", "thesis", "AGENTS", "(log.md)", "[[log]]"):
            self.assertNotIn(needle, text)

    def test_the_index_and_the_log_are_not_pages(self):
        self.touch("wiki/alpha.md", "---\ntype: idea\n---\n# Alpha\n")
        self.touch("wiki/index.md", "---\nokf_version: 0.2\n---\n")
        self.touch("wiki/log.md", "# Log\n")
        self.assertEqual(lint.wiki_page_files(), ["wiki/alpha.md"])

    def test_a_generated_index_passes_its_own_link_check(self):
        self.index()
        self.assertEqual(lint.check_index_links(self.pages()), 0)
        self.assertEqual(lint.errors, [])

    def test_a_dangling_link_in_index_is_an_error(self):
        self.touch("wiki/index.md", "- [Ghost](ghost.md) — x\n")
        self.assertEqual(lint.check_index_links({}), 1)
        self.assertTrue(any("ghost" in e for e in lint.errors))

    def test_a_wikilink_in_index_is_an_error(self):
        self.touch("wiki/index.md", "| [[alpha]] | x |\n")
        self.assertEqual(lint.check_index_links(self.pages()), 1)
        self.assertTrue(any("wikilink [[alpha]]" in e for e in lint.errors))


if __name__ == "__main__":
    unittest.main()

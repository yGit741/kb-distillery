#!/usr/bin/env python3
"""wiki/index.md (a tiny root) and wiki/<type>/index.md (the rows) are generated OKF reserved files: bulleted relative
links, no Meta rows, not pages; lint checks the links of every one of them."""
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
        """The root and the idea section, as one text."""
        lint.write_index(pages if pages is not None else self.pages(), quiet=True)
        return "".join(open(os.path.join(self.root, "wiki", rel), encoding="utf-8").read() for rel in ("index.md", "idea/index.md"))

    def test_the_index_lives_in_the_bundle_root_and_the_root_stays_clean(self):
        self.index()
        self.assertTrue(os.path.isfile(os.path.join(self.root, "wiki", "index.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "index.md")))

    def test_okf_shape_frontmatter_has_only_okf_version_and_rows_are_relative_links(self):
        text = self.index()
        self.assertTrue(text.startswith("---\nokf_version: 0.2\n---\n"))
        self.assertNotIn("type: meta", text)
        self.assertIn("- [Alpha one](../alpha.md) — About | alpha.", text)      # title the app shows, summary: no maturity
        self.assertIn("- [Beta](../beta.md) — Alpha one in a summary", text)           # a link inside a summary is plain text
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

    def test_the_root_lists_sections_not_pages(self):
        self.index()
        root = open(os.path.join(self.root, "wiki", "index.md"), encoding="utf-8").read()
        self.assertIn("- [Ideas](idea/index.md) — 2 pages.", root)
        self.assertNotIn("alpha.md", root)

    def test_a_section_link_to_a_missing_index_file_is_an_error(self):
        self.touch("wiki/index.md", "- [Ideas](idea/index.md) — 1 page.\n")
        self.assertEqual(lint.check_index_links(self.pages()), 1)
        self.assertTrue(any("idea/index.md" in e for e in lint.errors))

    def test_a_dangling_row_in_a_section_index_is_an_error(self):
        self.touch("wiki/idea/index.md", "- [Ghost](../ghost.md) — x\n")
        self.assertEqual(lint.check_index_links({}), 1)
        self.assertTrue(any(e.startswith("wiki/idea/index.md") and "ghost" in e for e in lint.errors))

    def test_a_wikilink_in_a_section_index_is_an_error(self):
        self.touch("wiki/idea/2020/index.md", "- [[alpha]]\n")
        self.assertEqual(lint.check_index_links(self.pages()), 1)

    def test_a_section_folder_is_not_a_stray_but_other_files_in_it_are(self):
        self.index()
        self.touch("wiki/idea/other.md", "x")
        lint.check_wiki_strays()
        self.assertEqual([w for w in lint.warnings if "idea/index.md" in w], [])
        self.assertTrue(any(w.startswith("wiki/idea/other.md") for w in lint.warnings))
        self.touch("wiki/leftover/note.md", "x")
        lint.check_wiki_strays()
        self.assertTrue(any("subfolder in wiki/" in w and "leftover" in w for w in lint.warnings))

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

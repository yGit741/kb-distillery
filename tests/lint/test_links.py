"""Wikilink parsing and bibliography rendering.

Regression for two bugs found together: lint read [[slug\\|label]] as target `slug\\` (false
broken links, and links invisible to the graph), while bibliography tables used a bare | that
split every row. Researcher indexing also left hundreds of dangling [[links]] to uncataloged papers.
"""
import os
import sys
import unittest
from unittest import mock

from kb_distillery.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.core import graph
from kb_distillery.lint import lint
from kb_distillery.ingest import researcher


class LinkRegexTests(unittest.TestCase):
    def test_all_forms_resolve_to_the_bare_slug(self):
        for text in ["[[tensor-rank]]", "[[tensor-rank|Tensor rank]]",
                     "[[tensor-rank\\|Tensor rank]]", "[[tensor-rank#Formal|x]]"]:
            with self.subTest(text=text):
                self.assertEqual(lint.LINK.findall(text), ["tensor-rank"])
                self.assertEqual(graph.LINK.findall(text), ["tensor-rank"])


class TablePipeLintTests(unittest.TestCase):
    def _warnings_for(self, body):
        lint.warnings = []
        lint.check_table_pipes({"p": ("wiki/p.md", {}, body)})
        return lint.warnings

    def test_bare_pipe_in_table_warns(self):
        self.assertEqual(len(self._warnings_for("| a | [[x|Title]] | b |")), 1)

    def test_escaped_pipe_in_table_ok(self):
        self.assertEqual(self._warnings_for("| a | [[x\\|Title]] | b |"), [])

    def test_bare_pipe_outside_table_ok(self):
        self.assertEqual(self._warnings_for("- see [[x|Title]] for more"), [])


class BibliographyRenderTests(unittest.TestCase):
    def test_cataloged_paper_links_with_escaped_pipe(self):
        cell = researcher.bib_title_cell({"slug": "k", "title": "Known"}, {"paper-k"})
        self.assertEqual(cell, "[[paper-k\\|Known]]")
        self.assertEqual(lint.LINK.findall(cell), ["paper-k"])

    def test_uncataloged_paper_links_out_not_in(self):
        cell = researcher.bib_title_cell({"slug": "u", "title": "Elsewhere", "arxiv": "2101.08303"}, set())
        self.assertEqual(cell, "[Elsewhere](https://arxiv.org/abs/2101.08303)")
        self.assertEqual(lint.LINK.findall(cell), [], "must not create a dangling wikilink")

    def test_title_is_one_line_and_pipe_free(self):
        cell = researcher.bib_title_cell({"slug": "u", "title": "On Projection\n$$P | Q$$ Matrices"}, set())
        self.assertNotIn("\n", cell)
        self.assertNotIn("|", cell)


class RelinkTests(unittest.TestCase):
    PAPERS = {
        "1992-influence": {"slug": "1992-influence", "title": "The influence of variables",
                           "url": "https://example.org/p"},
        "1993-no-url": {"slug": "1993-no-url", "title": "No url paper"},
    }

    def test_only_dangling_bibliography_links_change(self):
        text = ("| ⭐ | [[1992-influence\\|The influence of variables]] |\n"
                "| ⭐ | [[1993-no-url|No url paper]] |\n"
                "- [[tensor-rank]] stays · [[q-not-a-paper]] stays")
        new, n = researcher.relink_text(text, self.PAPERS, known={"tensor-rank"})
        self.assertEqual(n, 2)
        self.assertIn("[The influence of variables](https://example.org/p)", new)
        self.assertIn("| ⭐ | No url paper |", new)
        self.assertIn("[[tensor-rank]]", new)
        self.assertIn("[[q-not-a-paper]]", new, "non-bibliography dangling links are not ours to rewrite")

    def test_existing_page_keeps_its_link(self):
        text = "| [[1992-influence\\|The influence of variables]] |"
        new, n = researcher.relink_text(text, self.PAPERS, known={"1992-influence"})
        self.assertEqual((new, n), (text, 0))


if __name__ == "__main__":
    unittest.main()

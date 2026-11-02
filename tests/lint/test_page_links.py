"""lint.check_links: pages link with [Title](slug.md); a wikilink is only legal in ## My notes; a link must resolve."""
import os
import tempfile
import unittest
from unittest import mock

from kb_distillery.lint import lint

FM = "---\ntype: idea\n---\n\n"


def run(pages):
    """(errors, warnings, broken) for {slug: body}."""
    lint.errors, lint.warnings = [], []
    table = {s: (f"wiki/{s}.md", {}, FM + body) for s, body in pages.items()}
    broken = lint.check_links(table)
    return list(lint.errors), list(lint.warnings), broken


class PageLinks(unittest.TestCase):
    def setUp(self):
        self.saved = (lint.errors, lint.warnings)

    def tearDown(self):
        lint.errors, lint.warnings = self.saved

    def test_a_page_link_to_a_page_is_fine(self):
        errs, warns, broken = run({"a": "# A\n\nsee [B](b.md) and [B](b.md#why-it-works)\n", "b": "# B\n\n## Why it works\n"})
        self.assertEqual((errs, warns, broken), ([], [], 0))

    def test_a_new_wikilink_fails(self):
        errs, _w, _b = run({"a": "# A\n\nsee [[b]]\n", "b": "# B\n"})
        self.assertEqual(len(errs), 1)
        self.assertIn("wikilinks live only in ## My notes", errs[0])

    def test_wikilinks_in_my_notes_are_the_users(self):
        errs, warns, _b = run({"a": "# A\n\n## My notes\n[[b]] and [[ghost]]\n", "b": "# B\n"})
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 1)                                  # a dead one only warns, as before
        self.assertIn("ghost", warns[0])

    def test_code_math_comments_and_empty_placeholders_are_not_links(self):
        body = "# A\n\n`[[x]]` $[[1,2],[3,4]]$ <!-- [Title](slug.md) -->\n\n```\n[[y]] [z](nope.md)\n```\n- Concepts: [[]]\n"
        self.assertEqual(run({"a": body}), ([], [], 0))

    def test_a_link_to_no_page_fails(self):
        errs, _w, broken = run({"a": "# A\n\n[Gone](gone.md)\n"})
        self.assertEqual(broken, 1)
        self.assertIn("resolves to no page", errs[0])

    def test_an_unknown_heading_fails(self):
        errs, _w, _b = run({"a": "# A\n\n[B](b.md#nope)\n", "b": "# B\n\n## Real\n"})
        self.assertEqual(len(errs), 1)
        self.assertIn("heading", errs[0])

    def test_a_path_is_not_a_page_link(self):
        errs, _w, _b = run({"a": "# A\n\n[B](wiki/b.md) [B](./b.md)\n", "b": "# B\n"})
        self.assertEqual(len(errs), 2)
        self.assertTrue(all("path-prefixed" in e for e in errs))

    def test_an_excalidraw_drawing_is_not_a_page(self):
        """A drawing's `[[x]]` text element is the plugin's, not a page link: the page loaders never read it."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "wiki", "excalidraw"))
            with open(os.path.join(root, "wiki", "a.md"), "w", encoding="utf-8") as f:
                f.write(FM + "# A\n")
            with open(os.path.join(root, "wiki", "excalidraw", "d.excalidraw.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: excalidraw\n---\n## Text Elements\n[[a]] ^id1\n")
            with mock.patch.object(lint, "ROOT", root):
                pages = lint.load_wiki_pages()
            self.assertEqual(list(pages), ["a"])
            lint.errors, lint.warnings = [], []
            lint.check_links(pages)
            self.assertEqual(lint.errors, [])

    def test_urls_and_raw_images_are_left_alone(self):
        self.assertEqual(run({"a": "# A\n\n[x](https://example.org/a.md) ![i](../raw/img/p.png)\n"}), ([], [], 0))


if __name__ == "__main__":
    unittest.main()

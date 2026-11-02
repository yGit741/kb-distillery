"""`query mocs` lists theme pages with their maturity, read from the page: index rows carry none."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from kb_distillery.search import query


class Mocs(unittest.TestCase):
    def test_maturity_comes_from_the_page_not_the_index_row(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "theme-x.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: topic\nlayer: concept\nmaturity: growing\n---\n\n# X\n")
            index = {"theme-x": {"section": "Topics", "title": "X", "status": "", "summary": "About x"},
                     "idea-y": {"section": "Ideas", "title": "Y", "status": "", "summary": "no"}}
            out = io.StringIO()
            with mock.patch.object(query, "parse_index", lambda: index), \
                    mock.patch.object(query, "wiki_path", lambda s: os.path.join(d, s + ".md")), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(query.cmd_mocs(), 0)
        self.assertIn("[X](theme-x.md)  growing  About x", out.getvalue())
        self.assertNotIn("idea-y", out.getvalue())


if __name__ == "__main__":
    unittest.main()

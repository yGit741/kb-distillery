import os
import sys
import unittest

from kb.services import corpus as cd


class CorpusDataTest(unittest.TestCase):
    def test_columns_per_format(self):
        for fmt in cd.FORMATS:
            keys = [c["key"] for c in cd.columns(fmt)]
            for common in ("path", "disposition", "slug", "year", "sha1"):
                self.assertIn(common, keys)
        self.assertIn("authors", [c["key"] for c in cd.columns("printed-docs")])
        self.assertIn("thread_date", [c["key"] for c in cd.columns("emails")])
        self.assertIn("domain", [c["key"] for c in cd.columns("web-clips")])
        self.assertIn("companion_of", [c["key"] for c in cd.columns("images")])

    def test_path_guard(self):
        for bad in ("raw/inbox/x.pdf", "raw/../backend/src/kb/lint/lint.py", "wiki/a.md", "/etc/passwd", "raw/", "raw/x.pdf", "", None,
                    "raw/printed-docs/../inbox/x.pdf"):
            self.assertIsNone(cd.check_raw_path(bad)[0], bad)
            self.assertIsNotNone(cd.check_raw_path(bad)[1], bad)
        full, err = cd.check_raw_path("raw/printed-docs/2020-x.pdf")
        self.assertIsNone(err)
        self.assertTrue(full.endswith("raw/printed-docs/2020-x.pdf"))

    def test_action_validator(self):
        self.assertIn("unknown action", cd.validate_action("deep-digest", "raw/printed-docs/a.pdf"))
        self.assertIn("unknown action", cd.validate_action("catalog", "raw/printed-docs/a.pdf"))
        self.assertIsNotNone(cd.validate_action("easy-digest", "raw/inbox/a.pdf"))
        self.assertIsNone(cd.validate_action("easy-digest", "raw/printed-docs/a.pdf"))
        self.assertEqual(cd.run_action("full", "raw/printed-docs/a.pdf")[0], None)

    def test_unknown_format(self):
        self.assertIsNone(cd.build_corpus("nope"))
        self.assertIsNone(cd.build_corpus("inbox"))

    def test_corpus_rows(self):
        data = cd.build_corpus("web-clips")
        self.assertEqual(data["count"], len(data["rows"]))
        for r in data["rows"][:5]:
            for c in data["columns"]:
                self.assertIn(c["key"], r)

    def test_preview_refuses_inbox(self):
        self.assertIsNotNone(cd.build_preview("raw/inbox/x")[1])

    def test_citations_missing_or_shaped(self):
        c = cd.build_citations()
        self.assertIn("nodes", c)
        self.assertIn("links", c)


if __name__ == "__main__":
    unittest.main()

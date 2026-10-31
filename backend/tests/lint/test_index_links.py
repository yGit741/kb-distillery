#!/usr/bin/env python3
"""index.md is generated: its Meta rows exist only for pages that exist, and lint checks its links."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb.lint import lint


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

    def touch(self, rel):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("x")

    def index(self):
        lint.write_index({}, quiet=True)
        return open(os.path.join(self.root, "index.md"), encoding="utf-8").read()

    def test_no_meta_rows_when_no_meta_pages_exist(self):
        text = self.index()
        for slug in ("[[thesis]]", "[[log]]", "[[AGENTS]]", "## Meta"):
            self.assertNotIn(slug, text)
        self.assertEqual(lint.check_index_links({}), 0)

    def test_meta_rows_only_for_pages_that_exist(self):
        self.touch("meta/log.md")
        text = self.index()
        self.assertIn("[[log]]", text)
        self.assertNotIn("[[AGENTS]]", text)
        self.assertEqual(lint.check_index_links({}), 0)

    def test_thesis_in_meta_dir_is_listed(self):
        self.touch("meta/thesis.md")
        self.assertIn("[[thesis]]", self.index())

    def test_a_dangling_link_in_index_is_an_error(self):
        with open(os.path.join(self.root, "index.md"), "w") as f:
            f.write("| [[ghost]] | x |\n")
        self.assertEqual(lint.check_index_links({}), 1)
        self.assertTrue(any("ghost" in e for e in lint.errors))


if __name__ == "__main__":
    unittest.main()

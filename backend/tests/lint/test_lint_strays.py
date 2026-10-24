#!/usr/bin/env python3
"""Stray-artifact warnings of backend/src/kb/lint/lint.py: wiki/ subfolders and non-.md files, vault-root leftovers."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb.lint import lint


class Strays(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-strays-")
        os.makedirs(os.path.join(self.root, "wiki"))
        self.patches = [mock.patch.object(lint, "ROOT", self.root),
                        mock.patch.object(lint, "warnings", []), mock.patch.object(lint, "errors", [])]
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

    def test_wiki_clean(self):
        self.touch("wiki/idea-a.md")
        lint.check_wiki_strays()
        self.assertEqual(lint.warnings, [])

    def test_wiki_strays_warn_never_error(self):
        self.touch("wiki/excalidraw/Drawing.excalidraw.md")
        self.touch("wiki/picture.png")
        self.touch("wiki/Top.excalidraw.md")
        lint.check_wiki_strays()
        text = "\n".join(lint.warnings)
        self.assertIn("wiki/excalidraw: subfolder", text)
        self.assertIn("wiki/excalidraw/Drawing.excalidraw.md: excalidraw", text)
        self.assertIn("wiki/Top.excalidraw.md: excalidraw", text)
        self.assertIn("wiki/picture.png: non-markdown", text)
        self.assertEqual(lint.errors, [])

    def test_root_strays(self):
        self.touch("notes.txt")
        self.touch("README.md")
        os.makedirs(os.path.join(self.root, "junk"))
        os.makedirs(os.path.join(self.root, ".hidden"))
        with mock.patch.object(lint, "_git_ignored", return_value=set()):
            lint.check_root()
        text = "\n".join(lint.warnings)
        self.assertIn("notes.txt", text)
        self.assertIn("junk/", text)
        self.assertNotIn("README.md", text)
        self.assertNotIn(".hidden", text)
        self.assertEqual(lint.errors, [])

    def test_root_ignored_entries_do_not_warn(self):
        self.touch("scratch.txt")
        with mock.patch.object(lint, "_git_ignored", return_value={"scratch.txt"}):
            lint.check_root()
        self.assertEqual(lint.warnings, [])


if __name__ == "__main__":
    unittest.main()

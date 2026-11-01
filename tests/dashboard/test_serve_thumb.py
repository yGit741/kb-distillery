"""Dashboard raw-file endpoints only ever read inside raw/, and thumbnails render PDFs."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery.dashboard import serve


class RawPathTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "raw", "printed-docs"))
        os.makedirs(os.path.join(self.root, "meta"))
        with open(os.path.join(self.root, "meta", "secret.py"), "w") as f:
            f.write("x")
        self.addCleanup(shutil.rmtree, self.root)
        patcher = mock.patch.object(serve, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_guard(self):
        self.assertIsNone(serve.safe_raw_path("meta/secret.py"))
        self.assertIsNone(serve.safe_raw_path("raw/../meta/secret.py"))
        self.assertIsNone(serve.safe_raw_path("raw/printed-docs/missing.pdf"))
        self.assertIsNone(serve.safe_raw_path(""))

    def test_symlink_escape(self):
        link = os.path.join(self.root, "raw", "printed-docs", "evil.pdf")
        os.symlink(os.path.join(self.root, "meta", "secret.py"), link)
        self.assertIsNone(serve.safe_raw_path("raw/printed-docs/evil.pdf"))

    def test_pdf_thumbnail(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("pymupdf not installed")
        path = os.path.join(self.root, "raw", "printed-docs", "2000-x.pdf")
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "hello")
        doc.save(path)
        full = serve.safe_raw_path("raw/printed-docs/2000-x.pdf")
        self.assertEqual(full, os.path.realpath(path))
        png = serve.thumbnail_png(full)
        self.assertTrue(png.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()

"""kb_distillery.storage.raw: raw sources by logical key through the current kb's connector."""
import os
import unittest
import uuid

from kb_distillery import paths
from kb_distillery.storage import NotFound, StorageError, raw


class RawFacade(unittest.TestCase):
    def setUp(self):
        raw.reset()
        self.key = f"raw/web-clips/facade-{uuid.uuid4().hex[:8]}.md"
        self.addCleanup(lambda: os.path.exists(self.full) and os.remove(self.full))
        self.full = os.path.join(paths.ROOT, *self.key.split("/"))

    def test_put_then_read_in_every_shape(self):
        raw.put(self.key, "héllo\n".encode())
        self.assertTrue(raw.exists(self.key))
        self.assertEqual(raw.read_bytes(self.key), "héllo\n".encode())
        self.assertEqual(raw.read_text(self.key), "héllo\n")
        self.assertEqual(raw.info(self.key).size, len("héllo\n".encode()))
        self.assertIn(self.key, raw.list("raw/web-clips/facade-"))

    def test_path_is_the_file_in_the_kb(self):
        raw.put(self.key, b"x")
        self.assertEqual(raw.path(self.key), self.full)

    def test_missing_and_invalid_keys(self):
        self.assertFalse(raw.exists("raw/web-clips/does-not-exist.md"))
        self.assertFalse(raw.exists("../outside.md"))                     # an invalid key names nothing
        with self.assertRaises(NotFound):
            raw.read_bytes("raw/web-clips/does-not-exist.md")
        with self.assertRaises(StorageError):
            raw.read_bytes("../outside.md")

    def test_is_raw_key_is_the_check_serving_code_runs_first(self):
        self.assertTrue(raw.is_raw_key("raw/pdf/a.pdf"))
        for bad in ("meta/x.tsv", "raw", "/raw/a.pdf", "raw/../meta/x", "raw//a", "", None, 5):
            with self.subTest(bad=bad):
                self.assertFalse(raw.is_raw_key(bad))

    def test_raw_is_immutable_through_the_facade_too(self):
        raw.put(self.key, b"one")
        with self.assertRaises(StorageError):
            raw.put(self.key, b"two")


if __name__ == "__main__":
    unittest.main()

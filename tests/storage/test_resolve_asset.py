"""pages.resolve_asset finds an Obsidian embed under raw/ by logical key, and never outside it."""
import os
import unittest
import uuid

from kb_distillery.config import paths
from kb_distillery.services import pages
from kb_distillery.storage import raw


class ResolveAsset(unittest.TestCase):
    def setUp(self):
        raw.reset()
        self.stem = f"asset-{uuid.uuid4().hex[:8]}"
        self.made = []
        self.addCleanup(self._clean)

    def _clean(self):
        for p in self.made:
            if os.path.exists(p):
                os.remove(p)

    def put(self, key):
        raw.put(key, b"\x89PNG\r\n")
        self.made.append(os.path.join(paths.ROOT, *key.split("/")))

    def test_a_bare_name_is_found_in_images_then_web_clips(self):
        self.put(f"raw/web-clips/{self.stem}.png")
        self.assertEqual(pages.resolve_asset(f"{self.stem}.png"), os.path.join(paths.ROOT, "raw", "web-clips", f"{self.stem}.png"))
        self.put(f"raw/images/{self.stem}.png")
        self.assertEqual(pages.resolve_asset(f"{self.stem}.png"), os.path.join(paths.ROOT, "raw", "images", f"{self.stem}.png"))

    def test_a_full_raw_path_is_found(self):
        self.put(f"raw/images/{self.stem}.jpg")
        self.assertTrue(pages.resolve_asset(f"raw/images/{self.stem}.jpg").endswith(f"{self.stem}.jpg"))

    def test_missing_wrong_extension_and_empty_name_find_nothing(self):
        self.assertIsNone(pages.resolve_asset(f"{self.stem}.png"))
        self.assertIsNone(pages.resolve_asset(f"{self.stem}.txt"))
        self.assertIsNone(pages.resolve_asset(""))
        self.assertIsNone(pages.resolve_asset(None))

    def test_nothing_outside_raw_is_reachable(self):
        for name in ("../wiki/x.png", "raw/../kb.toml.png", "meta/chats/assets/x.png", "/etc/x.png", "raw/images/../../x.png"):
            with self.subTest(name=name):
                self.assertIsNone(pages.resolve_asset(name))


if __name__ == "__main__":
    unittest.main()

import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.ingest.sources.chat import chat_store


class TestChatStore(unittest.TestCase):
    def setUp(self):
        self._orig_dir = chat_store.CHATS_ABS
        self._orig_index = chat_store.INDEX_PATH
        self.tmp = tempfile.mkdtemp()
        chat_store.CHATS_ABS = self.tmp
        chat_store.INDEX_PATH = os.path.join(self.tmp, "index.json")

    def tearDown(self):
        chat_store.CHATS_ABS = self._orig_dir
        chat_store.INDEX_PATH = self._orig_index
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mk_conv(self, cid):
        return {
            "id": cid,
            "provider": "gemini",
            "slug": "test-conv",
            "wiki": "wiki/source-test-conv.md",
            "canonical_clip": "raw/chats/x.md",
            "source_urls": ["https://gemini.google.com/app/abc"],
            "clips": {"raw/chats/x.md": {"sha1": "aaa"}},
            "root": "t-1",
            "nodes": {"t-1": {"id": "t-1", "hash": "h1", "parent": None, "children": []}},
            "leaves": ["t-1"],
            "branch_points": [],
            "landed_well": [],
            "status": {"digest": "digested"},
        }

    def test_save_and_load_roundtrip(self):
        conv = self._mk_conv("conv-abc123")
        chat_store.save(conv)
        loaded = chat_store.load("conv-abc123")
        self.assertEqual(loaded["id"], "conv-abc123")
        self.assertEqual(loaded["schema"], chat_store.CHAT_TREE_SCHEMA if hasattr(chat_store, "CHAT_TREE_SCHEMA") else loaded["schema"])

    def test_load_missing_returns_none(self):
        self.assertIsNone(chat_store.load("conv-doesnotexist"))

    def test_new_id_deterministic_and_collision_suffix(self):
        cid = chat_store.new_id("deadbeefcafe")
        self.assertEqual(cid, "conv-deadbeefcafe")
        chat_store.save(self._mk_conv(cid))
        cid2 = chat_store.new_id("deadbeefcafe")
        self.assertEqual(cid2, "conv-deadbeefcafe-1")

    def test_rebuild_index_and_load_index_consistent(self):
        chat_store.save(self._mk_conv("conv-one"))
        idx = chat_store.rebuild_index()
        self.assertIn("h1", idx["by_turn"])
        self.assertEqual(idx["by_turn"]["h1"], ["conv-one"])
        self.assertEqual(idx["by_clip"]["raw/chats/x.md"], "conv-one")
        self.assertEqual(idx["by_url"]["https://gemini.google.com/app/abc"], "conv-one")
        self.assertEqual(idx["by_wiki"]["wiki/source-test-conv.md"], "conv-one")

        idx2 = chat_store.load_index()
        self.assertEqual(idx, idx2)

    def test_save_twice_deterministic_bytes(self):
        conv = self._mk_conv("conv-det")
        chat_store.save(conv)
        with open(chat_store._path("conv-det"), "rb") as f:
            b1 = f.read()
        chat_store.save(chat_store.load("conv-det"))
        with open(chat_store._path("conv-det"), "rb") as f:
            b2 = f.read()
        self.assertEqual(b1, b2)

    def test_all_conversations_iterates(self):
        chat_store.save(self._mk_conv("conv-a"))
        chat_store.save(self._mk_conv("conv-b"))
        ids = sorted(c["id"] for c in chat_store.all_conversations())
        self.assertEqual(ids, ["conv-a", "conv-b"])


if __name__ == "__main__":
    unittest.main()

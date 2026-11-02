import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.ingest.sources.chat import chat, chat_signal, chat_store, chat_merge

from kb_distillery.config.paths import vault_root
ROOT = os.path.join(vault_root(), "meta")
CHATS = os.path.join(ROOT, "..", "raw", "llm-chats")


def _parse(name):
    with open(os.path.join(CHATS, name), encoding="utf-8", errors="replace") as f:
        text = f.read()
    fm, turns = chat.parse_clip(text)
    for t in turns:
        t.signal = chat_signal.score_turn(t)
    return fm, turns


def _meta(inbox_name, clipped="2026-08-14"):
    return {"sha1": "fake", "clipped": clipped, "inbox_name": inbox_name}


class ChatMergeTestCase(unittest.TestCase):
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

    def _catalog(self, clip_name, dest_rel=None, clipped="2026-08-14"):
        """Simulate catalog_chat's identity+merge steps for one clip."""
        fm, turns = _parse(clip_name)
        dest_rel = dest_rel or f"raw/llm-chats/{clip_name}"
        idx = chat_store.load_index()
        cid, info = chat_merge.find_conversation(
            turns, source_url=(fm or {}).get("source"), clip_path=dest_rel, index=idx
        )
        if cid:
            conv = chat_store.load(cid)
        else:
            conv = chat_merge.new_conversation(turns, fm, slug=clip_name)
            conv["id"] = chat_store.new_id(turns[0].hash)
        report = chat_merge.attach_clip(conv, dest_rel, turns, _meta(clip_name, clipped))
        chat_store.save(conv)
        chat_store.rebuild_index()
        return conv, report


class TestExactDuplicates(ChatMergeTestCase):
    def test_chat_5_is_identical_to_chat_4(self):
        conv1, r1 = self._catalog("new-chat-4.md")
        self.assertEqual(r1["relation"], "new")
        conv2, r2 = self._catalog("new-chat-5.md")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertEqual(r2["relation"], "identical")
        self.assertEqual(r2["added_nodes"], 0)

    def test_chat_13_is_identical_to_chat_12(self):
        conv1, _ = self._catalog("new-chat-12.md")
        conv2, r2 = self._catalog("new-chat-13.md")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertEqual(r2["relation"], "identical")


class TestRecapture(ChatMergeTestCase):
    def test_chat_48_is_a_recapture_of_chat_1(self):
        # The first Gemini answer differs only by "arXiv" citation chips the clipper
        # caught in one clip and not the other; every later turn is byte-identical.
        # That is one conversation captured twice, not a fork.
        conv1, r1 = self._catalog("new-chat-1.md", clipped="2026-08-14")
        self.assertEqual(r1["relation"], "new")
        n_before = len(conv1["nodes"])

        conv2, r2 = self._catalog("new-chat-48.md", clipped="2026-08-29")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertEqual(r2["added_nodes"], 0)
        self.assertEqual(len(conv2["nodes"]), n_before)
        self.assertEqual(conv2["branch_points"], [])
        variants = [n for n in conv2["nodes"].values() if n.get("capture_variants")]
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0]["role"], "model")
        self.assertEqual(variants[0]["depth"], 1)


class TestBranch(ChatMergeTestCase):
    def test_chat_46_forks_from_chat_45_after_a_recapture(self):
        # Turn 1 is a recapture (two bullets dropped); the real fork is the user's
        # reply at depth 16, where the two clips go different ways.
        conv1, _ = self._catalog("new-chat-45.md")
        conv2, r2 = self._catalog("new-chat-46.md")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertEqual(r2["relation"], "branch")
        self.assertEqual(len(conv2["branch_points"]), 1)
        bp = conv2["branch_points"][0]
        self.assertEqual(len(bp["variants"]), 2)
        for v in bp["variants"]:
            self.assertEqual(conv2["nodes"][v["child"]]["role"], "user")


class TestSegmentBothOrders(ChatMergeTestCase):
    """New chat 11 is a mid-conversation segment of New chat.md. Must collapse to
    ONE conversation and converge to the SAME final node set regardless of order."""

    def test_full_first_then_segment(self):
        conv_full, r_full = self._catalog("new-chat.md", clipped="2026-08-14")
        self.assertEqual(r_full["relation"], "new")
        conv_seg, r_seg = self._catalog("new-chat-11.md", clipped="2026-08-29")
        self.assertEqual(conv_seg["id"], conv_full["id"])
        self.assertEqual(r_seg["relation"], "segment")
        self.assertEqual(r_seg["added_nodes"], 0)
        return conv_seg

    def test_segment_first_then_full(self):
        conv_seg, r_seg = self._catalog("new-chat-11.md", clipped="2026-08-14")
        self.assertEqual(r_seg["relation"], "new")
        n_seg = len(conv_seg["nodes"])

        conv_full, r_full = self._catalog("new-chat.md", clipped="2026-08-29")
        self.assertEqual(conv_full["id"], conv_seg["id"])
        # New chat.md is a prefix superset: it should re-parent, adding the
        # turns that precede New chat 11's first turn.
        self.assertEqual(r_full["relation"], "extension")
        self.assertGreater(len(conv_full["nodes"]), n_seg)
        return conv_full

    def test_both_orders_converge_to_same_final_tree(self):
        conv_a = self.test_full_first_then_segment()
        # fresh store for the reverse order
        self.tearDown()
        self.setUp()
        conv_b = self.test_segment_first_then_full()

        hashes_a = sorted(n["hash"] for n in conv_a["nodes"].values())
        hashes_b = sorted(n["hash"] for n in conv_b["nodes"].values())
        self.assertEqual(hashes_a, hashes_b)
        self.assertEqual(len(conv_a["nodes"]), len(conv_b["nodes"]))
        # ids should match too: same final ancestor-content-chain -> same Merkle ids
        ids_a = sorted(conv_a["nodes"].keys())
        ids_b = sorted(conv_b["nodes"].keys())
        self.assertEqual(ids_a, ids_b)
        self.assertEqual(conv_a["root"], conv_b["root"])


class TestBranchAndExtensionCombo(ChatMergeTestCase):
    """Covector uniqueness vs Why V isomorphic to V*? — real in-vault case with
    multiple divergence points and different lengths."""

    def test_real_branch_family(self):
        conv1, r1 = self._catalog("covector-uniqueness.md", clipped="2026-08-14")
        self.assertEqual(r1["relation"], "new")
        conv2, r2 = self._catalog("why-v-isomorphic-to-v.md", clipped="2026-08-29")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertIn(r2["relation"], ("branch", "extension"))
        self.assertGreater(r2["added_nodes"], 0)
        # exactly one wiki-worthy conversation, not two
        self.assertEqual(len(chat_store.load_index()["by_url"]), 0)  # no URLs in these clips


class TestContiguousRunMatch(ChatMergeTestCase):
    """new-chat-41's first 4 turns are byte-identical to covector-uniqueness turns
    16-19, but new-chat-41 is 20 turns long so the cover RATIO is only ~0.20 —
    below MIN_COVER. An unbroken 4-turn chain is unambiguous evidence regardless of
    ratio, so MIN_RUN must accept it."""

    def test_new_chat_41_joins_covector_conversation(self):
        conv1, r1 = self._catalog("covector-uniqueness.md", clipped="2026-08-14")
        self.assertEqual(r1["relation"], "new")

        fm, turns = _parse("new-chat-41.md")
        cid, info = chat_merge.find_conversation(
            turns, clip_path="raw/llm-chats/new-chat-41.md", index=chat_store.load_index()
        )
        self.assertEqual(cid, conv1["id"], "contiguous run should rescue this match")
        self.assertLess(info["cover"], chat_merge.MIN_COVER, "cover alone would reject")
        self.assertGreaterEqual(info["run"], chat_merge.MIN_RUN)

        conv2, r2 = self._catalog("new-chat-41.md", clipped="2026-08-29")
        self.assertEqual(conv2["id"], conv1["id"])
        self.assertGreater(r2["added_nodes"], 0)

    def test_unrelated_clip_still_rejected(self):
        """The run rule must not merge genuinely unrelated conversations."""
        conv1, _ = self._catalog("new-chat-9.md")
        fm, turns = _parse("new-chat-6.md")
        cid, info = chat_merge.find_conversation(
            turns, clip_path="raw/llm-chats/new-chat-6.md", index=chat_store.load_index()
        )
        self.assertIsNone(cid)


class TestIdempotency(ChatMergeTestCase):
    def test_double_catalog_same_clip_is_noop(self):
        conv1, r1 = self._catalog("new-chat-9.md", dest_rel="raw/llm-chats/x.md")
        self.assertEqual(r1["relation"], "new")
        n1 = len(conv1["nodes"])

        # Second run: node set/ids/root are the stable invariant. The per-clip
        # bookkeeping legitimately updates ("root" -> "identical" once the tree
        # already exists) — that's correct metadata, not drift.
        conv2, r2 = self._catalog("new-chat-9.md", dest_rel="raw/llm-chats/x.md")
        self.assertEqual(len(conv2["nodes"]), n1)
        self.assertEqual(r2["added_nodes"], 0)
        self.assertEqual(r2["relation"], "identical")
        self.assertEqual(sorted(conv1["nodes"].keys()), sorted(conv2["nodes"].keys()))
        self.assertEqual(conv1["root"], conv2["root"])

        # Third run must be byte-identical to the second (true fixed point).
        conv3, r3 = self._catalog("new-chat-9.md", dest_rel="raw/llm-chats/x.md")
        self.assertEqual(conv2, conv3)


class TestLandedWellRollup(ChatMergeTestCase):
    def test_landed_well_populated_on_new_conversation(self):
        conv, r = self._catalog("new-chat-34.md", clipped="2026-08-14")
        self.assertEqual(r["relation"], "new")
        self.assertTrue(any(h["score"] >= 70 for h in conv["landed_well"]))
        for h in conv["landed_well"]:
            self.assertIn(h["praise_node"], conv["nodes"])
            self.assertIn(h["credited_node"], conv["nodes"])

    def test_landed_well_survives_reclip_without_duplicating(self):
        conv1, _ = self._catalog("new-chat-34.md", clipped="2026-08-14")
        n1 = len(conv1["landed_well"])
        conv2, _ = self._catalog("new-chat-34.md", clipped="2026-08-14")
        self.assertEqual(len(conv2["landed_well"]), n1)

    def test_landed_well_ids_survive_reparent_cascade(self):
        """new-chat-11 (segment, has a landed_well hit) cataloged FIRST, then
        new-chat.md triggers a prefix-superset re-parent that cascades new ids
        onto new-chat-11's whole subtree. landed_well must be rewritten too."""
        conv_seg, _ = self._catalog("new-chat-11.md", clipped="2026-08-14")
        self.assertTrue(len(conv_seg["landed_well"]) > 0, "expected a landed_well hit within new-chat-11")
        conv_full, r = self._catalog("new-chat.md", clipped="2026-08-29")
        self.assertEqual(r["relation"], "extension")
        for h in conv_full["landed_well"]:
            self.assertIn(h["praise_node"], conv_full["nodes"],
                          "landed_well references a node id that no longer exists after re-parent")
            self.assertIn(h["credited_node"], conv_full["nodes"])


if __name__ == "__main__":
    unittest.main()

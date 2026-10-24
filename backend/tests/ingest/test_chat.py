import os
import sys
import unittest


from kb.ingest import chat
from kb.ingest import chat_signal

from kb.paths import vault_root
ROOT = vault_root()
CHATS = os.path.join(ROOT, "raw", "chats")
INBOX = os.path.join(ROOT, "raw", "inbox")


def _read(name, base=CHATS):
    # Fixtures are live vault files; inbox ones disappear once triaged.
    if not os.path.exists(os.path.join(base, name)):
        raise unittest.SkipTest(f"fixture gone: {name}")
    with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
        return f.read()


class TestIsChat(unittest.TestCase):
    def test_gemini_clip_detected(self):
        self.assertTrue(chat.is_chat(_read("new-chat-1.md")))

    def test_hebrew_web_clip_not_chat(self):
        text = _read("אז מה זו אלגברה לינארית?.md", base=INBOX)
        self.assertFalse(chat.is_chat(text))

    def test_plain_prose_not_chat(self):
        self.assertFalse(chat.is_chat("just some prose\nwith **bold** text\nno markers"))

    def test_marker_inside_fence_not_boundary(self):
        text = "```\n**You**\n**Gemini**\n```\nplain text only"
        self.assertFalse(chat.is_chat(text))


class TestParseTurns(unittest.TestCase):
    def test_new_chat_1_turn_count_and_roles(self):
        text = _read("new-chat-1.md")
        fm, turns = chat.parse_clip(text)
        self.assertEqual(len(turns), 14)
        roles = [t.role for t in turns]
        self.assertEqual(roles, ["user", "model"] * 7)
        self.assertEqual(fm["source"], "https://gemini.google.com/app/cdf6fa71d9e94ab2")

    def test_new_chat_43_html_block_stays_in_one_turn(self):
        text = _read("new-chat-43.md")
        fm, turns = chat.parse_clip(text)
        # the interactive covector demo must not be split across turn boundaries
        viz_turns = [t for t in turns if t.fences and any(f.looks_runnable for f in t.fences)]
        self.assertEqual(len(viz_turns), 1)
        fence = [f for f in viz_turns[0].fences if f.looks_runnable][0]
        self.assertGreater(fence.end_line - fence.start_line, 100)

    def test_no_frontmatter_clip_still_parses(self):
        text = _read("new-chat-9.md")
        fm, turns = chat.parse_clip(text)
        self.assertIsNone(fm)
        self.assertGreater(len(turns), 0)

    def test_double_catalog_idempotent_hash(self):
        text = _read("new-chat-9.md")
        _, turns1 = chat.parse_clip(text)
        _, turns2 = chat.parse_clip(text)
        self.assertEqual([t.hash for t in turns1], [t.hash for t in turns2])

    def test_exact_duplicate_pair_same_hashes(self):
        _, turns4 = chat.parse_clip(_read("new-chat-4.md"))
        _, turns5 = chat.parse_clip(_read("new-chat-5.md"))
        self.assertEqual([t.hash for t in turns4], [t.hash for t in turns5])

    def test_branch_pair_diverges_at_one_point(self):
        _, turns1 = chat.parse_clip(_read("new-chat-1.md"))
        _, turns48 = chat.parse_clip(_read("new-chat-48.md"))
        self.assertEqual(len(turns1), len(turns48))
        diffs = [i for i in range(len(turns1)) if turns1[i].hash != turns48[i].hash]
        self.assertEqual(diffs, [1])  # the second turn (first Gemini answer) differs

    def test_segment_new_chat_11_is_suffix_of_new_chat_dot_md(self):
        _, turns_full = chat.parse_clip(_read("new-chat.md"))
        _, turns_11 = chat.parse_clip(_read("new-chat-11.md"))
        full_hashes = [t.hash for t in turns_full]
        seg_hashes = [t.hash for t in turns_11]
        # New chat 11 should appear as a contiguous run inside New chat.md
        found = any(
            full_hashes[i:i + len(seg_hashes)] == seg_hashes
            for i in range(len(full_hashes) - len(seg_hashes) + 1)
        )
        self.assertTrue(found)

    def test_covector_vs_why_v_isomorphic_branch(self):
        _, turns_cov = chat.parse_clip(_read("covector-uniqueness.md"))
        _, turns_v = chat.parse_clip(_read("why-v-isomorphic-to-v.md"))
        common_prefix = 0
        for a, b in zip(turns_cov, turns_v):
            if a.hash != b.hash:
                break
            common_prefix += 1
        self.assertGreater(common_prefix, 5)
        self.assertLess(common_prefix, min(len(turns_cov), len(turns_v)))


class TestObsGood(unittest.TestCase):
    def test_marker_stripped_before_hash(self):
        class FakeTurn:
            text = "this is a great answer"
            fences = []
        t1 = FakeTurn()
        t2 = FakeTurn()
        t2.text = "this is a great answer @obs-good"
        h1 = chat.turn_hash(chat.normalize_turn(t1))
        h2 = chat.turn_hash(chat.normalize_turn(t2))
        self.assertEqual(h1, h2)

    def test_explicit_signal_detected(self):
        class FakeTurn:
            text = "this explanation @obs-good really landed"
        sig = chat_signal.score_turn(FakeTurn())
        self.assertTrue(sig["explicit"])
        self.assertEqual(sig["score"], 100)


class TestModelTurnsNotScored(unittest.TestCase):
    def test_model_stock_enthusiasm_scores_zero(self):
        class T:
            role = "model"
            text = "Excellent question! That's a perfect way to see it."
        self.assertEqual(chat_signal.score_turn(T())["score"], 0)

    def test_same_text_from_user_does_score(self):
        class T:
            role = "user"
            text = "Excellent question! That's a perfect way to see it."
        self.assertGreater(chat_signal.score_turn(T())["score"], 0)

    def test_obs_good_on_model_turn_still_ignored(self):
        class T:
            role = "model"
            text = "here you go @obs-good"
        self.assertFalse(chat_signal.score_turn(T())["explicit"])

    def test_no_model_turn_in_corpus_carries_signal(self):
        _, turns = chat.parse_clip(_read("new-chat-44.md"))
        for t in turns:
            t.signal = chat_signal.score_turn(t)
        self.assertTrue(all(t.signal["score"] == 0 for t in turns if t.role == "model"))


class TestLandedWell(unittest.TestCase):
    def test_new_chat_34_credits_preceding_model_turn(self):
        text = _read("new-chat-34.md")
        _, turns = chat.parse_clip(text)
        from kb.ingest import chat_signal as cs
        for t in turns:
            t.signal = cs.score_turn(t)
        hits = cs.landed_well(turns)
        # "Oh, it is so beautifull..." is this clip's ROOT turn (no preceding model
        # turn in this clip — it's a mid-conversation segment), so it can't be credited
        # here; it will be once merged into the fuller tree. "let it sink" (turn 4,
        # preceded by a real model turn) is what this single-clip parse can credit.
        self.assertTrue(any(h["score"] >= 70 for h in hits))


if __name__ == "__main__":
    unittest.main()

"""chat-digest: one ai-chat page per conversation, re-runnable, safe on bad replies. No real LLM (llm.run is faked)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb_distillery import llm
from kb_distillery.ingest.sources.chat import chat_build, chat_digest as cd
from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.vault import summary as summary_lib

TURNS_A = [("You", "What is a dual space?"), ("Gemini", "The space of linear functionals on V."),
           ("You", "Why is V isomorphic to V**?"), ("Gemini", "The evaluation map is a natural isomorphism.")]


def clip(turns, title="New chat", created="2026-03-01", source="https://gemini.google.com/app/abc"):
    body = "\n\n".join(f"**{who}**\n\n{text}" for who, text in turns)
    return f"---\ntitle: \"{title}\"\nsource: {source}\ncreated: {created}\n---\n\n{body}\n"


def reply(**over):
    vals = {"title": "Dual spaces and the double dual", "slug": "dual-spaces-double-dual",
            "description": "A conversation on dual spaces: linear functionals, and why the evaluation map makes a "
                           "finite-dimensional space naturally isomorphic to its double dual.",
            "scope": "Dual spaces, linear functionals, the double dual and the evaluation map.",
            "positions": ["Asked what a dual space is.", "Asked why V is isomorphic to its double dual."],
            "suggestions": ["The evaluation map is a natural isomorphism in finite dimension."],
            "takeaways": []}
    vals.update(over)
    return json.dumps(vals)


class FakeLLM:
    """Stands in for llm.run: replies taken in order from a list (text, or an error with `error=`)."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, reqs, backend=None, **kw):
        self.calls.append(reqs)
        out = []
        for r in reqs:
            nxt = self.replies.pop(0)
            if isinstance(nxt, dict):
                out.append(llm.Result(id=r.id, error=nxt["error"], backend="batch"))
            else:
                out.append(llm.Result(id=r.id, text=nxt, usd=0.01, backend="batch", model="claude-sonnet-5-5"))
        return out


class ChatDigestCase(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="chat-digest-"))
        for d in ("raw/llm-chats", "wiki", "meta"):
            os.makedirs(os.path.join(self.root, d))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def page(self, slug):
        with open(os.path.join(self.root, "wiki", f"{slug}.md"), encoding="utf-8") as f:
            text = f.read()
        return text, parse_frontmatter(text)

    def corpus(self, rows):
        lines = ["# generated", "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes"]
        lines += [f"{p}\tx\tchat\t{d}\t\t\t" for p, d in rows]
        self.put("meta/corpus.tsv", "\n".join(lines) + "\n")

    def run_cd(self, fake, **kw):
        with mock.patch.object(llm, "run", fake):
            return cd.run(root=self.root, lint=False, **kw)


class TestPlan(ChatDigestCase):
    def test_reclips_are_one_conversation_and_one_new_page(self):
        self.put("raw/llm-chats/new-chat-1.md", clip(TURNS_A[:2]))
        self.put("raw/llm-chats/new-chat-2.md", clip(TURNS_A, created="2026-03-02"))
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        items = cd.plan(convs, self.root)
        self.assertEqual([i["action"] for i in items], ["new"])
        self.assertEqual(items[0]["clips"], ["raw/llm-chats/new-chat-1.md", "raw/llm-chats/new-chat-2.md"])

    def test_clips_merge_oldest_first_by_created(self):
        self.assertEqual(chat_build.clip_date({"created": "2026-03-02"}), "2026-03-02")
        self.assertEqual(chat_build.clip_date({"clipped": "2026-01-01", "created": "2026-03-02"}), "2026-01-01")
        self.assertEqual(chat_build.clip_date({}), "")

    def test_existing_page_gains_the_missing_clip(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/b.md", clip(TURNS_A, created="2026-03-05"))
        self.put("wiki/chat-dual.md", "---\ntype: ai-chat\nlegacy: true\nraw: raw/llm-chats/a.md\n---\n\n# Dual\n")
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        [item] = cd.plan(convs, self.root)
        self.assertEqual((item["action"], item["page"], item["missing"]), ("attach", "chat-dual", ["raw/llm-chats/b.md"]))

    def test_an_uncited_copy_of_a_cited_clip_becomes_its_dupe(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/z.md", clip(TURNS_A))          # sorts last: the canonical clip on a tie
        self.put("wiki/chat-dual.md", "---\ntype: ai-chat\nlegacy: true\nraw: raw/llm-chats/a.md\n---\n\n# Dual\n")
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        [item] = cd.plan(convs, self.root)
        self.assertEqual((item["action"], item["dupes"]), ("done", {"raw/llm-chats/z.md": "raw/llm-chats/a.md"}))

    def test_two_pages_on_one_conversation_is_a_conflict(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A[:2]))
        self.put("raw/llm-chats/b.md", clip(TURNS_A, created="2026-03-05"))
        self.put("wiki/chat-one.md", "---\ntype: ai-chat\nraw: raw/llm-chats/a.md\n---\n\n# One\n")
        self.put("wiki/chat-two.md", "---\ntype: ai-chat\nraw: raw/llm-chats/b.md\n---\n\n# Two\n")
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        [item] = cd.plan(convs, self.root)
        self.assertEqual(item["action"], "conflict")
        self.assertIn("chat-one", item["why"])

    def test_skip_and_dupe_clips_are_never_cited(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/b.md", clip(TURNS_A, created="2026-03-05"))
        self.put("raw/llm-chats/c.md", clip([("You", "Unrelated?"), ("Gemini", "Yes.")]))
        self.corpus([("raw/llm-chats/a.md", "queued"), ("raw/llm-chats/b.md", "dupe:raw/llm-chats/a.md"),
                     ("raw/llm-chats/c.md", "skip")])
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        actions = {tuple(i["clips"]): i["action"] for i in cd.plan(convs, self.root)}
        self.assertEqual(actions, {("raw/llm-chats/a.md",): "new", (): "skip"})

    def test_only_and_limit(self):
        items = [{"conv": "conv-1", "page": None, "clips": ["raw/llm-chats/a.md"], "action": "new"},
                 {"conv": "conv-2", "page": None, "clips": ["raw/llm-chats/b.md"], "action": "new"},
                 {"conv": "conv-3", "page": "chat-x", "clips": ["raw/llm-chats/c.md"], "action": "attach"}]
        self.assertEqual([i["conv"] for i in cd.select(items, only=["raw/llm-chats/b.md"])], ["conv-2"])
        self.assertEqual([i["conv"] for i in cd.select(items, only=["chat-x"])], ["conv-3"])
        self.assertEqual([i["conv"] for i in cd.select(items, limit=1)], ["conv-1", "conv-3"])


class TestRun(ChatDigestCase):
    def test_writes_one_page_with_tree_and_every_clip_then_is_idempotent(self):
        self.put("raw/llm-chats/new-chat-1.md", clip(TURNS_A[:2]))
        self.put("raw/llm-chats/new-chat-2.md", clip(TURNS_A, created="2026-03-02"))
        fake = FakeLLM(reply())
        res = self.run_cd(fake, backend="batch")
        self.assertEqual(res["written"], ["chat-dual-spaces-double-dual"])
        text, fm = self.page("chat-dual-spaces-double-dual")
        self.assertEqual(fm["type"], "ai-chat")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "meta", "chats", fm["conversation"] + ".json")))
        self.assertEqual(cd.raw_list(fm), ["raw/llm-chats/new-chat-2.md", "raw/llm-chats/new-chat-1.md"])
        self.assertEqual(fm["generated"]["by"], "chat-digest/claude-sonnet-5-5")
        self.assertFalse(summary_lib.hand_written(fm))
        self.assertEqual(fm["summary_from"], summary_lib.summary_hash(text))
        self.assertEqual(summary_lib.problems(summary_lib.unquote(fm["description"])), [])
        self.assertIn("# Dual spaces and the double dual", text)
        self.assertIn("- Asked what a dual space is.", text)
        self.assertNotIn("{{", text)
        again = FakeLLM()
        self.assertEqual(self.run_cd(again)["written"], [])
        self.assertEqual(again.calls, [])

    def test_byte_identical_copy_is_marked_dupe_not_cited(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A, source=""))
        self.put("raw/llm-chats/b.md", clip(TURNS_A, source=""))
        self.corpus([("raw/llm-chats/a.md", "queued"), ("raw/llm-chats/b.md", "queued")])
        res = self.run_cd(FakeLLM(reply()))
        text, fm = self.page(res["written"][0])
        [kept] = cd.raw_list(fm)
        other = ({"raw/llm-chats/a.md", "raw/llm-chats/b.md"} - {kept}).pop()
        self.assertEqual(cd.dispositions(self.root)[other], f"dupe:{kept}")
        self.assertNotRegex(text, r"(?m)^url:")

    def test_attach_writes_no_llm_call(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/b.md", clip(TURNS_A, created="2026-03-05"))
        self.put("wiki/chat-dual.md", "---\ntype: ai-chat\nlegacy: true\nraw: raw/llm-chats/a.md\n---\n\n# Dual\n")
        fake = FakeLLM()
        self.run_cd(fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(cd.raw_list(self.page("chat-dual")[1]), ["raw/llm-chats/a.md", "raw/llm-chats/b.md"])

    def test_a_non_chat_page_citing_a_clip_does_not_own_it(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("wiki/course-x.md", "---\ntype: course\nraw: raw/llm-chats/a.md\n---\n\n# X\n")
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        self.assertEqual([i["action"] for i in cd.plan(convs, self.root)], ["new"])

    def test_a_comma_in_a_clip_name_is_skipped_not_mangled(self):
        self.put("raw/llm-chats/dual, part 2.md", clip(TURNS_A))
        convs, _ = chat_build.build(chat_build.clip_paths(self.root), self.root)
        [item] = cd.plan(convs, self.root)
        self.assertEqual(item["action"], "skip")
        self.assertIn("rename", item["why"])

    def test_a_raised_llm_error_keeps_the_zero_llm_work(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/b.md", clip([("You", "Graph coloring?"), ("Gemini", "Assign colors.")]))
        self.put("wiki/chat-dual.md", "---\ntype: ai-chat\nlegacy: true\nraw: raw/llm-chats/a.md\n---\n\n# D\n")

        def boom(reqs, backend=None, **kw):
            raise llm.LLMError("batch timed out")
        res = self.run_cd(boom)
        self.assertEqual((res["written"], len(res["failed"])), ([], 1))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "meta", "chats")))

    def test_bad_reply_is_asked_again_with_the_problem(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        fake = FakeLLM(reply(title="New chat"), reply())
        res = self.run_cd(fake)
        self.assertEqual(res["written"], ["chat-dual-spaces-double-dual"])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("previous reply to this was rejected", fake.calls[1][0].prompt)

    def test_reply_that_fails_twice_or_errors_writes_nothing(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("raw/llm-chats/b.md", clip([("You", "Graph coloring?"), ("Gemini", "Assign colors.")]))
        fake = FakeLLM(reply(description="too short"), {"error": "overloaded"}, reply(description="still short"))
        res = self.run_cd(fake)
        self.assertEqual((res["written"], len(res["failed"])), ([], 2))
        self.assertEqual([n for n in os.listdir(os.path.join(self.root, "wiki"))], [])

    def test_slug_collision_gets_a_suffix(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        self.put("wiki/chat-dual-spaces-double-dual.md", "---\ntype: ai-chat\nraw: raw/other.md\n---\n\n# X\n")
        res = self.run_cd(FakeLLM(reply()))
        self.assertEqual(res["written"], ["chat-dual-spaces-double-dual-2"])

    def test_dry_run_writes_nothing(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        res = self.run_cd(FakeLLM(), dry_run=True)
        self.assertEqual([i["action"] for i in res["items"]], ["new"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "meta", "chats")))

    def test_max_usd_refuses_before_any_call(self):
        self.put("raw/llm-chats/a.md", clip(TURNS_A))
        fake = FakeLLM()
        res = self.run_cd(fake, max_usd=0.0)
        self.assertEqual((fake.calls, len(res["failed"])), ([], 1))


class TestReply(unittest.TestCase):
    def test_too_many_or_too_long_bullets_are_trimmed(self):
        vals, bad = cd.check_reply(json.loads(reply(positions=["p"] * 9, suggestions=["word " * 200])))
        self.assertEqual(bad, [])
        self.assertEqual(len(vals["positions"]), 6)
        self.assertLessEqual(len(vals["suggestions"][0]), cd.BULLET_MAX)

    def test_placeholder_title_and_missing_positions_are_refused(self):
        _, bad = cd.check_reply(json.loads(reply(title="New notebook", positions=[])))
        self.assertTrue(any(b.startswith("title") for b in bad) and any(b.startswith("positions") for b in bad))
        self.assertEqual(cd.check_reply(None)[1], ["reply is not a JSON object"])

    def test_slug_is_sanitised(self):
        vals, _ = cd.check_reply(json.loads(reply(slug="Chat: AdamW vs. Muon!")))
        self.assertEqual(cd.unique_slug(vals["slug"], set()), "chat-adamw-vs-muon")
        long = cd.slugify("word " * 40)
        first = cd.unique_slug(long, set())
        self.assertLessEqual(len(cd.unique_slug(long, {first})), cd.SLUG_MAX)

    def test_clamp_keeps_head_and_tail(self):
        text = "A" * 100 + "B" * 100
        out = cd.clamp(text, limit=50)
        self.assertTrue(out.startswith("A" * 30) and out.endswith("B" * 20))
        self.assertIn("characters left out", out)


class TestEasyDigestRoutesChats(unittest.TestCase):
    def test_easy_digest_refuses_a_chat_clip(self):
        from kb_distillery.ingest import easy_digest
        with self.assertRaisesRegex(ValueError, "chat-digest --only"):
            easy_digest.prepare("raw/llm-chats/a.md")


if __name__ == "__main__":
    unittest.main()

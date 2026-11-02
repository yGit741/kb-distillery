"""Dashboard Chat tab: prompts, retrieval, message building, streaming parse, save-to-inbox."""
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


from kb_distillery.services import chat as chat_data
from kb_distillery.ingest import catalog
from kb_distillery.ingest.sources.chat import chat
from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.search import query

CHAT = {
    "id": "kb-chat:20261021-abc123",
    "title": "Tensor rank # basics",
    "model": "claude-sonnet-5-5",
    "template": "learn",
    "custom": True,
    "system": "Be brief.\n\nUse examples.",
    "messages": [
        {"role": "user", "content": "What is tensor rank?", "sources": ["tensor-rank"]},
        {"role": "assistant", "content": "It is the minimal number of rank-one terms [[tensor-rank]].\n\n```\n**You**\n```"},
        {"role": "user", "content": "And border rank?", "sources": []},
        {"role": "assistant", "content": "A limit version."},
    ],
}


class TestPrompts(unittest.TestCase):
    def test_shipped_templates(self):
        ids = [p["id"] for p in chat_data.list_prompts()]
        self.assertEqual(ids[0], "query")
        self.assertEqual(set(ids), {"query", "brainstorm", "learn", "critique", "draft"})
        for p in chat_data.list_prompts():
            self.assertTrue(p["text"] and not p["text"].startswith("---"))

    def test_system_keeps_fixed_suffix(self):
        system = chat_data.build_system("Custom instructions only.")
        self.assertTrue(system.startswith("Custom instructions only."))
        self.assertIn("[Title](slug.md)", system)
        self.assertNotIn("[[", system)
        self.assertIn(chat_data.FIXED_SUFFIX, chat_data.build_system(""))


class TestRetrieval(unittest.TestCase):
    def test_stopwords_only_returns_nothing(self):
        self.assertEqual(chat_data.retrieve("what do you know about this"), [])

    def test_slug_words_rank_their_page(self):
        index = query.parse_index()
        slug = next((s for s in sorted(index) if s.count("-") >= 1 and not s.startswith(("theme-", "course-"))
                     and os.path.isfile(query.wiki_path(s))), None)
        if not slug:
            raise unittest.SkipTest("no wiki pages")
        hits = chat_data.retrieve(slug.replace("-", " "), index=index)
        self.assertIn(slug, [h["slug"] for h in hits])
        self.assertEqual(hits, sorted(hits, key=lambda h: -h["score"]))

    def test_concept_named_in_question_ranks_first(self):
        if not os.path.isfile(query.wiki_path("tensor-rank")):
            raise unittest.SkipTest("no tensor-rank page")
        hits = chat_data.retrieve("In two sentences, what is tensor rank according to my notes?")
        self.assertEqual(hits[0]["slug"], "tensor-rank")

    def test_plan_turn_marks_pages_already_in_context(self):
        fake = [{"slug": "a", "score": 9, "summary": ""}, {"slug": "b", "score": 5, "summary": ""}]
        with mock.patch.object(chat_data, "retrieve", return_value=[dict(h) for h in fake]):
            hits, new = chat_data.plan_turn([{"role": "user", "content": "q", "sources": ["a"]}], "q2")
        self.assertEqual(new, ["b"])
        self.assertTrue(hits[0]["in_context"])


class TestMessages(unittest.TestCase):
    def test_history_replays_pages_and_caches_last_block(self):
        with mock.patch.object(chat_data, "pages_block", side_effect=lambda s: f"<kb-pages>{','.join(s)}</kb-pages>" if s else ""):
            msgs = chat_data.build_messages(CHAT["messages"], "New q", ["x"])
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user", "assistant", "user"])
        self.assertTrue(msgs[0]["content"][0]["text"].startswith("<kb-pages>tensor-rank</kb-pages>"))
        self.assertEqual(msgs[2]["content"][0]["text"], "And border rank?")
        self.assertIn("cache_control", msgs[-1]["content"][0])
        self.assertTrue(all("cache_control" not in m["content"][0] for m in msgs[:-1]))


class TestStream(unittest.TestCase):
    def test_parses_sse(self):
        events = [
            {"type": "message_start", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": 7}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
        ]
        raw = "".join(f"event: x\ndata: {json.dumps(e)}\n\n" for e in events).encode()
        resp = io.BytesIO(raw)
        with mock.patch("urllib.request.urlopen", return_value=resp) as op:
            out = list(chat_data.stream_claude("sys", [], "claude-sonnet-5-5", "k"))
        req = op.call_args[0][0]
        self.assertEqual(req.get_header("X-api-key"), "k")
        self.assertEqual("".join(v for k, v in out if k == "text"), "Hello")
        self.assertEqual(out[-1], ("usage", {"input_tokens": 10, "cache_read_input_tokens": 7, "output_tokens": 2}))


class TestKeyStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.keys = os.path.join(self.tmp.name, "keys")
        self.legacy = os.path.join(self.tmp.name, "anthropic_key")
        self._p = [mock.patch.object(chat_data, "KEYS_DIR", self.keys),
                   mock.patch.object(chat_data, "KEY_FILE", self.legacy),
                   mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self.tmp.cleanup()

    def test_add_list_switch_remove(self):
        self.assertEqual(chat_data.list_keys(), [])
        entry = chat_data.add_key(" Personal ", "sk-ant-api03-personal-0000000000abcd")
        self.assertEqual(entry["name"], "personal")
        self.assertEqual(entry["hint"], "sk-ant-…abcd")
        self.assertEqual(oct(os.stat(os.path.join(self.keys, "personal")).st_mode & 0o777), "0o600")
        chat_data.add_key("work", "sk-ant-api03-work-000000000000wxyz")
        self.assertEqual([k["name"] for k in chat_data.list_keys()], ["personal", "work"])
        # the active_key setting picks the key; a missing one falls back
        self.assertEqual(chat_data.load_api_key({"active_key": "work"}),
                         ("sk-ant-api03-work-000000000000wxyz", "work"))
        self.assertEqual(chat_data.load_api_key({"active_key": "gone"}), (None, None))
        with open(self.legacy, "w") as f:
            f.write("sk-ant-api03-legacy-00000000000leg\n")
        self.assertEqual(chat_data.load_api_key({"active_key": "gone"})[1], "default")
        self.assertEqual(chat_data.load_api_key({"active_key": ""})[1], "default")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-env-00000000000000env"}):
            self.assertEqual(chat_data.load_api_key({"active_key": ""})[1], "env")
            self.assertEqual(chat_data.load_api_key({"active_key": "work"})[1], "work")
            self.assertEqual(chat_data.list_keys()[0]["name"], "env")
            with self.assertRaises(ValueError):
                chat_data.remove_key("env")
        chat_data.remove_key("personal")
        self.assertEqual([k["name"] for k in chat_data.list_keys()], ["default", "work"])
        chat_data.remove_key("default")
        self.assertFalse(os.path.exists(self.legacy))
        with self.assertRaises(ValueError):
            chat_data.remove_key("personal")

    def test_add_key_validation(self):
        for name, key in [("env", "sk-ant-api03-x0000000000000000"), ("default", "sk-ant-api03-x0000000000000000"),
                          ("Bad Name!", "sk-ant-api03-x0000000000000000"), ("ok", "not-a-key"),
                          ("ok", "sk-ant-short"), ("ok", "sk-ant-api03-with space 000000000")]:
            with self.assertRaises(ValueError, msg=f"{name} {key}"):
                chat_data.add_key(name, key)
        self.assertEqual(chat_data.list_keys(), [])

    def test_auth_settings_validate(self):
        path = os.path.join(self.tmp.name, "chat.json")
        s = chat_data.load_settings(path)
        self.assertEqual((s["auth_mode"], s["active_key"]), ("api_key", ""))
        s = chat_data.save_settings({"auth_mode": "subscription", "active_key": "work"}, path)
        self.assertEqual((s["auth_mode"], s["active_key"]), ("subscription", "work"))
        with self.assertRaises(ValueError):
            chat_data.save_settings({"auth_mode": "oauth"}, path)
        with self.assertRaises(ValueError):
            chat_data.save_settings({"active_key": "../etc"}, path)

    def test_subscription_turns_do_not_touch_the_credit(self):
        ledger = os.path.join(self.tmp.name, "usage.jsonl")
        now = datetime.datetime(2026, 10, 22, 10, 0)
        usage = {"input_tokens": 1000, "output_tokens": 100}
        paid = chat_data.record_usage("claude-sonnet-5-5", usage, ledger, now, cost=0.05)
        free = chat_data.record_usage("claude-sonnet-5-5", usage, ledger, now, cost=0.24, billing="subscription")
        self.assertEqual((paid, free), (0.05, 0.0))
        rows = [json.loads(l) for l in open(ledger)]
        self.assertEqual((rows[1]["billing"], rows[1]["cost_usd"], rows[1]["est_cost_usd"]), ("subscription", 0.0, 0.24))
        s = chat_data.spend_summary(ledger, settings={"monthly_credit": 100.0, "reset_day": 30, "key_name": ""},
                                    today=datetime.date(2026, 10, 22))
        self.assertEqual((s["spent"], s["turns"], s["subscription_turns"]), (0.05, 1, 1))


class TestKey(unittest.TestCase):
    def test_env_wins_then_file(self):
        with tempfile.TemporaryDirectory() as d:
            kf = os.path.join(d, "k")
            with open(kf, "w") as f:
                f.write("file-key\n")
            no_pref = {"active_key": ""}   # no key chosen in the Session card
            with mock.patch.object(chat_data, "KEY_FILE", kf):
                with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
                    self.assertEqual(chat_data.load_api_key(no_pref), ("env-key", "env"))
                with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
                    self.assertEqual(chat_data.load_api_key(no_pref), ("file-key", "default"))
            with mock.patch.object(chat_data, "KEY_FILE", os.path.join(d, "missing")), \
                    mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
                self.assertEqual(chat_data.load_api_key(no_pref), (None, None))


class TestSpend(unittest.TestCase):
    USAGE = {"input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
             "cache_read_input_tokens": 1_000_000, "output_tokens": 1_000_000}

    def test_cost_per_model(self):
        # Sonnet 5.5: 2 in + 2*1.25 write + 0.20 read + 10 out
        self.assertAlmostEqual(chat_data.cost_usd("claude-sonnet-5-5", self.USAGE), 14.70)
        self.assertAlmostEqual(chat_data.cost_usd("claude-opus-5-5", self.USAGE), 29.20)
        self.assertAlmostEqual(chat_data.cost_usd("claude-haiku-5-5", self.USAGE), 0.735)
        self.assertEqual(chat_data.cost_usd("unknown-model", self.USAGE), 0.0)

    def test_one_hour_cache_writes_cost_double(self):
        u = {"cache_creation_input_tokens": 1_000_000,
             "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}}
        self.assertAlmostEqual(chat_data.cost_usd("claude-sonnet-5-5", u), 4.0)

    def test_cycle_bounds_clamp_to_month_end(self):
        d = datetime.date
        self.assertEqual(chat_data._cycle_bounds(d(2026, 10, 21), 30), (d(2026, 9, 30), d(2026, 10, 30)))
        self.assertEqual(chat_data._cycle_bounds(d(2026, 10, 30), 30), (d(2026, 10, 30), d(2026, 11, 30)))
        self.assertEqual(chat_data._cycle_bounds(d(2027, 3, 1), 30), (d(2027, 2, 28), d(2027, 3, 30)))
        self.assertEqual(chat_data._cycle_bounds(d(2026, 12, 31), 1), (d(2026, 12, 1), d(2027, 1, 1)))

    def test_ledger_sums_current_cycle_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "usage.jsonl")
            u = {"input_tokens": 100_000, "output_tokens": 10_000}            # $0.30 on Sonnet
            chat_data.record_usage("claude-sonnet-5-5", u, ledger, now=datetime.datetime(2026, 9, 29, 12))
            chat_data.record_usage("claude-sonnet-5-5", u, ledger, now=datetime.datetime(2026, 10, 1, 12))
            chat_data.record_usage("claude-sonnet-5-5", u, ledger, now=datetime.datetime(2026, 10, 21, 9))
            s = chat_data.spend_summary(ledger, settings={"monthly_credit": 100.0, "reset_day": 30, "key_name": ""},
                                        today=datetime.date(2026, 10, 21))
        self.assertEqual(s["turns"], 2)
        self.assertAlmostEqual(s["spent"], 0.60)
        self.assertAlmostEqual(s["left"], 99.40)
        self.assertEqual((s["cycle_start"], s["next_reset"]), ("2026-09-30", "2026-10-30"))

    def test_settings_validate_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chat.json")
            self.assertEqual(chat_data.load_settings(path), chat_data.DEFAULT_SETTINGS)
            saved = chat_data.save_settings({"key_name": "  thesis   kb ", "monthly_credit": "50", "reset_day": 1}, path)
            self.assertEqual(saved, {"key_name": "thesis kb", "monthly_credit": 50.0, "reset_day": 1,
                                     "backend": "agent", "auth_mode": "api_key", "active_key": ""})
            self.assertEqual(chat_data.load_settings(path), saved)
            self.assertEqual(chat_data.save_settings({"backend": "direct"}, path)["backend"], "direct")
            with self.assertRaises(ValueError):
                chat_data.save_settings({"backend": "foo"}, path)
            with self.assertRaises(ValueError):
                chat_data.save_settings({"reset_day": 0}, path)
            with self.assertRaises(ValueError):
                chat_data.save_settings({"monthly_credit": -5}, path)

    def test_key_hint_shows_last_four_only(self):
        self.assertEqual(chat_data.key_hint("sk-ant-api03-secretsecretABCD"), "sk-ant-…ABCD")
        self.assertEqual(chat_data.key_hint(None), "")


class TestSave(unittest.TestCase):
    def test_round_trip_through_parser_and_catalog(self):
        text = chat_data.render_chat(CHAT, today="2026-10-21")
        fm = parse_frontmatter(text)
        self.assertEqual(fm["title"], "Tensor rank basics")
        self.assertEqual(fm["source"], CHAT["id"])
        self.assertEqual(fm["prompt_template"], "learn")
        self.assertEqual(fm["system_prompt"], "custom")
        self.assertEqual(fm["retrieved"], ["tensor-rank"])
        self.assertTrue(chat.is_chat(text))
        turns = chat.parse_turns(text)
        self.assertEqual([t.role for t in turns], ["user", "model", "user", "model"])
        self.assertEqual(turns[0].text, "What is tensor rank?")
        self.assertIn("**You**", turns[1].text)          # marker inside a fence stays body text
        self.assertEqual(turns[3].text, "A limit version.")

        with tempfile.TemporaryDirectory() as d:
            first = chat_data.save_chat(CHAT, inbox=d, today="2026-10-21")
            second = chat_data.save_chat(CHAT, inbox=d, today="2026-10-21")
            self.assertNotEqual(first, second)
            name = os.path.join(d, os.path.basename(first))
            self.assertTrue(name.endswith("tensor-rank-basics.md"))
            self.assertTrue(catalog._looks_like_chat(name))

    def test_refuses_empty_chat(self):
        with self.assertRaises(ValueError):
            chat_data.save_chat({"messages": [{"role": "user", "content": "hi"}]}, inbox=tempfile.gettempdir())


if __name__ == "__main__":
    unittest.main()

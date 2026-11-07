"""Tests for the Chat tab's agent backend (src/kb_distillery/services/chat_agent.py).

A fake `claude_agent_sdk` is injected into sys.modules, so these run without the SDK and without
network: the policy is pure, and the stream bridge is driven by a scripted message list.
"""
import asyncio
import os
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock


from kb_distillery.config import userdir
from kb_distillery.services import chat_agent
from kb_distillery.services import chat as chat_data

ROOT = chat_agent.ROOT


# ── fake SDK ───────────────────────────────────────────────────────────────

class _Opts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Matcher:
    def __init__(self, matcher=None, hooks=None, timeout=None):
        self.matcher, self.hooks = matcher, hooks or []
        self.timeout = timeout


class _Allow:
    def __init__(self, updated_input=None, updated_permissions=None):
        self.behavior, self.updated_input = "allow", updated_input


class _Deny:
    def __init__(self, message="", interrupt=False):
        self.behavior, self.message = "deny", message


def _cls(cls_name, **fields):
    return type(cls_name, (), {"__init__": lambda self, **kw: self.__dict__.update({**fields, **kw})})


SystemMessage = _cls("SystemMessage", subtype=None, data=None)
AssistantMessage = _cls("AssistantMessage", content=None)
UserMessage = _cls("UserMessage", content=None)
StreamEvent = _cls("StreamEvent", event=None, parent_tool_use_id=None)
ResultMessage = _cls("ResultMessage", session_id=None, total_cost_usd=None, usage=None, num_turns=None,
                     duration_ms=None, is_error=False, result=None)
TextBlock = _cls("TextBlock", text="")
ToolUseBlock = _cls("ToolUseBlock", id=None, name="", input=None)
ToolResultBlock = _cls("ToolResultBlock", tool_use_id=None, is_error=False, content=None)


class CLINotFoundError(Exception):
    pass


class FakeClient:
    """Scripted ClaudeSDKClient. `script(options)` returns the messages, or raises."""
    instances = []
    script = staticmethod(lambda options: [])
    block = None            # threading.Event: when set, the stream parks after the first message

    def __init__(self, options):
        self.options = options
        self.prompt = None
        self.interrupted = False
        self.disconnected = False
        FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.disconnected = True
        return False

    async def query(self, prompt):
        self.prompt = prompt

    async def interrupt(self):
        self.interrupted = True

    async def receive_response(self):
        msgs = FakeClient.script(self.options)
        for i, m in enumerate(msgs):
            yield m
            if FakeClient.block is not None and i == 0:
                while not FakeClient.block.is_set():
                    await asyncio.sleep(0.01)


def fake_sdk():
    mod = types.ModuleType("claude_agent_sdk")
    mod.__version__ = "0.0-fake"
    mod.ClaudeAgentOptions = _Opts
    mod.HookMatcher = _Matcher
    mod.PermissionResultAllow = _Allow
    mod.PermissionResultDeny = _Deny
    mod.ClaudeSDKClient = FakeClient
    mod.CLINotFoundError = CLINotFoundError
    return mod


def delta(text):
    return StreamEvent(event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


def read_tool(slug, tid="t1"):
    return AssistantMessage(content=[ToolUseBlock(id=tid, name="Read",
                                                  input={"file_path": os.path.join(ROOT, "wiki", f"{slug}.md")})])


def result(**kw):
    base = dict(session_id="s1", total_cost_usd=0.0123, num_turns=3, duration_ms=4200,
                usage={"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 500,
                       "cache_creation_input_tokens": 0})
    base.update(kw)
    return ResultMessage(**base)


class SDKCase(unittest.TestCase):
    def setUp(self):
        FakeClient.instances = []
        FakeClient.block = None
        FakeClient.script = staticmethod(lambda options: [])
        self._mods = mock.patch.dict(sys.modules, {"claude_agent_sdk": fake_sdk()})
        self._mods.start()
        self.tmp = tempfile.TemporaryDirectory()
        self._ledger = mock.patch.object(chat_data, "LEDGER_FILE", os.path.join(self.tmp.name, "usage.jsonl"))
        self._ledger.start()
        self._ca = mock.patch.object(chat_agent, "ca_bundle_path", lambda *a, **k: None)
        self._ca.start()
        self._index = mock.patch.object(chat_agent.query, "parse_index", lambda: {
            "tensor-rank": {"summary": "Minimal number of rank-one terms", "status": "solid", "section": ""},
            "theme-tensor-factorization": {"summary": "Tensors", "status": "solid", "section": ""},
        })
        self._index.start()

    def tearDown(self):
        for p in (self._index, self._ca, self._ledger, self._mods):
            p.stop()
        self.tmp.cleanup()

    def run_stream(self, **kw):
        kw.setdefault("model", "claude-sonnet-5-5")
        kw.setdefault("system", "sys")
        kw.setdefault("key", "sk-test")
        kw.setdefault("log", lambda s: None)
        return list(chat_agent.stream_agent("What is tensor rank?", **kw))


# ── policy ─────────────────────────────────────────────────────────────────

class TestPolicy(unittest.TestCase):
    def allow(self, tool, inp):
        d = chat_agent.tool_policy(tool, inp)
        self.assertTrue(d.allow, f"{tool} {inp} should be allowed: {d.reason}")
        return d

    def deny(self, tool, inp):
        d = chat_agent.tool_policy(tool, inp)
        self.assertFalse(d.allow, f"{tool} {inp} should be denied")
        self.assertTrue(d.reason)
        return d

    def test_read_scope(self):
        self.allow("Read", {"file_path": "wiki/tensor-rank.md"})
        self.allow("Read", {"file_path": os.path.join(ROOT, "wiki", "tensor-rank.md")})
        self.allow("Read", {"file_path": "wiki/index.md"})
        self.allow("Read", {"file_path": "think/ideas.md"})
        self.allow("Read", {"file_path": "raw/web-clips/some-post.md"})
        self.deny("Read", {"file_path": "raw/printed-docs/2023-paper.pdf"})
        self.deny("Read", {"file_path": userdir.path("anthropic_key")})
        self.deny("Read", {"file_path": os.path.join(userdir.legacy_dir(), "anthropic_key")})
        self.deny("Read", {"file_path": "wiki/../src/kb_distillery/vault/schema.py"})
        self.deny("Read", {"file_path": "meta/corpus.tsv"})
        self.deny("Read", {"file_path": ".claude/settings.json"})
        self.deny("Read", {})

    def test_read_symlink_out_of_wiki_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = os.path.join(tmp, "secret.md")
            with open(secret, "w") as f:
                f.write("x")
            link = os.path.join(ROOT, "wiki", "zz-test-link-do-not-keep.md")
            try:
                os.symlink(secret, link)
                self.deny("Read", {"file_path": link})
            finally:
                if os.path.islink(link):
                    os.unlink(link)

    def test_grep_glob_default_to_wiki(self):
        d = self.allow("Grep", {"pattern": "tensor"})
        self.assertEqual(d.updated_input["path"], chat_agent.WIKI)
        self.assertEqual(d.updated_input["pattern"], "tensor")
        self.assertIsNone(self.allow("Grep", {"pattern": "x", "path": "wiki"}).updated_input)
        self.allow("Glob", {"pattern": "q-*.md", "path": "wiki"})
        self.allow("Glob", {"pattern": "*.md", "path": "raw/web-clips"})
        self.deny("Grep", {"pattern": "key", "path": "meta"})
        self.deny("Grep", {"pattern": "key", "path": "/etc"})

    def test_bash_allowlist(self):
        self.allow("Bash", {"command": 'python3 -m kb_distillery.search.query candidates "tensor rank"'})
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.query mocs"})
        self.allow("Bash", {"command": "python -m kb_distillery.search.semfind theme theme-quantum"})
        self.allow("Bash", {"command": "python3 -m kb_distillery.ingest resolve old-slug"})
        self.allow("Bash", {"command": f"/usr/bin/python3 {os.path.join(ROOT, 'src/kb_distillery/search/query.py')} mocs"})
        self.allow("Bash", {"command": 'python3 -m kb_distillery.search.explore_raw find "x"'})
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.explore_raw read raw/web-clips/a.md"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.explore_raw find x | cat"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.explore_raw bogus x"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.query mocs && rm -rf wiki"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.query mocs; git status"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.query mocs | tee x"})
        self.deny("Bash", {"command": "$(python3 -m kb_distillery.search.query mocs)"})
        self.deny("Bash", {"command": "rm wiki/tensor-rank.md"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.lint.lint"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.ingest scrap http://x"})
        self.deny("Bash", {"command": "cat index.md"})
        self.deny("Bash", {"command": "git status"})
        self.deny("Bash", {"command": ""})
        self.deny("Bash", {})

    def test_citations_read_only_subcommands(self):
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.citations rank 2103.00001 --limit 5"})
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.citations status"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.citations fetch --limit 5"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.citations fetch"})

    def test_cypher_queries(self):
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.cypher run 'MATCH (s:Source)-[:MENTIONS]->(i:Idea) "
                                       "WHERE i.slug = \"x\" RETURN s.slug' --limit 20"})
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.cypher named gaps --param min_shared=3"})
        self.allow("Bash", {"command": "python3 -m kb_distillery.search.cypher list"})
        # the carve-out is one single-quoted argument, nothing after it but --limit/--json
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher run 'MATCH (n) RETURN n' ; rm -rf wiki"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher run 'MATCH (n) RETURN n' | tee x"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher run 'a' 'b'"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher run \"MATCH (n) RETURN $(id)\""})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher run 'x'\nrm -rf wiki"})
        self.deny("Bash", {"command": "python3 -m kb_distillery.search.cypher bogus"})

    def test_cypher_denied_in_scope(self):
        scope = {"slug": "scope-x", "rows": []}
        for cmd in ("python3 -m kb_distillery.search.cypher list",
                    "python3 -m kb_distillery.search.cypher run 'MATCH (n) RETURN n.slug'"):
            self.assertFalse(chat_agent._bash_allowed(cmd, scope), cmd)

    def test_other_tools_denied(self):
        self.deny("Write", {"file_path": "wiki/x.md", "content": "y"})
        self.deny("Edit", {"file_path": "wiki/x.md"})
        self.deny("WebFetch", {"url": "http://x"})
        self.deny("Agent", {"prompt": "x"})

    def test_hook_wrapper_shapes(self):
        hook = chat_agent.make_hook()
        out = asyncio.run(hook({"tool_name": "Grep", "tool_input": {"pattern": "x"}}, "t", None))
        spec = out["hookSpecificOutput"]
        self.assertEqual((spec["hookEventName"], spec["permissionDecision"]), ("PreToolUse", "allow"))
        self.assertEqual(spec["updatedInput"]["path"], chat_agent.WIKI)
        out = asyncio.run(hook({"tool_name": "Write", "tool_input": {"file_path": "wiki/x.md"}}, "t", None))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("read-only", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_can_use_tool_wrapper(self):
        with mock.patch.dict(sys.modules, {"claude_agent_sdk": fake_sdk()}):
            cb = chat_agent.make_can_use_tool()
            ok = asyncio.run(cb("Read", {"file_path": "wiki/x.md"}, None))
            self.assertEqual(ok.behavior, "allow")
            no = asyncio.run(cb("Bash", {"command": "rm -rf wiki"}, None))
            self.assertEqual(no.behavior, "deny")
            self.assertIn("read-only", no.message)


# ── options and prompt ─────────────────────────────────────────────────────

class TestOptions(SDKCase):
    def test_build_options(self):
        o = chat_agent.build_options("claude-opus-5-5", "SYS", "sk-x", session_id="abc")
        self.assertEqual(o.cwd, ROOT)
        self.assertEqual(o.model, "claude-opus-5-5")
        self.assertEqual(o.system_prompt, "SYS")
        self.assertEqual(o.setting_sources, [])
        self.assertEqual(o.permission_mode, "default")
        self.assertEqual(o.max_turns, chat_agent.MAX_TURNS)
        self.assertTrue(o.include_partial_messages)
        self.assertEqual(o.resume, "abc")
        self.assertEqual(o.env["ANTHROPIC_API_KEY"], "sk-x")
        self.assertEqual(o.env["CLAUDECODE"], "")
        self.assertNotIn("NODE_EXTRA_CA_CERTS", o.env)
        self.assertEqual(set(o.tools), {"Read", "Grep", "Glob", "Bash"})
        self.assertIn("Write", o.disallowed_tools)
        self.assertIn("WebFetch", o.disallowed_tools)
        self.assertEqual(len(o.hooks["PreToolUse"][0].hooks), 1)
        self.assertTrue(callable(o.can_use_tool))
        self.assertIsNone(chat_agent.build_options("claude-opus-5-5", "SYS", "sk-x").resume)

    def test_ca_bundle_goes_to_node(self):
        o = chat_agent.build_options("claude-opus-5-5", "SYS", "sk-x", ca_path="/tmp/roots.pem")
        self.assertEqual(o.env["NODE_EXTRA_CA_CERTS"], "/tmp/roots.pem")

    def test_agent_system_prompt(self):
        s = chat_agent.build_agent_system("Be brief.")
        self.assertTrue(s.startswith("Be brief."))
        self.assertIn("[theme-tensor-factorization](theme-tensor-factorization.md)", s)
        self.assertIn("kb_distillery.search.query candidates", s)
        self.assertIn("[Title](slug.md)", s)
        self.assertNotIn("[[", s)
        self.assertNotIn("<kb-pages>", s)


# ── stream mapping ─────────────────────────────────────────────────────────

class TestStream(SDKCase):
    def test_event_order_sources_and_cost(self):
        FakeClient.script = staticmethod(lambda o: [
            SystemMessage(subtype="init", data={"session_id": "s1"}),
            delta("Hel"), delta("lo. "),
            read_tool("tensor-rank"),
            UserMessage(content=[ToolResultBlock(tool_use_id="t1")]),
            delta("Rank is minimal [[tensor-rank]], see [[theme-tensor-factorization]] and [[nope]]."),
            result(),
        ])
        events = self.run_stream()
        names = [n for n, _ in events]
        self.assertEqual(names, ["session", "delta", "delta", "tool", "sources", "tool", "delta",
                                 "usage", "session", "sources", "done"])
        data = dict((n, d) for n, d in events)   # last of each kind
        tool = events[3][1]
        self.assertEqual((tool["name"], tool["summary"], tool["id"]), ("Read", "read tensor-rank", "t1"))
        self.assertEqual(events[4][1]["new"], ["tensor-rank"])
        final = events[9][1]
        self.assertEqual([h["slug"] for h in final["hits"]], ["tensor-rank", "theme-tensor-factorization"])
        self.assertEqual(final["hits"][0]["summary"], "Minimal number of rank-one terms")
        self.assertEqual(final["hits"][0]["score"], 1)
        self.assertEqual((tool["round"], tool["kind"], tool["status"], tool["read"]), (1, "open", "running", ["tensor-rank"]))
        self.assertEqual(events[5][1]["status"], "done")
        self.assertAlmostEqual(data["usage"]["cost_usd"], 0.0123)
        self.assertEqual(data["usage"]["num_turns"], 3)
        self.assertEqual(data["usage"]["input_tokens"], 1000)
        self.assertIn("spend", data["usage"])
        self.assertEqual(data["session"], {"id": "s1"})
        with open(chat_data.LEDGER_FILE) as f:
            import json
            row = json.loads(f.readline())
        self.assertAlmostEqual(row["cost_usd"], 0.0123)   # SDK total, not the price-table estimate
        client = FakeClient.instances[0]
        self.assertEqual(client.prompt, "What is tensor rank?")
        self.assertIsNone(client.options.resume)
        self.assertTrue(client.disconnected)

    def test_tool_error_marks_trace_entry(self):
        FakeClient.script = staticmethod(lambda o: [
            SystemMessage(subtype="init", data={"session_id": "s1"}),
            AssistantMessage(content=[ToolUseBlock(id="b1", name="Bash", input={"command": "python3 -m kb_distillery.search.query candidates \"x\""})]),
            UserMessage(content=[ToolResultBlock(tool_use_id="b1", is_error=True)]),
            delta("ok"), result(),
        ])
        events = self.run_stream()
        tools = [d for n, d in events if n == "tool"]
        self.assertEqual(tools[0]["summary"], 'candidates "x"')
        self.assertTrue(tools[1]["error"])
        self.assertEqual(tools[1]["id"], "b1")

    def test_read_and_seen_slugs_land_on_trace_steps(self):
        FakeClient.script = staticmethod(lambda o: [
            SystemMessage(subtype="init", data={"session_id": "s1"}),
            AssistantMessage(content=[ToolUseBlock(id="g1", name="Grep", input={"pattern": "rank"})]),
            UserMessage(content=[ToolResultBlock(tool_use_id="g1", content="wiki/tensor-rank.md:3: rank\nnope.md\ntensor-rank.md")]),
            read_tool("tensor-rank", tid="r1"),
            UserMessage(content=[ToolResultBlock(tool_use_id="r1", content="tensor-rank text")]),
            delta("ok"), result(),
        ])
        tools = [d for n, d in self.run_stream() if n == "tool"]
        grep = [t for t in tools if t["id"] == "g1"][-1]
        self.assertEqual(grep["seen"], ["tensor-rank"])
        self.assertNotIn("read", grep)
        read = [t for t in tools if t["id"] == "r1"]
        self.assertEqual(read[0]["read"], ["tensor-rank"])
        self.assertNotIn("seen", read[-1])

    def test_steps_without_page_data_stay_bare(self):
        FakeClient.script = staticmethod(lambda o: [
            AssistantMessage(content=[ToolUseBlock(id="g1", name="Grep", input={"pattern": "zzz"})]),
            UserMessage(content=[ToolResultBlock(tool_use_id="g1", content="nothing here")]),
            delta("ok"), result(),
        ])
        tools = [d for n, d in self.run_stream() if n == "tool"]
        self.assertEqual([t["status"] for t in tools], ["running", "done"])     # the result ticks the step off
        for t in tools:
            self.assertNotIn("seen", t)
            self.assertNotIn("read", t)

    def test_grep_text_is_not_a_seen_page_and_failed_read_is_not_read(self):
        FakeClient.script = staticmethod(lambda o: [
            AssistantMessage(content=[ToolUseBlock(id="g1", name="Grep", input={"pattern": "rank"})]),
            UserMessage(content=[ToolResultBlock(tool_use_id="g1", content="the tensor-rank of a matrix")]),
            read_tool("tensor-rank", tid="r1"),
            UserMessage(content=[ToolResultBlock(tool_use_id="r1", is_error=True)]),
            delta("ok"), result(),
        ])
        tools = [d for n, d in self.run_stream() if n == "tool"]
        self.assertFalse([t for t in tools if t["id"] == "g1" and "seen" in t])
        self.assertNotIn("read", [t for t in tools if t["id"] == "r1"][-1])

    def _map(self, state, *msgs):
        out = []
        for m in msgs:
            out += [d for n, d in chat_agent.map_message(m, state) if n == "tool"]
        return out

    def test_rounds_share_parallel_calls_and_kinds_and_queries(self):
        bash = lambda tid, cmd: ToolUseBlock(id=tid, name="Bash", input={"command": cmd})
        state = chat_agent.TurnState()
        first = self._map(state, AssistantMessage(content=[
            bash("a", 'python3 -m kb_distillery.search.query candidates "tensor rank"'),
            ToolUseBlock(id="b", name="Grep", input={"pattern": "rank"}),
            ToolUseBlock(id="c", name="Glob", input={"pattern": "wiki/paper-*.md"})]))
        self.assertEqual([t["round"] for t in first], [1, 1, 1])
        self.assertEqual([(t["kind"], t["query"], t["status"]) for t in first],
                         [("shortlist", '"tensor rank"', "running"), ("keyword", "rank", "running"),
                          ("files", "wiki/paper-*.md", "running")])
        self._map(state, UserMessage(content=[ToolResultBlock(tool_use_id="a")]), AssistantMessage(content=[TextBlock(text="hm")]))
        second = self._map(state, AssistantMessage(content=[
            bash("d", "python3 -m kb_distillery.search.semfind 'implicit bias'"),
            bash("e", "python3 -m kb_distillery.search.cypher MATCH"),
            bash("f", "python3 -m kb_distillery.ingest resolve Smith"),
            bash("g", "python3 -m kb_distillery.search.query mocs"),
            bash("h", "ls")]))
        self.assertEqual([t["round"] for t in second], [2] * 5)
        self.assertEqual([t["kind"] for t in second], ["meaning", "graph", "alias", "shortlist", "other"])
        self.assertEqual(second[0]["query"], "'implicit bias'")
        self.assertNotIn("query", second[4])
        third = self._map(state, UserMessage(content=[ToolResultBlock(tool_use_id="d")]),
                          read_tool("tensor-rank", tid="r"))
        third = third[-1]
        self.assertEqual((third["round"], third["kind"], third["read"]), (3, "open", ["tensor-rank"]))
        self.assertNotIn("query", third)
        self.assertEqual(chat_agent.TurnState().round, 0)       # a new turn starts over

    def test_calls_split_over_messages_still_share_a_round_until_results_return(self):
        state = chat_agent.TurnState()
        t = self._map(state,
                      AssistantMessage(content=[ToolUseBlock(id="a", name="Grep", input={"pattern": "x"})]),
                      AssistantMessage(content=[ToolUseBlock(id="b", name="Grep", input={"pattern": "y"})]),
                      UserMessage(content=[ToolResultBlock(tool_use_id="a"), ToolResultBlock(tool_use_id="b")]),
                      AssistantMessage(content=[ToolUseBlock(id="c", name="Grep", input={"pattern": "z"})]))
        self.assertEqual([(x["id"], x["round"]) for x in t if x["status"] == "running"], [("a", 1), ("b", 1), ("c", 2)])

    def test_web_steps_carry_url_and_domains(self):
        state = chat_agent.TurnState()
        sub = self._map(state, AssistantMessage(content=[
            ToolUseBlock(id="s", name="WebSearch", input={"query": "grokking"}),
            ToolUseBlock(id="f", name="WebFetch", input={"url": "https://a.org/x"})]))
        self.assertEqual((sub[0]["kind"], sub[0]["query"]), ("web-search", "grokking"))
        self.assertEqual((sub[1]["kind"], sub[1]["url"]), ("web-source", "https://a.org/x"))
        links = ('Links: [{"title": "A", "url": "https://a.org/1"}, {"title": "B", "url": "https://b.com/2"},'
                 ' {"title": "C", "url": "https://a.org/3"}]\n')
        done = self._map(state, UserMessage(content=[ToolResultBlock(tool_use_id="s", content=links),
                                                     ToolResultBlock(tool_use_id="f", is_error=True)]))
        self.assertEqual(done[0]["domains"], ["a.org", "b.com"])
        self.assertEqual((done[0]["status"], done[1]["status"], done[1]["error"]), ("done", "error", True))
        self.assertNotIn("result", done[0])                     # preview stays agent-mode only

    def test_explore_raw_read_maps_digested_raw_file_to_its_page(self):
        from kb_distillery.search import explore_raw
        rows = {"raw/printed-docs/p.pdf": {"slug": "tensor-rank", "disposition": "source"},
                "raw/printed-docs/u.pdf": {"slug": "", "disposition": "queued"}}
        cmd = lambda v, path: ToolUseBlock(id=path, name="Bash", input={
            "command": f"python3 -m kb_distillery.search.explore_raw {v} {path} --pages 1-2"})
        with mock.patch.object(explore_raw, "_manifest", return_value=rows):
            state = chat_agent.TurnState()
            t = self._map(state, AssistantMessage(content=[cmd("read", "raw/printed-docs/p.pdf"),
                                                           cmd("check", "raw/printed-docs/p.pdf"),
                                                           cmd("read", "raw/printed-docs/u.pdf"),
                                                           cmd("read", "raw/printed-docs/zz.pdf")]))
        self.assertEqual([x["kind"] for x in t], ["raw"] * 4)
        self.assertEqual(t[0]["read"], ["tensor-rank"])
        self.assertEqual(t[1]["read"], ["tensor-rank"])
        self.assertEqual(t[0]["query"], "raw/printed-docs/p.pdf")
        self.assertNotIn("read", t[2])
        self.assertEqual(t[2]["query"], "raw/printed-docs/u.pdf")
        self.assertNotIn("read", t[3])
        self.assertIn("tensor-rank", state.reads)

    def test_attachment_read_and_status_outside_agent_mode(self):
        att = os.path.join(chat_agent.chat_attachments.chat_root(), "sess", "n.txt")
        state = chat_agent.TurnState()
        t = self._map(state, AssistantMessage(content=[ToolUseBlock(id="x", name="Read", input={"file_path": att})]))
        self.assertEqual((t[0]["kind"], t[0]["status"]), ("attachment", "running"))
        self.assertNotIn("read", t[0])
        done = self._map(state, UserMessage(content=[ToolResultBlock(tool_use_id="x", content="hi")]))
        self.assertEqual(done[0]["status"], "done")
        self.assertEqual((done[0]["name"], done[0]["summary"], done[0]["id"]), ("Read", t[0]["summary"], "x"))

    def test_result_slugs_cap_and_dedupe(self):
        index = {f"p{i}": {} for i in range(80)}
        text = " ".join(f"p{i}.md p{i}" for i in range(80))
        out = chat_agent.result_slugs(text, index)
        self.assertEqual(len(out), 50)
        self.assertEqual(out[:2], ["p0", "p1"])
        self.assertEqual(chat_agent.result_slugs("a.md b", None), ["a"])

    def test_subagent_deltas_are_ignored(self):
        ev = StreamEvent(event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}},
                         parent_tool_use_id="inner")
        self.assertEqual(chat_agent.map_message(ev, chat_agent.TurnState()), [])

    def test_result_error_is_reported(self):
        FakeClient.script = staticmethod(lambda o: [delta("partial"), result(is_error=True, result="budget exceeded")])
        events = self.run_stream()
        self.assertEqual(events[-1][0], "error")
        self.assertIn("budget exceeded", events[-1][1]["error"])
        self.assertNotIn("done", [n for n, _ in events])

    def test_resume_is_passed_and_expired_session_restarts(self):
        def script(o):
            if o.resume == "old":
                raise RuntimeError("No conversation found with session ID: old")
            return [SystemMessage(subtype="init", data={"session_id": "new"}), delta("fresh"), result(session_id="new")]
        FakeClient.script = staticmethod(script)
        history = [{"role": "user", "content": "What is tensor rank?"},
                   {"role": "assistant", "content": "x" * 2000},
                   {"role": "user", "content": "and border rank?"}]
        events = self.run_stream(session_id="old", history=history)
        names = [n for n, _ in events]
        self.assertEqual(names[0], "notice")
        self.assertIn("done", names)
        self.assertEqual([c.options.resume for c in FakeClient.instances], ["old", None])
        prompt = FakeClient.instances[1].prompt
        self.assertTrue(prompt.startswith("Earlier in this conversation:"))
        self.assertIn("and border rank?", prompt)
        self.assertTrue(prompt.endswith("New question: What is tensor rank?"))
        self.assertIn(" […]", prompt)     # long turns are truncated
        self.assertEqual([d for n, d in events if n == "session"][-1], {"id": "new"})

    def test_other_errors_do_not_retry(self):
        def script(o):
            raise RuntimeError("Command failed with exit code 1")
        FakeClient.script = staticmethod(script)
        events = self.run_stream(session_id="old")
        self.assertEqual([n for n, _ in events], ["error"])
        self.assertIn("exit code 1", events[0][1]["error"])
        self.assertEqual(len(FakeClient.instances), 1)

    def test_missing_cli_falls_back_to_path_claude(self):
        calls = []

        def script(o):
            calls.append(getattr(o, "cli_path", None))
            if len(calls) == 1:
                raise CLINotFoundError("Claude Code not found")
            return [delta("ok"), result()]
        FakeClient.script = staticmethod(script)
        with mock.patch.object(chat_agent.shutil, "which", lambda name: "/opt/homebrew/bin/claude"):
            events = self.run_stream()
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(calls, [None, "/opt/homebrew/bin/claude"])

    def test_closing_the_generator_interrupts_the_agent(self):
        FakeClient.block = threading.Event()
        FakeClient.script = staticmethod(lambda o: [delta("first"), delta("second"), result()])
        gen = chat_agent.stream_agent("q", model="claude-sonnet-5-5", system="s", key="k", log=lambda s: None)
        self.assertEqual(next(gen), ("delta", "first"))
        with mock.patch.object(chat_agent, "PING_SECONDS", 0.05):
            self.assertEqual(next(gen), ("ping", None))
        FakeClient.block.set()
        gen.close()
        client = FakeClient.instances[0]
        self.assertTrue(client.interrupted)
        self.assertTrue(client.disconnected)

    def test_sdk_info_without_sdk(self):
        with mock.patch.dict(sys.modules, {"claude_agent_sdk": None}):
            info = chat_agent.sdk_info()
        self.assertFalse(info["available"])
        self.assertIn("pixi install", info["error"])


class TestSubscription(SDKCase):
    def test_env_blank_key_means_subscription(self):
        self.assertEqual(chat_agent.agent_env(None, ca_path=None)["ANTHROPIC_API_KEY"], "")
        self.assertEqual(chat_agent.agent_env("sk-x", ca_path=None)["ANTHROPIC_API_KEY"], "sk-x")

    def test_subscription_status_parses_auth_status(self):
        chat_agent._SUB_CACHE.update(at=0.0, value=None)
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw["env"].get("ANTHROPIC_API_KEY")))
            return types.SimpleNamespace(stdout='{"loggedIn": true, "authMethod": "claude.ai", '
                                                '"email": "me@example.com", "subscriptionType": "max"}')
        with mock.patch.object(chat_agent.subprocess, "run", fake_run):
            s = chat_agent.subscription_status(now=1000.0, cli="/x/claude")
            again = chat_agent.subscription_status(now=1030.0, cli="/x/claude")   # cached
        self.assertEqual((s["logged_in"], s["email"], s["plan"], s["error"]), (True, "me@example.com", "max", None))
        self.assertIs(again, s)
        self.assertEqual(calls, [(["/x/claude", "auth", "status"], "")])

    def test_subscription_status_when_api_key_or_logged_out(self):
        chat_agent._SUB_CACHE.update(at=0.0, value=None)
        with mock.patch.object(chat_agent.subprocess, "run", lambda *a, **k: types.SimpleNamespace(
                stdout='{"loggedIn": true, "authMethod": "api_key"}')):
            s = chat_agent.subscription_status(now=2000.0, cli="/x/claude")
        self.assertFalse(s["logged_in"])
        self.assertIn("claude login", s["error"])
        chat_agent._SUB_CACHE.update(at=0.0, value=None)
        with mock.patch.object(chat_agent.subprocess, "run", mock.Mock(side_effect=OSError("boom"))):
            s = chat_agent.subscription_status(now=3000.0, cli="/x/claude")
        self.assertFalse(s["logged_in"])
        self.assertIn("boom", s["error"])
        chat_agent._SUB_CACHE.update(at=0.0, value=None)
        with mock.patch.object(chat_agent.shutil, "which", lambda name: None):
            self.assertEqual(chat_agent.subscription_status(now=4000.0, cli="")["error"], "claude CLI not found")
        chat_agent._SUB_CACHE.update(at=0.0, value=None)

    def test_subscription_turn_is_free_in_the_ledger(self):
        FakeClient.script = staticmethod(lambda o: [delta("ok"), result(total_cost_usd=0.24)])
        events = self.run_stream(key=None, billing="subscription")
        usage = dict(events)["usage"]
        self.assertEqual((usage["billing"], usage["cost_usd"], usage["est_cost_usd"]), ("subscription", 0.0, 0.24))
        self.assertEqual(FakeClient.instances[0].options.env["ANTHROPIC_API_KEY"], "")
        with open(chat_data.LEDGER_FILE) as f:
            import json
            row = json.loads(f.readline())
        self.assertEqual((row["billing"], row["cost_usd"]), ("subscription", 0.0))
        self.assertEqual(usage["spend"]["subscription_turns"], 1)


class TestHelpers(unittest.TestCase):
    def test_tool_summaries(self):
        self.assertEqual(chat_agent.tool_summary("Read", {"file_path": os.path.join(ROOT, "wiki", "q-x.md")}), "read q-x")
        self.assertEqual(chat_agent.tool_summary("Read", {"file_path": "raw/web-clips/a.md"}), "read raw/web-clips/a.md")
        self.assertEqual(chat_agent.tool_summary("Grep", {"pattern": "rank"}), "grep rank")
        self.assertEqual(chat_agent.tool_summary("Glob", {"pattern": "wiki/q-*.md"}), "glob wiki/q-*.md")
        self.assertEqual(chat_agent.tool_summary("Bash", {"command": "python3 -m kb_distillery.ingest resolve old"}), "resolve old")
        self.assertEqual(chat_agent.tool_summary("Bash", {"command": "python3 -m kb_distillery.search.semfind theme t"}), "theme t")
        self.assertTrue(chat_agent.tool_summary("Bash", {"command": "python3 -m kb_distillery.search.query candidates " + "x" * 100}).endswith("…"))
        self.assertEqual(chat_agent.tool_summary("Bash", {"command": 'python3 -m kb_distillery.search.explore_raw find "tensor rank"'}), 'explore find "tensor rank"')
        self.assertEqual(chat_agent.tool_summary("Bash", {"command": "python3 -m kb_distillery.search.explore_raw read raw/web-clips/a.md --pages 1-2"}), "explore read a.md")

    def test_harvest_citations(self):
        idx = {"a": {}, "b": {}}
        self.assertEqual(chat_agent.harvest_citations("see [[a]] and [[b|label]] and [[a]] and [[zz]]", idx), ["a", "b"])
        self.assertEqual(chat_agent.harvest_citations("see [A](a.md) and [B](b.md#why) and [A](a.md) and [Z](zz.md)", idx), ["a", "b"])


if __name__ == "__main__":
    unittest.main()


class TestRunnerWiring(SDKCase):
    def test_flag_off_path_has_no_new_options(self):
        chat_agent.build_options("claude-opus-5-5", "SYS", "sk-x")
        FakeClient.script = staticmethod(lambda o: [result()])
        self.run_stream()
        o = FakeClient.instances[0].options
        for k in ("effort", "skills", "max_budget_usd"):
            self.assertFalse(hasattr(o, k), k)

    def test_effort_and_budget_reach_the_options(self):
        FakeClient.script = staticmethod(lambda o: [result()])
        self.run_stream(effort="high", budget=2.0)
        o = FakeClient.instances[0].options
        self.assertEqual((o.effort, o.max_budget_usd), ("high", 2.0))

    def test_subscription_billing_blanks_the_key(self):
        FakeClient.script = staticmethod(lambda o: [result()])
        events = self.run_stream(key=None, billing="subscription")
        self.assertEqual(FakeClient.instances[0].options.env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(dict(events)["usage"]["billing"], "subscription")

    def test_batch_billing_queues_one_request_and_never_starts_the_sdk(self):
        FakeClient.script = staticmethod(lambda o: [result()])
        with mock.patch("kb_distillery.llm.submit", return_value="bid9") as submit:
            events = self.run_stream(key="sk-test", billing="batch")
        self.assertEqual(submit.call_count, 1)
        self.assertEqual(FakeClient.instances, [])
        self.assertIn("bid9", dict(events)["notice"]["text"])
        self.assertEqual(events[-1][0], "done")

    def test_policy_groups_deny_web_skills_and_unknown(self):
        for tool in ("WebSearch", "WebFetch", "Skill", "Task", "Agent", "Write"):
            self.assertFalse(chat_agent.tool_policy(tool, {}).allow, tool)

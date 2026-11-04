"""Agent-mode web tools and the AskUserQuestion round trip (src/kb_distillery/services/chat_agent.py).

No SDK, no network: the fake SDK of test_chat_agent is reused, DNS is a stub, answers come from a thread.
"""
import asyncio
import threading
import unittest

import pytest

from kb_distillery.services import chat_agent as ca
from tests.services import test_chat_agent as base

PUBLIC = "93.184.216.34"


def resolver(table):
    def resolve(host):
        if host not in table:
            raise OSError("no such host")
        return table[host]
    return resolve


DNS = resolver({"example.com": [PUBLIC], "docs.example.org": ["2606:2800:220:1::1"],
                "rebind.example.com": [PUBLIC, "10.0.0.5"], "meta.example.com": ["169.254.169.254"],
                "intranet.example.com": ["192.168.1.9"], "loop.example.com": ["127.0.0.1"]})


def run_ctx(**kw):
    kw.setdefault("agent_mode", True)
    kw.setdefault("resolve", DNS)
    return ca.RunContext(**kw)


# ── URL policy table ───────────────────────────────────────────────────────

ALLOWED = ["https://example.com/a?b=1", "http://example.com", "https://docs.example.org/x", "https://93.184.216.34/"]
DENIED = [
    "file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "example.com/no-scheme", "", None,
    "http://localhost:8765/api", "http://LOCALHOST./", "http://127.0.0.1/", "http://127.9.9.9:80/", "http://[::1]/",
    "http://169.254.169.254/latest/meta-data", "http://10.1.2.3/", "http://172.16.0.1/", "http://192.168.0.10/",
    "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/",
    "http://printer.local/", "http://db.internal/", "http://app.localhost/",
    "http://rebind.example.com/", "http://meta.example.com/", "http://intranet.example.com/", "http://loop.example.com/",
    "http://unknown-host.example.com/", "http://2130706433/",
]


@pytest.mark.parametrize("url", ALLOWED)
def test_web_fetch_allowed_urls(url):
    d = ca.tool_policy("WebFetch", {"url": url}, run=run_ctx())
    assert d.allow, d.reason


@pytest.mark.parametrize("url", DENIED)
def test_web_fetch_denied_urls(url):
    d = ca.tool_policy("WebFetch", {"url": url}, run=run_ctx(resolve=lambda h: DNS(h) if h != "2130706433" else ["127.0.0.1"]))
    assert not d.allow and d.reason


def test_hostname_is_resolved_once_per_check():
    calls = []
    r = run_ctx(resolve=lambda h: calls.append(h) or [PUBLIC])
    assert ca.tool_policy("WebFetch", {"url": "https://example.com/x"}, run=r).allow
    assert calls == ["example.com"]


def test_web_search_needs_a_query_and_is_allowed_in_agent_mode():
    assert ca.tool_policy("WebSearch", {"query": "tensor rank"}, run=run_ctx()).allow
    assert not ca.tool_policy("WebSearch", {"query": "  "}, run=run_ctx()).allow


def test_flag_off_and_scoped_chat_deny_web_and_agent_ui_tools():
    for tool, inp in (("WebFetch", {"url": "https://example.com"}), ("WebSearch", {"query": "q"}),
                      ("AskUserQuestion", {"questions": []}), ("TodoWrite", {"todos": []})):
        assert not ca.tool_policy(tool, inp).allow                                  # no run context = today's policy
        assert not ca.tool_policy(tool, inp, run=run_ctx(agent_mode=False)).allow
    scope = {"slug": "scope-x", "rows": [], "pages": []}
    for tool, inp in (("WebFetch", {"url": "https://example.com"}), ("WebSearch", {"query": "q"})):
        d = ca.tool_policy(tool, inp, scope, run=run_ctx())
        assert not d.allow and "scoped" in d.reason
    assert ca.tool_policy("TodoWrite", {"todos": []}, run=run_ctx()).allow
    assert ca.tool_policy("AskUserQuestion", {"questions": []}, run=run_ctx()).allow


def test_other_tools_stay_denied_in_agent_mode():
    for tool in ("Write", "Edit", "Task", "Agent", "Skill", "KillShell"):
        assert not ca.tool_policy(tool, {}, run=run_ctx()).allow, tool


# ── per-turn caps (counted by the hook, per run) ───────────────────────────

def call_hook(hook, tool, inp, tid="t"):
    out = asyncio.run(hook({"tool_name": tool, "tool_input": inp}, tid, None))
    return out["hookSpecificOutput"]


def test_fetch_and_search_caps_are_per_run():
    r = run_ctx(web_fetch_cap=2, web_search_cap=1)
    hook = ca.make_hook(run=r)
    fetch = {"url": "https://example.com/p"}
    assert [call_hook(hook, "WebFetch", fetch)["permissionDecision"] for _ in range(3)] == ["allow", "allow", "deny"]
    assert "limit" in call_hook(hook, "WebFetch", fetch)["permissionDecisionReason"]
    assert [call_hook(hook, "WebSearch", {"query": "q"})["permissionDecision"] for _ in range(2)] == ["allow", "deny"]
    other = ca.make_hook(run=run_ctx(web_fetch_cap=2))                               # a new run starts at zero
    assert call_hook(other, "WebFetch", fetch)["permissionDecision"] == "allow"


def test_a_denied_url_does_not_use_up_the_cap():
    r = run_ctx(web_fetch_cap=1)
    hook = ca.make_hook(run=r)
    assert call_hook(hook, "WebFetch", {"url": "http://127.0.0.1/"})["permissionDecision"] == "deny"
    assert call_hook(hook, "WebFetch", {"url": "https://example.com/"})["permissionDecision"] == "allow"


def test_can_use_tool_does_not_count_a_call_the_hook_already_allowed():
    r = run_ctx(web_fetch_cap=1)
    inp = {"url": "https://example.com/"}
    call_hook(ca.make_hook(run=r), "WebFetch", inp)
    with base.mock.patch.dict(base.sys.modules, {"claude_agent_sdk": base.fake_sdk()}):
        cb = ca.make_can_use_tool(run=r)
        assert asyncio.run(cb("WebFetch", inp, None)).behavior == "allow"
        assert asyncio.run(cb("WebFetch", inp, None)).behavior == "deny"             # a second, unseen call hits the cap
    assert r.fetches == 1


def test_cap_defaults_and_kb_toml_override(monkeypatch):
    class Cfg:
        def section(self, name):
            return {"web_fetch_cap": 3, "web_search_cap": "x"} if name == "agent" else {}
    monkeypatch.setattr(ca.kbconfig, "current", lambda: Cfg())
    assert ca._agent_cap("web_fetch_cap", 20) == 3
    assert ca._agent_cap("web_search_cap", 10) == 10                                 # not an int: default
    monkeypatch.setattr(ca.kbconfig, "current", lambda: None)
    assert ca._agent_cap("web_fetch_cap", 20) == 20


# ── AskUserQuestion round trip ─────────────────────────────────────────────

QUESTIONS = [{"question": "Which scope?", "header": "Scope", "multiSelect": False,
              "options": [{"label": "Wiki only", "description": ""}, {"label": "Wiki and web", "description": ""}]}]


def ask_round_trip(answer, session="s1", timeout=5.0, answer_session="s1"):
    """Run the hook on an AskUserQuestion; `answer(registry, ask_id)` plays the HTTP side from another thread."""
    events = []
    reg = ca.AskRegistry()
    r = run_ctx(emit=events.append, session=session, asks=reg, ask_timeout=timeout)
    hook = ca.make_hook(run=r)

    async def go():
        task = asyncio.create_task(hook({"tool_name": "AskUserQuestion", "tool_input": {"questions": QUESTIONS}}, "toolu_1", None))
        for _ in range(500):
            if events:
                break
            await asyncio.sleep(0.01)
        if answer:
            t = threading.Thread(target=answer, args=(reg, events[0][1]["id"]))
            t.start()
            t.join()
        return await task

    out = asyncio.run(go())
    return out["hookSpecificOutput"], events, r


def test_ask_round_trip_injects_the_answer_through_updated_input():
    res = {}
    spec, events, r = ask_round_trip(lambda reg, i: res.setdefault("ok", reg.answer("s1", i, {"Which scope?": "Wiki and web"})))
    assert events == [("ask", {"id": "toolu_1", "questions": QUESTIONS})]
    assert res["ok"] is True
    assert spec["permissionDecision"] == "allow"
    assert spec["updatedInput"]["answers"] == {"Which scope?": "Wiki and web"}
    assert spec["updatedInput"]["questions"] == QUESTIONS
    assert not r.pending_asks


def test_ask_times_out_with_a_deny_reason():
    spec, events, r = ask_round_trip(None, timeout=0.05)
    assert events[0][0] == "ask"
    assert spec["permissionDecision"] == "deny" and "did not answer" in spec["permissionDecisionReason"]
    assert not r.pending_asks


def test_ask_cancelled_when_the_stream_closes():
    spec, _, _ = ask_round_trip(lambda reg, i: reg.cancel([i]))
    assert spec["permissionDecision"] == "deny" and "closed" in spec["permissionDecisionReason"]


def test_answer_from_another_session_or_unknown_id_is_refused():
    out = {}

    def wrong(reg, i):
        out["other"] = reg.answer("someone-else", i, {"q": "a"})
        out["unknown"] = reg.answer("s1", "nope", {"q": "a"})
        out["right"] = reg.answer("s1", i, {"q": "a"})
        out["again"] = reg.answer("s1", i, {"q": "a"})
    spec, _, _ = ask_round_trip(wrong)
    assert out == {"other": False, "unknown": False, "right": True, "again": False}
    assert spec["permissionDecision"] == "allow"


def test_can_use_tool_reuses_the_answer_the_hook_injected():
    spec, _, r = ask_round_trip(lambda reg, i: reg.answer("s1", i, {"Which scope?": "Wiki only"}))
    with base.mock.patch.dict(base.sys.modules, {"claude_agent_sdk": base.fake_sdk()}):
        res = asyncio.run(ca.make_can_use_tool(run=r)("AskUserQuestion", spec["updatedInput"], None))
    assert res.behavior == "allow" and res.updated_input["answers"] == {"Which scope?": "Wiki only"}


def test_ask_denied_without_agent_mode():
    hook = ca.make_hook(run=run_ctx(agent_mode=False))
    assert call_hook(hook, "AskUserQuestion", {"questions": QUESTIONS})["permissionDecision"] == "deny"


# ── citations ──────────────────────────────────────────────────────────────

def test_sources_carry_kind_and_web_hits_come_from_fetch_and_search():
    state = ca.TurnState(index={"tensor-rank": {"summary": "s"}})
    ev = ca.map_message(base.read_tool("tensor-rank"), state)
    assert ev[-1][1]["hits"] == [{"kind": "wiki", "slug": "tensor-rank", "score": 1, "summary": "s", "in_context": False}]

    fetch = base.AssistantMessage(content=[base.ToolUseBlock(id="w1", name="WebFetch", input={"url": "https://example.com/a", "prompt": "p"})])
    ev = dict(ca.map_message(fetch, state))
    assert ev["tool"]["summary"] == "fetch https://example.com/a"
    assert "sources" not in ev                                                       # cited only after the fetch succeeds
    done = base.UserMessage(content=[base.ToolResultBlock(tool_use_id="w1", content="page")])
    ev = dict(ca.map_message(done, state))
    web = [h for h in ev["sources"]["hits"] if h["kind"] == "web"]
    assert web == [{"kind": "web", "url": "https://example.com/a", "title": "example.com", "score": 1, "summary": "", "in_context": False}]
    assert ev["sources"]["new"] == ["tensor-rank"]                                   # web hits never enter `new`

    search = base.AssistantMessage(content=[base.ToolUseBlock(id="w2", name="WebSearch", input={"query": "rank"})])
    ca.map_message(search, state)
    text = 'Web search results for query: "rank"\n\nLinks: [{"title": "Rank (wiki)", "url": "https://en.example.org/Rank"}, {"title": "bad", "url": "ftp://x"}]\n\nSummary'
    result = base.UserMessage(content=[base.ToolResultBlock(tool_use_id="w2", content=[{"type": "text", "text": text}])])
    ev = dict(ca.map_message(result, state))
    urls = [h["url"] for h in ev["sources"]["hits"] if h["kind"] == "web"]
    assert urls == ["https://example.com/a", "https://en.example.org/Rank"]
    assert {h["url"]: h["title"] for h in ev["sources"]["hits"] if h["kind"] == "web"}["https://en.example.org/Rank"] == "Rank (wiki)"


def test_a_malformed_search_result_adds_nothing():
    assert ca.search_links("no links here") == [] and ca.search_links("Links: [not json]\n") == [] and ca.search_links(None) == []


# ── tool set and the whole stream, flag on / off ───────────────────────────

def test_agent_request_tool_sets():
    off = ca.agent_request("q", "m", "s")
    assert set(off.tools) == {"Read", "Grep", "Glob", "Bash"} and "WebFetch" in off.disallowed
    on = ca.agent_request("q", "m", "s", agent_mode=True)
    assert set(ca.AGENT_MODE_TOOLS) <= set(on.tools) and not set(ca.AGENT_MODE_TOOLS) & set(on.disallowed)
    assert "Write" in on.disallowed
    scoped = ca.agent_request("q", "m", "s", scope={"slug": "x"}, agent_mode=True)
    assert "WebFetch" not in scoped.tools and "WebFetch" in scoped.disallowed and "AskUserQuestion" in scoped.tools


class TestStream(base.SDKCase):
    def test_flag_off_is_today(self):
        base.FakeClient.script = staticmethod(lambda o: [base.result()])
        events = self.run_stream(agent_mode=False)
        o = base.FakeClient.instances[0].options
        self.assertEqual(set(o.tools), {"Read", "Grep", "Glob", "Bash"})
        self.assertIn("WebFetch", o.disallowed_tools)
        self.assertNotIn("Web tools", o.system_prompt)
        self.assertNotIn("ask", [e for e, _ in events])
        self.assertEqual(asyncio.run(o.hooks["PreToolUse"][0].hooks[0](
            {"tool_name": "WebFetch", "tool_input": {"url": "https://example.com"}}, "t", None))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_flag_on_exposes_the_tools_and_wires_the_run(self):
        base.FakeClient.script = staticmethod(lambda o: [base.result()])
        self.run_stream(agent_mode=True)
        o = base.FakeClient.instances[0].options
        self.assertTrue(set(ca.AGENT_MODE_TOOLS) <= set(o.tools))
        self.assertIn("Web tools", o.system_prompt)
        hook = o.hooks["PreToolUse"][0].hooks[0]
        out = asyncio.run(hook({"tool_name": "WebFetch", "tool_input": {"url": "http://127.0.0.1/"}}, "t", None))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_ask_event_reaches_the_stream_and_the_answer_reaches_the_tool(self):
        got = {}

        class Client(base.FakeClient):
            async def receive_response(self):
                hook = self.options.hooks["PreToolUse"][0].hooks[0]
                got["out"] = await hook({"tool_name": "AskUserQuestion", "tool_input": {"questions": QUESTIONS}}, "toolu_7", None)
                yield base.result()
        sdk = base.fake_sdk()
        sdk.ClaudeSDKClient = Client
        events = []
        with base.mock.patch.dict(base.sys.modules, {"claude_agent_sdk": sdk}):
            def answer_when_asked():
                for _ in range(500):
                    if any(e == "ask" for e, _ in events):
                        break
                    threading.Event().wait(0.01)
                ca.ASKS.answer("", "toolu_7", {"Which scope?": "Wiki only"})
            t = threading.Thread(target=answer_when_asked)
            t.start()
            for ev in ca.stream_agent("q?", model="claude-sonnet-5-5", system="s", key="k", log=lambda s: None, agent_mode=True):
                events.append(ev)
            t.join()
        self.assertEqual([e for e, _ in events if e == "ask"], ["ask"], events)
        self.assertEqual(got["out"]["hookSpecificOutput"]["updatedInput"]["answers"], {"Which scope?": "Wiki only"})


if __name__ == "__main__":
    unittest.main()


def test_empty_session_cannot_answer_a_session_bound_ask():
    out = {}
    spec, _, _ = ask_round_trip(lambda reg, i: (out.setdefault("empty", reg.answer("", i, {"q": "a"})),
                                                out.setdefault("ok", reg.answer("s1", i, {"q": "a"}))))
    assert out == {"empty": False, "ok": True} and spec["permissionDecision"] == "allow"


def test_hook_timeout_outlasts_the_ask_timeout():
    from kb_distillery.llm import agent as llm_agent
    assert llm_agent.HOOK_TIMEOUT > ca.ASK_TIMEOUT_SECONDS
    o = ca.build_options("claude-sonnet-5-5", "S", "k", run=run_ctx())
    assert o.hooks["PreToolUse"][0].timeout == llm_agent.HOOK_TIMEOUT

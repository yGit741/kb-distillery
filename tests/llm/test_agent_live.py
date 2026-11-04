"""llm.agent with a `live` handle (a message queued mid-turn gets its own turn) and thinking options. SDK mocked."""
import asyncio
import sys
import types

import pytest

from kb_distillery.llm import agent

ResultMessage = type("ResultMessage", (), {"__init__": lambda self, **kw: self.__dict__.update(
    {"is_error": False, "result": "ok", "total_cost_usd": 0.1, "usage": {"input_tokens": 1}, **kw})})


class Opts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Client:
    """receive_response yields one scripted block per call, each ending in a ResultMessage."""
    blocks = []

    def __init__(self, options):
        self.options, self.prompts, self.calls = options, [], 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, prompt):
        self.prompts.append(prompt)

    async def interrupt(self):
        pass

    async def receive_response(self):
        block = Client.blocks[self.calls]
        self.calls += 1
        for m in block:
            yield m


class Live:
    def __init__(self, pending):
        self.pending, self.attached = pending, None

    def attach(self, client, loop):
        self.attached = (client, loop)

    def take_pending(self):
        if self.pending:
            self.pending -= 1
            return True
        return False


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch):
    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions, mod.ClaudeSDKClient = Opts, Client
    mod.HookMatcher = lambda matcher=None, hooks=None, timeout=None: (matcher, hooks)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", mod)
    monkeypatch.delenv("KB_LLM_BACKEND", raising=False)
    monkeypatch.delenv("NODE_EXTRA_CA_CERTS", raising=False)


def run(req, **kw):
    async def go():
        return [e async for e in agent.stream(req, "subscription", policy_hook=lambda *a: None,
                                              can_use_tool=lambda *a: None, **kw)]
    return asyncio.run(go())


def test_a_queued_message_gets_its_own_turn_and_one_final_result():
    Client.blocks = [["a", ResultMessage(result="first")], ["b", ResultMessage(result="second")]]
    live, spent = Live(pending=1), []
    ev = run(agent.AgentRequest("q"), live=live, usage_sink=lambda m, u, est, b: spent.append(est) or est)
    msgs = [d for k, d in ev if k == "message"]
    assert [m for m in msgs if isinstance(m, str)] == ["a", "b"]
    assert [d["result"].result for k, d in ev if k == "result"] == ["second"]
    assert len(spent) == 2 and live.attached is not None          # the first turn's cost was recorded too


def test_without_a_queued_message_there_is_one_turn():
    Client.blocks = [[ResultMessage()]]
    ev = run(agent.AgentRequest("q"), live=Live(pending=0))
    assert [k for k, _ in ev].count("result") == 1


def test_thinking_budget_scales_with_effort():
    Client.blocks = [[ResultMessage()]]
    holder = {}
    orig = Client.__init__
    Client.__init__ = lambda self, o: (orig(self, o), holder.update(o=o))[0]
    try:
        run(agent.AgentRequest("q", effort="max", thinking=True))
        assert holder["o"].thinking == {"type": "enabled", "budget_tokens": 32000, "display": "summarized"}
        run(agent.AgentRequest("q"))
        assert not hasattr(holder["o"], "thinking")
    finally:
        Client.__init__ = orig

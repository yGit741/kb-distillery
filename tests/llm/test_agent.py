"""kb_distillery.llm.agent: backend selection, options and the fallbacks, with the SDK mocked (no network)."""
import asyncio
import sys
import types

import pytest

from kb_distillery import llm
from kb_distillery.llm import agent


class Opts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Matcher:
    def __init__(self, matcher=None, hooks=None):
        self.hooks = hooks or []


ResultMessage = type("ResultMessage", (), {"__init__": lambda self, **kw: self.__dict__.update(
    {"is_error": False, "result": None, "total_cost_usd": 0.5, "usage": {"input_tokens": 3}, **kw})})
CLINotFoundError = type("CLINotFoundError", (Exception,), {})


class Client:
    instances = []
    script = staticmethod(lambda o: [ResultMessage()])

    def __init__(self, options):
        self.options = options
        Client.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, prompt):
        self.prompt = prompt

    async def interrupt(self):
        pass

    async def receive_response(self):
        for m in Client.script(self.options):
            yield m


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch):
    Client.instances = []
    Client.script = staticmethod(lambda o: [ResultMessage()])
    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions, mod.HookMatcher, mod.ClaudeSDKClient = Opts, Matcher, Client
    mod.AgentDefinition = lambda **kw: ("agent", kw)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", mod)
    monkeypatch.delenv("KB_LLM_BACKEND", raising=False)
    monkeypatch.delenv("NODE_EXTRA_CA_CERTS", raising=False)


def run(req, backend=None, **kw):
    async def go():
        return [e async for e in agent.stream(req, backend, policy_hook=lambda *a: None,
                                              can_use_tool=lambda *a: None, **kw)]
    return asyncio.run(go())


def kinds(events):
    return [k for k, _ in events]


def test_subscription_is_the_default_and_blanks_the_key():
    ev = run(agent.AgentRequest("q"), key="sk-ignored")
    assert Client.instances[0].options.env["ANTHROPIC_API_KEY"] == ""
    assert dict(ev)["result"]["billing"] == "subscription"


def test_env_selects_backend(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "api")
    ev = run(agent.AgentRequest("q"), key="sk-env")
    assert Client.instances[0].options.env["ANTHROPIC_API_KEY"] == "sk-env"
    assert dict(ev)["result"]["billing"] == "api"


def test_api_uses_the_key_and_the_usage_sink():
    seen = []
    ev = run(agent.AgentRequest("q", model="opus"), "api", key="sk-x",
             usage_sink=lambda m, u, est, b: seen.append((m, u, est, b)) or 1.25)
    assert Client.instances[0].options.env["ANTHROPIC_API_KEY"] == "sk-x"
    assert seen == [("claude-opus-5-5", {"input_tokens": 3}, 0.5, "api")]
    assert dict(ev)["result"]["cost_usd"] == 1.25


def test_api_without_a_key_errors(monkeypatch):
    monkeypatch.setattr(llm, "api_key", lambda: None)
    ev = run(agent.AgentRequest("q"), "api")
    assert kinds(ev) == ["error"] and Client.instances == []


def test_batch_queues_a_toolless_request(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: sent.append(reqs) or "bid1")
    ev = run(agent.AgentRequest("why?", model="sonnet", system="SYS", effort="high"), "batch")
    assert kinds(ev) == ["pending"] and ev[0][1]["batch_id"] == "bid1"
    assert Client.instances == []                              # no SDK session for a queued question
    (r,) = sent[0]
    assert (r.prompt, r.system, r.model, r.effort) == ("why?", "SYS", "sonnet", "high")


def test_unknown_backend_raises():
    with pytest.raises(llm.LLMError):
        run(agent.AgentRequest("q"), "bogus")


def test_options_carry_effort_model_budget_and_skills():
    run(agent.AgentRequest("q", model="haiku", effort="xhigh", budget=2.5, skills=("deep-research",),
                           tools=("Read",), disallowed=("Write",), system="S", cwd="/kb"))
    o = Client.instances[0].options
    assert (o.model, o.effort, o.max_budget_usd, o.skills) == ("claude-haiku-5-5", "xhigh", 2.5, ["deep-research"])
    assert (o.tools, o.disallowed_tools, o.system_prompt, o.cwd) == (["Read"], ["Write"], "S", "/kb")
    assert o.setting_sources == [] and o.permission_mode == "default"


def test_options_omit_unset_extras():
    run(agent.AgentRequest("q"))
    o = Client.instances[0].options
    assert not any(hasattr(o, k) for k in ("effort", "skills", "max_budget_usd", "cli_path"))


def test_bad_effort_is_rejected():
    with pytest.raises(llm.LLMError):
        run(agent.AgentRequest("q", effort="turbo"))


def test_resume_failure_restarts_with_the_fresh_prompt():
    def script(o):
        if o.resume:
            raise RuntimeError("No conversation found with session ID")
        return [ResultMessage()]
    Client.script = staticmethod(script)
    ev = run(agent.AgentRequest("q", session="old", fresh_prompt="history q"))
    assert "notice" in kinds(ev) and kinds(ev)[-1] == "result"
    assert [c.prompt for c in Client.instances] == ["q", "history q"]


def test_cli_fallback(monkeypatch):
    def script(o):
        if not hasattr(o, "cli_path"):
            raise CLINotFoundError("missing")
        return [ResultMessage()]
    Client.script = staticmethod(script)
    monkeypatch.setattr(agent.shutil, "which", lambda n: "/usr/bin/claude")
    assert kinds(run(agent.AgentRequest("q")))[-1] == "result"
    assert Client.instances[1].options.cli_path == "/usr/bin/claude"


def test_error_result_and_sdk_error():
    Client.script = staticmethod(lambda o: [ResultMessage(is_error=True, result="boom")])
    assert run(agent.AgentRequest("q"))[-1] == ("error", {"error": "agent: boom"})
    Client.script = staticmethod(lambda o: (_ for _ in ()).throw(RuntimeError("down")))
    assert run(agent.AgentRequest("q"))[-1] == ("error", {"error": "agent: down"})


def test_ca_bundle_uses_injected_pem(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    p = agent.ca_bundle_path(str(tmp_path), lambda: "PEM")
    assert p == str(tmp_path / "ca-roots.pem") and (tmp_path / "ca-roots.pem").read_text() == "PEM"
    assert agent.ca_bundle_path(str(tmp_path), lambda: "") == p                 # fresh file reused
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/x.pem")
    assert agent.ca_bundle_path(str(tmp_path), None) == "/x.pem"


def test_layer_rule_no_service_imports():
    src = open(agent.__file__, encoding="utf-8").read()
    assert not any(f"kb_distillery.{m}" in src for m in ("services", "server", "search", "config"))


def test_options_carry_plugins_and_subagents():
    run(agent.AgentRequest("q", plugins=("/cache/plug",), agents={"helper": {"description": "d", "prompt": "p", "tools": ["Read"]}}))
    o = Client.instances[0].options
    assert o.plugins == [{"type": "local", "path": "/cache/plug"}]
    assert o.agents == {"helper": ("agent", {"description": "d", "prompt": "p", "tools": ["Read"]})}
    assert o.setting_sources == []


def test_options_without_plugins_or_subagents_do_not_pass_them():
    run(agent.AgentRequest("q"))
    o = Client.instances[0].options
    assert not hasattr(o, "plugins") and not hasattr(o, "agents")

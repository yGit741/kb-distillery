"""llm.resolve: the one (provider, backend) pair; provider config from env, kb.toml and keys. Fakes only."""
import types

import pytest

from kb_distillery import llm
from kb_distillery.llm import __main__ as cli


@pytest.fixture
def world(monkeypatch):
    """Nothing set up: no env, no kb, no keys, claude not logged in. Tests flip `w.sub`, `w.keys`, `w.kb`."""
    for v in ("KB_LLM_PROVIDER", "KB_LLM_BACKEND"):
        monkeypatch.delenv(v, raising=False)
    w = types.SimpleNamespace(sub=False, claude_key=False, keys={"openai": False, "gemini": False}, kb=None)
    monkeypatch.setattr(llm, "_subscription", lambda: {"ok": w.sub, "why": "", "fix": ""})
    monkeypatch.setattr(llm, "api_key", lambda: "k" if w.claude_key else None)
    for name in ("openai", "gemini"):
        monkeypatch.setattr(llm.providers.get(name), "availability", lambda n=name: (w.keys[n], ""))
    from kb_distillery.config import kb as kbconfig
    monkeypatch.setattr(kbconfig, "current", lambda: w.kb)
    return w


def kb_with(provider):
    data = {"llm": {"provider": provider}} if provider else {}
    return types.SimpleNamespace(path="/kb/kb.toml", section=lambda n: data.get(n, {}))


def test_default_is_claude_subscription_when_logged_in(world):
    world.sub = True
    world.keys["openai"] = True
    assert llm.resolve() == ("claude", "subscription")


def test_claude_api_when_not_logged_in_but_keyed(world):
    world.claude_key = True
    world.keys["gemini"] = True
    assert llm.resolve() == ("claude", "api")


def test_first_other_provider_with_a_key(world):
    world.keys.update(openai=False, gemini=True)
    assert llm.resolve() == ("gemini", "api")
    world.keys["openai"] = True
    assert llm.resolve() == ("openai", "api")


def test_nothing_set_up_falls_back_to_claude_api(world):
    assert llm.resolve() == ("claude", "api")


def test_precedence_arg_env_kb(world, monkeypatch):
    world.sub = True
    world.kb = kb_with("gemini")
    assert llm.resolve() == ("gemini", "api")
    monkeypatch.setenv("KB_LLM_PROVIDER", "openai")
    assert llm.resolve() == ("openai", "api")
    assert llm.resolve("claude") == ("claude", "subscription")


def test_non_claude_rejects_subscription_and_batch(world, monkeypatch):
    for b in ("subscription", "batch"):
        with pytest.raises(llm.LLMError, match="api backend only"):
            llm.resolve("openai", b)
    monkeypatch.setenv("KB_LLM_BACKEND", "batch")
    world.kb = kb_with("gemini")
    with pytest.raises(llm.LLMError, match="Claude-only"):
        llm.resolve()
    assert llm.resolve("openai", "api") == ("openai", "api")


def test_explicit_backend_is_kept_for_claude(world):
    world.sub = True
    assert llm.resolve(backend="batch") == ("claude", "batch")
    assert llm.resolve("claude", "api") == ("claude", "api")


def test_unknown_provider_in_kb_toml_names_the_file(world):
    world.kb = kb_with("mistral")
    with pytest.raises(llm.LLMError, match=r"/kb/kb.toml.*mistral"):
        llm.resolve()
    with pytest.raises(llm.LLMError, match="unknown provider"):
        llm.resolve("mistral")


def test_cli_ask_uses_resolve(world, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(llm, "ask", lambda prompt, **kw: seen.update(kw) or llm.Result(id="r0", text="ok"))
    world.kb = kb_with("openai")
    assert cli.main(["ask", "hi"]) == 0
    assert seen["provider"] == "openai" and seen["backend"] == "api" and seen["model"] == "gpt-4.1-mini"
    with pytest.raises(llm.LLMError):
        cli.main(["ask", "hi", "--provider", "gemini", "--backend", "batch"])

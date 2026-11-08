"""Provider adapters (OpenAI, Gemini, Claude) with faked HTTP: shapes, usage and cost, resolution, refusals."""
import pytest

from kb_distillery import llm
from kb_distillery.config import userdir
from kb_distillery.llm import providers
from kb_distillery.llm.providers import anthropic as p_anthropic, gemini as p_gemini, openai as p_openai


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for v in ("KB_LLM_BACKEND", "KB_LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "no-anthropic-key"))
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setattr(llm, "_http", _boom)
    monkeypatch.setattr(llm, "_cli", _boom)
    monkeypatch.setattr(providers, "post_json", _boom)


def _boom(*a, **k):
    raise AssertionError("unexpected network or claude -p call")


class Fake:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body, timeout=600):
        self.calls.append({"url": url, "headers": headers, "body": body})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


OPENAI_OK = {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "prompt_tokens_details": {"cached_tokens": 400}}}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "hel"}, {"text": "lo"}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 150, "thoughtsTokenCount": 50,
                               "cachedContentTokenCount": 400}}


def test_registry():
    assert providers.PROVIDERS == ("claude", "openai", "gemini") == llm.PROVIDERS
    assert providers.get("openai") is p_openai and providers.get("claude") is p_anthropic
    with pytest.raises(ValueError):
        providers.get("mistral")


def test_provider_resolution(monkeypatch):
    assert llm.resolve_provider() == "claude"
    monkeypatch.setenv("KB_LLM_PROVIDER", "Gemini")
    assert llm.resolve_provider() == "gemini"
    assert llm.resolve_provider("openai") == "openai"
    with pytest.raises(llm.LLMError, match="unknown provider"):
        llm.resolve_provider("mistral")


def test_openai_request_usage_and_cost(monkeypatch):
    fake = Fake(OPENAI_OK)
    monkeypatch.setattr(providers, "post_json", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")
    r = llm.ask("q", backend="api", provider="openai", model="gpt-4.1-mini", system="sys", max_tokens=77)
    assert r.ok and r.text == "hello" and r.model == "gpt-4.1-mini" and r.backend == "api"
    c = fake.calls[0]
    assert c["url"] == "https://api.openai.com/v1/chat/completions" and c["headers"]["authorization"] == "Bearer sk-oa"
    assert c["body"] == {"model": "gpt-4.1-mini", "max_completion_tokens": 77,
                         "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]}
    assert r.usage == {"input_tokens": 600, "output_tokens": 200, "cache_read_input_tokens": 400}
    assert r.usd == pytest.approx((600 * 0.40 + 400 * 0.10 + 200 * 1.60) / 1e6)


def test_openai_stop_reasons(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    cut = {"choices": [{"message": {"content": "half"}, "finish_reason": "length"}], "usage": {}}
    monkeypatch.setattr(providers, "post_json", Fake(cut))
    r = llm.ask("q", backend="api", provider="openai", model="gpt-4.1")
    assert r.text == "half" and "cut at max_tokens" in r.error
    refused = {"choices": [{"message": {"content": None, "refusal": "no"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(providers, "post_json", Fake(refused))
    assert "refused" in llm.ask("q", backend="api", provider="openai", model="gpt-4.1").error


def test_gemini_request_usage_and_cost(monkeypatch):
    fake = Fake(GEMINI_OK)
    monkeypatch.setattr(providers, "post_json", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    r = llm.ask("q", backend="api", provider="gemini", model="gemini-2.5-flash", system="sys", max_tokens=9)
    assert r.ok and r.text == "hello" and r.model == "gemini-2.5-flash"
    c = fake.calls[0]
    assert c["url"] == ("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
                        "?key=g-key")
    assert c["body"]["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert c["body"]["generationConfig"] == {"maxOutputTokens": 9}
    assert r.usage == {"input_tokens": 600, "output_tokens": 200, "cache_read_input_tokens": 400}
    assert r.usd == pytest.approx((600 * 0.30 + 400 * 0.075 + 200 * 2.50) / 1e6)


def test_gemini_error_never_echoes_the_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-secret")
    monkeypatch.setattr(providers, "post_json", Fake(llm.HTTPFail(400, "bad key g-secret")))
    r = llm.ask("q", backend="api", provider="gemini", model="gemini-2.5-pro")
    assert not r.ok and "g-secret" not in r.error


def test_gemini_block_and_empty(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(providers, "post_json", Fake({"promptFeedback": {"blockReason": "SAFETY"}}))
    assert llm.ask("q", backend="api", provider="gemini", model="gemini-2.5-pro").error == "refused: SAFETY"


def test_transient_errors_retry_then_succeed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fake = Fake(llm.HTTPFail(429, "slow down"), llm.HTTPFail(0, "down"), OPENAI_OK)
    monkeypatch.setattr(providers, "post_json", fake)
    assert llm.ask("q", backend="api", provider="openai", model="gpt-4.1").ok and len(fake.calls) == 3


def test_client_errors_do_not_retry(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fake = Fake(llm.HTTPFail(401, "bad key"))
    monkeypatch.setattr(providers, "post_json", fake)
    r = llm.ask("q", backend="api", provider="openai", model="gpt-4.1")
    assert not r.ok and "401" in r.error and len(fake.calls) == 1


def test_missing_key_fails_without_network(monkeypatch):
    for prov, model in (("openai", "gpt-4.1"), ("gemini", "gemini-2.5-pro")):
        r = llm.ask("q", backend="api", provider=prov, model=model)
        assert not r.ok and "no API key" in r.error


def test_key_file(monkeypatch):
    import os
    os.makedirs(userdir.config_dir(), exist_ok=True)
    with open(userdir.path("openai_key"), "w") as f:
        f.write(" sk-file \n")
    fake = Fake(OPENAI_OK)
    monkeypatch.setattr(providers, "post_json", fake)
    assert llm.ask("q", backend="api", provider="openai", model="gpt-4.1").ok
    assert fake.calls[0]["headers"]["authorization"] == "Bearer sk-file"


def test_env_provider_default(monkeypatch):
    monkeypatch.setenv("KB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(providers, "post_json", Fake(OPENAI_OK))
    assert llm.ask("q", backend="api", model="gpt-4.1-nano").ok


@pytest.mark.parametrize("backend", ["subscription", "batch"])
@pytest.mark.parametrize("prov,model", [("openai", "gpt-4.1"), ("gemini", "gemini-2.5-flash")])
def test_non_claude_refuses_subscription_and_batch(backend, prov, model):
    with pytest.raises(llm.LLMError, match="api backend only"):
        llm.ask("q", backend=backend, provider=prov, model=model)


def test_model_must_match_provider():
    with pytest.raises(llm.LLMError, match="claude model"):
        llm.ask("q", backend="api", provider="openai", model="haiku")
    with pytest.raises(llm.LLMError, match="openai model"):
        llm.ask("q", backend="api", model="gpt-4.1")


@pytest.mark.parametrize("prov,model", [("openai", "gpt-4.1"), ("gemini", "gemini-2.5-pro")])
def test_images_need_claude(tmp_path, prov, model):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    with pytest.raises(llm.LLMError, match="images need the claude provider"):
        llm.ask("q", backend="api", provider=prov, model=model, images=(str(img),))
    with pytest.raises(llm.LLMError, match="images need the claude provider"):   # the adapters refuse on their own too
        providers.get(prov).complete(llm.Request(prompt="q", images=(str(img),)), model, "k")


def test_claude_unchanged_through_adapter(monkeypatch):
    seen = []

    def http(method, url, key, body=None, timeout=300):
        seen.append((method, url, key))
        import json
        return json.dumps({"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                           "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()
    monkeypatch.setattr(llm, "_http", http)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-a")
    r = llm.ask("q", backend="api", provider="claude")
    assert r.ok and seen == [("POST", "https://api.anthropic.com/v1/messages", "sk-a")]


def test_prices_cover_every_provider_and_cost_works():
    for m in ("gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
        assert m in llm.PRICES
        assert llm.cost(m, {"input_tokens": 1_000_000}) == pytest.approx(llm.PRICES[m]["in"])
        assert llm.cost(m, {"output_tokens": 1_000_000}) == pytest.approx(llm.PRICES[m]["out"])
        assert llm.model_provider(m) == ("openai" if m.startswith("gpt") else "gemini")
    assert llm.model_provider("haiku") == "claude"


def test_availability_without_keys(monkeypatch):
    monkeypatch.setattr(llm, "_which", lambda n: None)
    a = llm.availability()
    assert set(a) == {"subscription", "api", "batch", "providers"}
    assert set(a["providers"]) == set(llm.PROVIDERS)
    for p in a["providers"].values():
        assert not p["ok"] and p["why"] and p["fix"]
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert llm.availability()["providers"]["gemini"]["ok"]
    assert not llm.availability()["providers"]["openai"]["ok"]


def test_cli_provider_flag(monkeypatch, capsys):
    from kb_distillery.llm import __main__ as cli
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(providers, "post_json", Fake(OPENAI_OK))
    assert cli.main(["ask", "hi", "--provider", "openai"]) == 0      # api backend and small model picked for it
    assert '"model": "gpt-4.1-mini"' in capsys.readouterr().out
    monkeypatch.setenv("KB_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(providers, "post_json", Fake(GEMINI_OK))
    assert cli.main(["ask", "hi"]) == 0
    assert '"model": "gemini-2.5-flash"' in capsys.readouterr().out

"""Model tiers: (provider, tier) -> model from llm.toml or the built-ins; Request.model may be a tier. Fakes only."""
import pytest

from kb_distillery import llm


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    for v in ("KB_LLM_PROVIDER", "KB_LLM_BACKEND"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(llm, "TIERS_FILE", str(tmp_path / "llm.toml"))
    monkeypatch.setattr(llm, "PRICES", dict(llm.PRICES))
    return tmp_path / "llm.toml"


def test_builtin_map_covers_every_provider_and_tier_with_priced_models():
    for prov in llm.PROVIDERS:
        for tier in llm.TIERS:
            m = llm.tier_model(prov, tier)
            assert m in llm.PRICES and llm.model_provider(m) == prov
    assert llm.tier_model("claude", "light") == "claude-haiku-5-5"
    assert llm.tier_model("claude", "strong") == "claude-opus-5-5"


def test_file_overrides_and_adds_prices(clean):
    clean.write_text('[claude]\nstandard = "opus"\n[openai]\nstrong = "gpt-5"\n[prices."gpt-5"]\nin = 1.0\nout = 8.0\n')
    assert llm.tier_model("claude", "standard") == "claude-opus-5-5"
    assert llm.tier_model("claude", "light") == "claude-haiku-5-5"        # untouched tiers keep the built-in
    assert llm.tier_model("openai", "strong") == "gpt-5" and llm.PRICES["gpt-5"]["out"] == 8.0


def test_bad_file_or_values_raise(clean):
    with pytest.raises(llm.LLMError, match="unknown tier"):
        llm.tier_model("claude", "huge")
    clean.write_text('[claude]\nlight = "gpt-4.1"\n')
    with pytest.raises(llm.LLMError, match="not a claude model"):
        llm.tier_model("claude", "light")
    clean.write_text('[claude]\nlight = "mystery-1"\n')
    with pytest.raises(llm.LLMError, match="no price"):
        llm.tier_model("claude", "light")
    clean.write_text("[claude\n")
    with pytest.raises(llm.LLMError, match="llm.toml"):
        llm.tier_model("claude", "light")


def test_normalize_resolves_a_tier_for_the_requests_provider(monkeypatch):
    a, b, c = llm.normalize([llm.Request("x", model="light"), llm.Request("x", model="light", provider="openai"),
                             llm.Request("x", model="strong", provider="gemini")])
    assert (a.provider, a.model) == ("claude", "claude-haiku-5-5")
    assert (b.provider, b.model) == ("openai", "gpt-4.1-nano")
    assert (c.provider, c.model) == ("gemini", "gemini-2.5-pro")
    monkeypatch.setenv("KB_LLM_PROVIDER", "openai")
    assert llm.normalize([llm.Request("x", model="standard")])[0].model == "gpt-4.1-mini"


def test_model_id_and_cost_accept_tiers():
    assert llm.model_id("standard") == "claude-sonnet-5-5"
    assert llm.cost("light", {"input_tokens": 1_000_000}) == 0.10


def test_tier_does_not_change_the_backend(monkeypatch):
    monkeypatch.setattr(llm, "_subscription", lambda: {"ok": True, "why": "", "fix": ""})
    assert llm.resolve("claude", "batch") == ("claude", "batch")
    with pytest.raises(llm.LLMError):
        llm.resolve("openai", "batch")


def test_malformed_price_row_names_the_file(clean):
    clean.write_text('[prices."gpt-5"]\nin = 1.0\n')
    with pytest.raises(llm.LLMError, match="needs numeric in and out"):
        llm.tier_model("claude", "light")


def test_file_is_parsed_once_until_it_changes(clean, monkeypatch):
    clean.write_text('[claude]\nlight = "sonnet"\n')
    monkeypatch.setattr(llm, "_TIER_CACHE", {})
    assert llm.tier_model("claude", "light") == "claude-sonnet-5-5"
    clean.write_text('[claude]\nlight = "opus"\n# changed\n')
    assert llm.tier_model("claude", "light") == "claude-opus-5-5"

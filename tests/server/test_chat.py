"""Chat routes: SSE over a fake generator (never a real model), settings/keys in a temp config dir."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.chat import ChatSettings, ChatStatus, KeyList, PromptsResponse
from kb_distillery.services import chat as chat_data

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
KEY = "sk-ant-api03-" + "x" * 30


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def temp_config(tmp_path, monkeypatch):
    """Everything the chat service writes or reads from ~/.config/kb-distillery goes to a temp dir."""
    cfg = tmp_path / "cfg"
    monkeypatch.setattr(chat_data, "CONFIG_DIR", str(cfg))
    monkeypatch.setattr(chat_data, "SETTINGS_FILE", str(cfg / "chat.json"))
    monkeypatch.setattr(chat_data, "LEDGER_FILE", str(cfg / "usage.jsonl"))
    monkeypatch.setattr(chat_data, "KEYS_DIR", str(cfg / "keys"))
    monkeypatch.setattr(chat_data, "KEY_FILE", str(cfg / "anthropic_key"))
    monkeypatch.setattr(chat_data, "INBOX", str(tmp_path / "inbox"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("kb_distillery.llm.claude_available", lambda refresh=False: (True, ""))   # not this machine's login
    return cfg


def sse_events(text):
    out = []
    for block in text.split("\n\n"):
        if block.startswith("event: "):
            head, data = block.split("\ndata: ", 1)
            out.append((head[len("event: "):], json.loads(data)))
    return out


def test_status_valid_and_matches_service(client):
    r = client.get("/api/chat/status")
    assert r.status_code == 200
    body = r.json()
    ChatStatus.model_validate(body)
    assert set(chat_data.status()) <= set(body)
    assert body["key"] is False


def test_prompts_and_settings_get(client):
    r = client.get("/api/chat/prompts")
    PromptsResponse.model_validate(r.json())
    assert set(r.json()) == {"prompts"}
    s = client.get("/api/chat/settings")
    ChatSettings.model_validate(s.json())
    assert set(s.json()) == set(chat_data.DEFAULT_SETTINGS)


def test_settings_post_roundtrip_and_errors(client, temp_config):
    r = client.post("/api/chat/settings", json={"reset_day": 5, "backend": "direct"}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["reset_day"] == 5 and r.json()["backend"] == "direct"
    assert json.load(open(temp_config / "chat.json"))["reset_day"] == 5
    bad = client.post("/api/chat/settings", json={"reset_day": 40}, headers=LOOPBACK)
    assert bad.status_code == 400 and "error" in bad.json()
    bad = client.post("/api/chat/settings", json={"backend": "nope"}, headers=LOOPBACK)
    assert bad.status_code == 400


def test_mutations_refused_without_loopback_origin(client, temp_config):
    for path, body in (("/api/chat/settings", {"reset_day": 3}), ("/api/chat/keys", {"name": "a", "key": KEY}),
                       ("/api/chat/keys/remove", {"name": "a"}), ("/api/chat", {"question": "hi"}),
                       ("/api/chat/saved", {"messages": []})):
        assert client.post(path, json=body).status_code == 403
        assert client.post(path, json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.delete("/api/chat/keys/a").status_code == 403
    assert not os.path.exists(temp_config / "chat.json")


def test_keys_never_expose_secret(client, temp_config):
    r = client.post("/api/chat/keys", json={"name": "main", "key": KEY}, headers=LOOPBACK)
    assert r.status_code == 200
    assert KEY not in r.text and (temp_config / "keys" / "main").exists()
    assert os.stat(temp_config / "keys" / "main").st_mode & 0o777 == 0o600
    body = r.json()
    assert body["key"] is True and body["key_hint"] == "sk-ant-…xxxx"
    assert body["auth"]["active_key"] == "main"
    listing = client.get("/api/chat/keys")
    KeyList.model_validate(listing.json())
    assert KEY not in listing.text
    assert listing.json()["keys"] == [{"name": "main", "origin": "file", "hint": "sk-ant-…xxxx"}]
    assert KEY not in client.get("/api/chat/status").text
    assert KEY not in client.get("/api/chat/settings").text


def test_key_add_invalid_and_remove(client, temp_config):
    assert client.post("/api/chat/keys", json={"name": "Bad Name", "key": KEY}, headers=LOOPBACK).status_code == 400
    assert client.post("/api/chat/keys", json={"name": "a", "key": "nope"}, headers=LOOPBACK).status_code == 400
    client.post("/api/chat/keys", json={"name": "a", "key": KEY}, headers=LOOPBACK)
    r = client.delete("/api/chat/keys/a", headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["auth"]["keys"] == [] and r.json()["auth"]["active_key"] == ""
    assert client.delete("/api/chat/keys/a", headers=LOOPBACK).status_code == 400
    client.post("/api/chat/keys", json={"name": "b", "key": KEY}, headers=LOOPBACK)
    assert client.post("/api/chat/keys/remove", json={"name": "b"}, headers=LOOPBACK).status_code == 200
    assert client.delete("/api/chat/keys/env", headers=LOOPBACK).status_code == 400


def test_saved_chat(client, tmp_path):
    chat = {"title": "Tensor rank", "messages": [{"role": "user", "content": "q"},
                                                  {"role": "assistant", "content": "an answer"}]}
    r = client.post("/api/chat/saved", json=chat, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["path"].endswith("tensor-rank.md")
    assert (tmp_path / "inbox" / "tensor-rank.md").exists()
    empty = client.post("/api/chat/saved", json={"messages": []}, headers=LOOPBACK)
    assert empty.status_code == 400 and "error" in empty.json()


# ── POST /api/chat ──
def fake_agent(events):
    def stream(question, **kw):
        stream.kw = {"question": question, **kw}
        yield from events
    return stream


def test_chat_agent_streams_frames_and_pings(client):
    events = [("ping", None), ("delta", "hel"), ("delta", "lo"), ("usage", {"num_turns": 1}), ("done", {})]
    fake = fake_agent(events)
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", fake), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.build_agent_system", return_value="SYS"):
        chat_data.add_key("k", KEY)
        r = client.post("/api/chat", json={"question": " hi ", "backend": "agent", "active_key": "k",
                                           "model": "bogus"}, headers=LOOPBACK)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert ": ping\n\n" in r.text
    assert sse_events(r.text) == [("delta", "hel"), ("delta", "lo"), ("usage", {"num_turns": 1}), ("done", {})]
    assert fake.kw["question"] == "hi" and fake.kw["key"] == KEY and fake.kw["billing"] == "api"
    assert fake.kw["model"] == chat_data.DEFAULT_MODEL and fake.kw["system"] == "SYS"


def test_chat_generator_error_becomes_error_event(client):
    def boom(question, **kw):
        yield "delta", "a"
        raise RuntimeError("model down")
    chat_data.add_key("k", KEY)
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", boom):
        r = client.post("/api/chat", json={"question": "q", "backend": "agent", "active_key": "k"},
                        headers=LOOPBACK)
    assert sse_events(r.text) == [("delta", "a"), ("error", {"error": "model down"})]


def test_chat_direct_backend_with_stubbed_model(client):
    chat_data.add_key("k", KEY)
    usage = {"input_tokens": 3, "output_tokens": 2}
    with mock.patch.object(chat_data, "plan_turn", return_value=([{"slug": "s"}], ["s"])), \
         mock.patch.object(chat_data, "build_system", return_value="sys"), \
         mock.patch.object(chat_data, "build_messages", return_value=[]), \
         mock.patch.object(chat_data, "stream_claude", return_value=iter([("text", "hi"), ("usage", usage)])):
        r = client.post("/api/chat", json={"question": "q", "backend": "direct", "active_key": "k"},
                        headers=LOOPBACK)
    ev = sse_events(r.text)
    assert [e[0] for e in ev] == ["sources", "delta", "usage", "done"]
    assert ev[0][1] == {"hits": [{"slug": "s"}], "new": ["s"]} and ev[1][1] == "hi"
    assert ev[2][1]["model"] == chat_data.DEFAULT_MODEL and "cost_usd" in ev[2][1]


def test_chat_direct_chat_error(client):
    chat_data.add_key("k", KEY)

    def failing(*a):
        raise chat_data.ChatError("rate limited")
        yield
    with mock.patch.object(chat_data, "plan_turn", return_value=([], [])), \
         mock.patch.object(chat_data, "build_system", return_value=""), \
         mock.patch.object(chat_data, "build_messages", return_value=[]), \
         mock.patch.object(chat_data, "stream_claude", failing):
        r = client.post("/api/chat", json={"question": "q", "backend": "direct", "active_key": "k"},
                        headers=LOOPBACK)
    assert sse_events(r.text)[-1] == ("error", {"error": "rate limited"})


@pytest.mark.parametrize("body,fragment", [
    ({"question": "q", "auth_mode": "x"}, "auth_mode"),
    ({"question": "q", "backend": "x"}, "backend"),
    ({"question": "q", "backend": "direct"}, "no API key"),
    ({"question": "q", "auth_mode": "subscription", "backend": "direct"}, "Agent backend only"),
])
def test_chat_validation_errors_are_legacy_shaped(client, body, fragment):
    r = client.post("/api/chat", json=body, headers=LOOPBACK)
    assert r.status_code == 400 and fragment in r.json()["error"]


def test_chat_empty_question_and_unavailable_agent(client):
    chat_data.add_key("k", KEY)
    r = client.post("/api/chat", json={"question": "  ", "backend": "direct", "active_key": "k"}, headers=LOOPBACK)
    assert r.status_code == 400 and r.json() == {"error": "empty question"}
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info",
                    return_value={"available": False, "error": "not installed"}):
        r = client.post("/api/chat", json={"question": "q", "backend": "agent", "active_key": "k"},
                        headers=LOOPBACK)
    assert r.status_code == 400 and r.json()["error"] == "agent backend unavailable" and "hint" in r.json()


def test_chat_subscription_not_logged_in(client):
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.subscription_status",
                    return_value={"logged_in": False, "error": "no login"}):
        r = client.post("/api/chat", json={"question": "q", "auth_mode": "subscription", "backend": "agent"},
                        headers=LOOPBACK)
    assert r.status_code == 400 and r.json()["hint"] == "no login"


# ── agent-mode flag: effort / budget / attachments ──
def _post_agent(client, **extra):
    fake = fake_agent([("done", {})])
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", fake), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.build_agent_system", return_value="SYS"):
        chat_data.add_key("k", KEY)
        r = client.post("/api/chat", json={"question": "hi", "backend": "agent", "active_key": "k", **extra},
                        headers=LOOPBACK)
    assert r.status_code == 200
    return fake.kw


@pytest.mark.flag("agent-mode", False)
def test_agent_mode_off_ignores_new_fields(client):
    kw = _post_agent(client, effort="max", budget=3.0, attachments=["a.pdf"])
    assert "effort" not in kw and "budget" not in kw


@pytest.mark.flag("agent-mode", True)
def test_agent_mode_on_passes_effort_and_budget(client):
    kw = _post_agent(client, effort="high", budget=3.0)
    assert kw["effort"] == "high" and kw["budget"] == 3.0


@pytest.mark.flag("agent-mode", True)
@pytest.mark.parametrize("pick", ["api", "batch"])
def test_agent_mode_on_passes_billing_pick(client, pick):
    kw = _post_agent(client, billing=pick, auth_mode="subscription")
    assert kw["billing"] == pick and kw["key"] == KEY       # the pick replaces the stored account choice


@pytest.mark.flag("agent-mode", True)
def test_agent_mode_on_subscription_pick_needs_a_login(client):
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.subscription_status",
                    return_value={"logged_in": False, "error": "no login"}):
        r = client.post("/api/chat", json={"question": "q", "backend": "agent", "billing": "subscription",
                                           "auth_mode": "api_key"}, headers=LOOPBACK)
    assert r.status_code == 400 and r.json()["hint"] == "no login"


@pytest.mark.flag("agent-mode", True)
def test_agent_mode_on_subscription_pick_runs_keyless(client):
    fake = fake_agent([("done", {})])
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.subscription_status",
                    return_value={"logged_in": True, "error": ""}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", fake), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.build_agent_system", return_value="SYS"):
        r = client.post("/api/chat", json={"question": "q", "backend": "agent", "billing": "subscription"},
                        headers=LOOPBACK)
    assert r.status_code == 200 and fake.kw["billing"] == "subscription" and fake.kw["key"] is None


@pytest.mark.flag("agent-mode", False)
def test_agent_mode_off_ignores_billing_pick(client):
    kw = _post_agent(client, billing="batch")
    assert kw["billing"] == "api"


def test_billing_is_validated(client):
    r = client.post("/api/chat", json={"question": "hi", "billing": "free"}, headers=LOOPBACK)
    assert r.status_code == 422


def test_status_models_carry_a_context_window(client):
    assert all(m["context"] > 0 for m in client.get("/api/chat/status").json()["models"])


def test_effort_is_validated(client):
    r = client.post("/api/chat", json={"question": "hi", "effort": "turbo"}, headers=LOOPBACK)
    assert r.status_code == 422


# ── POST /api/chat/answer (the reply to an `ask` event) ──
def test_answer_unknown_question_is_404(client):
    r = client.post("/api/chat/answer", json={"session": "s", "id": "nope", "answers": {"q": "a"}}, headers=LOOPBACK)
    assert r.status_code == 404 and r.json()["error"]


def test_answer_reaches_the_waiting_turn(client):
    from kb_distillery.services import chat_agent
    seen = []
    with mock.patch.object(chat_agent.ASKS, "answer", lambda s, i, a: seen.append((s, i, a)) or True):
        r = client.post("/api/chat/answer", json={"session": "s1", "id": "toolu_1", "answers": {"Q?": "A"}}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert seen == [("s1", "toolu_1", {"Q?": "A"})]


def test_answer_needs_a_loopback_origin_and_a_valid_body(client):
    assert client.post("/api/chat/answer", json={"id": "x", "answers": {}}).status_code in (400, 403)
    assert client.post("/api/chat/answer", json={"answers": {}}, headers=LOOPBACK).status_code == 422


# ── "needs Claude": the Agent backend is refused (409) when nothing can run Claude ──
@pytest.fixture
def no_claude(monkeypatch):
    from kb_distillery import llm
    monkeypatch.setattr("kb_distillery.llm.claude_available", lambda refresh=False: (False, llm.NEEDS_CLAUDE))
    monkeypatch.setattr("kb_distillery.services.chat_agent.subscription_status",
                        lambda *a, **k: {"logged_in": False, "error": "no login"})


def test_status_reports_claude_available(client):
    body = client.get("/api/chat/status").json()
    ChatStatus.model_validate(body)
    assert body["claude"] == {"available": True, "reason": ""}


def test_status_reports_needs_claude(client, no_claude):
    from kb_distillery import llm
    assert client.get("/api/chat/status").json()["claude"] == {"available": False, "reason": llm.NEEDS_CLAUDE}


def test_agent_chat_is_refused_with_409_without_claude(client, no_claude):
    from kb_distillery import llm
    r = client.post("/api/chat", json={"question": "q", "backend": "agent"}, headers=LOOPBACK)
    assert r.status_code == 409 and r.json() == {"error": llm.NEEDS_CLAUDE}


def test_direct_backend_is_not_gated_by_the_agent_check(client, no_claude):
    r = client.post("/api/chat", json={"question": "q", "backend": "direct"}, headers=LOOPBACK)
    assert r.status_code == 400 and "no API key" in r.json()["error"]


def test_a_stored_chat_key_counts_as_claude(client, no_claude, temp_config):
    assert client.post("/api/chat/keys", json={"name": "a", "key": KEY}, headers=LOOPBACK).status_code == 200
    assert client.get("/api/chat/status").json()["claude"]["available"] is True

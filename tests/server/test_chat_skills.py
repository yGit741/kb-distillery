"""Per-session skill toggles: list, put, the whitelist bound, and the agent request carrying only the enabled names.
Temp kb, faked kb config, faked LLM; no network."""
import asyncio
import os
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.app import create_app
from kb_distillery.server.models.chat_skills import ChatSkillList
from kb_distillery.services import agent_skills, chat_agent
from kb_distillery.services import chat as chat_data
from kb_distillery.services import sessions_store as store

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
SID = "20261104101500-abc123"
THREE = ["deep-research", "query-knowledge", "explore-raw-data"]       # three app + read skills of the base kit


@pytest.fixture
def kb(tmp_path, monkeypatch):
    root = str(tmp_path / "kb")
    os.makedirs(root)
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, stdin=subprocess.DEVNULL)
    monkeypatch.delenv(store.READ_ONLY_ENV, raising=False)
    monkeypatch.setenv("KB_APP_CONFIG", "/nonexistent/app.toml")
    monkeypatch.setattr(agent_skills, "CACHE_PATH", str(tmp_path / ".cache"))
    with mock.patch.object(store, "DEFAULT_ROOT", root):
        yield root


@pytest.fixture(autouse=True)
def reset_active():
    token = agent_skills.ACTIVE.set(None)
    yield
    agent_skills.ACTIVE.reset(token)


def whitelist(monkeypatch, names):
    data = {"agent": {"skills": names}} if names is not None else {}
    monkeypatch.setattr(kbconfig, "current", lambda: SimpleNamespace(kit="base", data=data))


@pytest.fixture
def client(kb, monkeypatch):
    whitelist(monkeypatch, THREE)
    with TestClient(create_app()) as c:
        yield c


def put(client, names, sid=SID):
    return client.put(f"/api/chat/skills/{sid}", json={"enabled": names}, headers=LOOPBACK)


def on(body):
    return [s["name"] for s in body["skills"] if s["enabled"]]


# ── flag off: the endpoints are not there ──
@pytest.mark.flag("agent-mode", False)
def test_flag_off_answers_404_and_writes_nothing(client, kb):
    assert client.get("/api/chat/skills").status_code == 404
    assert put(client, ["deep-research"]).status_code == 404
    assert not os.path.exists(os.path.join(kb, ".local"))


# ── list ──
@pytest.mark.flag("agent-mode", True)
def test_list_is_the_whitelist_with_descriptions_all_on_by_default(client):
    r = client.get("/api/chat/skills", params={"session": SID})
    assert r.status_code == 200, r.text
    body = ChatSkillList.model_validate(r.json())
    assert [s.name for s in body.skills] == THREE and all(s.enabled for s in body.skills)
    assert all(s.description and "\n" not in s.description and len(s.description) <= 160 for s in body.skills)
    assert body.session == SID


@pytest.mark.flag("agent-mode", True)
def test_list_without_a_session_shows_everything_on(client):
    assert on(client.get("/api/chat/skills").json()) == THREE


@pytest.mark.flag("agent-mode", True)
def test_empty_whitelist_lists_nothing(client, monkeypatch):
    whitelist(monkeypatch, [])
    assert client.get("/api/chat/skills", params={"session": SID}).json()["skills"] == []


@pytest.mark.flag("agent-mode", True)
def test_a_bad_session_id_is_400(client):
    assert client.get("/api/chat/skills", params={"session": "../x"}).status_code == 400
    assert put(client, [], sid="Bad Id").status_code in (400, 404)


# ── put ──
@pytest.mark.flag("agent-mode", True)
def test_put_stores_the_subset_with_the_session_and_get_returns_it(client, kb):
    r = put(client, ["query-knowledge"])
    assert r.status_code == 200, r.text
    assert on(r.json()) == ["query-knowledge"]
    assert on(client.get("/api/chat/skills", params={"session": SID}).json()) == ["query-knowledge"]
    assert os.path.isfile(os.path.join(kb, ".local", "sessions", f"{SID}.skills.json"))
    assert on(client.get("/api/chat/skills", params={"session": "20261104101500-other1"}).json()) == THREE
    assert not os.path.exists(os.path.join(kb, "wiki")) and not os.path.exists(os.path.join(kb, "kb.toml"))


@pytest.mark.flag("agent-mode", True)
def test_put_can_turn_everything_off_and_back_on(client):
    assert on(put(client, []).json()) == []
    assert on(put(client, THREE).json()) == THREE


@pytest.mark.flag("agent-mode", True)
def test_nothing_outside_the_whitelist_can_be_enabled(client, monkeypatch):
    r = put(client, ["deep-research", "wiki-edit", "no-such-skill", "kbd:query-knowledge", "../x"])
    assert r.status_code == 200 and on(r.json()) == ["deep-research"]
    whitelist(monkeypatch, ["deep-research"])                       # the kb.toml shrinks later: a stored name falls away
    assert agent_skills.session_selection(SID) == ["deep-research"]
    whitelist(monkeypatch, ["query-knowledge"])
    assert agent_skills.session_selection(SID) == []


@pytest.mark.flag("agent-mode", True)
def test_a_session_file_keeps_no_session_listed_until_it_is_saved(client):
    put(client, ["deep-research"])
    assert client.get("/api/sessions").json()["sessions"] == []     # the sidecar is not a session
    client.put(f"/api/sessions/{SID}", json={"messages": [{"role": "user", "content": "hi"}]}, headers=LOOPBACK)
    assert [s["id"] for s in client.get("/api/sessions").json()["sessions"]] == [SID]
    assert on(client.get("/api/chat/skills", params={"session": SID}).json()) == ["deep-research"]
    client.delete(f"/api/sessions/{SID}", headers=LOOPBACK)
    assert on(client.get("/api/chat/skills", params={"session": SID}).json()) == THREE   # deleted with the session


@pytest.mark.flag("agent-mode", True)
def test_read_only_server_refuses_put(client, monkeypatch):
    monkeypatch.setenv(store.READ_ONLY_ENV, "1")
    r = put(client, [])
    assert r.status_code == 405 and r.json()["error"]


# ── the agent request ──
def fake_agent():
    def stream(question, **kw):
        stream.kw = {"question": question, **kw}
        yield ("done", {})
    return stream


def post(client, **extra):
    fake = fake_agent()
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", fake), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.build_agent_system", return_value="SYS"):
        chat_data.add_key("k", "sk-ant-api03-" + "x" * 30)
        r = client.post("/api/chat", json={"question": "hi", "backend": "agent", "active_key": "k", **extra}, headers=LOOPBACK)
    assert r.status_code == 200
    return fake.kw


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_data, "CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(chat_data, "SETTINGS_FILE", str(tmp_path / "cfg" / "chat.json"))
    monkeypatch.setattr(chat_data, "LEDGER_FILE", str(tmp_path / "cfg" / "usage.jsonl"))
    monkeypatch.setattr(chat_data, "KEYS_DIR", str(tmp_path / "cfg" / "keys"))
    monkeypatch.setattr(chat_data, "KEY_FILE", str(tmp_path / "cfg" / "anthropic_key"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.mark.flag("agent-mode", True)
def test_flag_on_chat_request_passes_the_subset(client, cfg):
    assert post(client, skills=["query-knowledge"])["skills"] == ["query-knowledge"]
    assert post(client, skills=[])["skills"] == []
    assert "skills" not in post(client)


@pytest.mark.flag("agent-mode", True)
def test_a_saved_subset_applies_when_the_client_sends_no_list(client, cfg):
    put(client, ["query-knowledge"])
    assert post(client, skills_session=SID)["skills"] == ["query-knowledge"]
    assert post(client, skills_session=SID, skills=["deep-research"])["skills"] == ["deep-research"]   # an explicit list wins
    assert post(client, skills_session="20261104101500-never1")["skills"] == THREE                   # nothing saved: the whole whitelist
    assert "skills" not in post(client)
    assert "skills" not in post(client, skills_session="Not A Slug!")        # a chat id of another shape still asks


@pytest.mark.flag("agent-mode", True)
def test_a_stored_allow_list_leaves_skills_added_later_off(client, monkeypatch):
    put(client, ["deep-research"])
    whitelist(monkeypatch, THREE)
    assert agent_skills.session_selection(SID) == ["deep-research"]      # a skill whitelisted after the choice stays off until switched on


@pytest.mark.flag("agent-mode", True)
def test_deleting_an_unsaved_session_keeps_nothing_it_did_not_own(client, kb):
    put(client, ["deep-research"])
    assert client.delete(f"/api/sessions/{SID}", headers=LOOPBACK).status_code == 404
    assert os.path.isfile(os.path.join(kb, ".local", "sessions", f"{SID}.skills.json"))


@pytest.mark.flag("agent-mode", False)
def test_flag_off_chat_request_ignores_skills(client, cfg):
    assert "skills" not in post(client, skills=["query-knowledge"], skills_session=SID)


def request_for(skills):
    agent_skills.set_active(skills)
    return chat_agent.agent_request("q", "sonnet", "SYS")


@pytest.mark.flag("agent-mode", True)
def test_the_agent_request_carries_only_the_enabled_names(client):
    req = request_for(["query-knowledge", "wiki-edit"])
    assert req.skills == ("kbd:query-knowledge",)
    (plugin,) = req.plugins
    assert sorted(os.listdir(os.path.join(plugin, "skills"))) == ["query-knowledge"]
    assert set(req.agents) == {"kb-researcher"}
    assert request_for(None).skills == tuple(agent_skills.qualified(n) for n in THREE)
    none = request_for([])
    assert not none.skills and not none.plugins and not none.agents and "Skill" not in none.tools


@pytest.mark.flag("agent-mode", True)
def test_the_policy_follows_the_turns_subset(client):
    agent_skills.set_active(["query-knowledge"])
    assert chat_agent.tool_policy("Skill", {"skill": "kbd:query-knowledge"}).allow
    assert not chat_agent.tool_policy("Skill", {"skill": "deep-research"}).allow
    assert chat_agent.tool_policy("Agent", {"subagent_type": "kb-researcher"}).allow
    agent_skills.set_active([])
    assert not chat_agent.tool_policy("Skill", {"skill": "query-knowledge"}).allow
    assert not chat_agent.tool_policy("Agent", {"subagent_type": "kb-researcher"}).allow
    agent_skills.set_active(None)
    assert chat_agent.tool_policy("Skill", {"skill": "deep-research"}).allow


@pytest.mark.flag("agent-mode", True)
def test_a_streamed_turn_builds_its_request_from_the_subset(client):
    """`_run` pins the subset before it builds the request; the LLM layer is faked."""
    seen = {}

    async def fake_stream(req, backend, **kw):
        seen["req"] = req
        seen["policy"] = chat_agent.tool_policy("Skill", {"skill": "deep-research"}).allow
        return
        yield                                                       # pragma: no cover  (an async generator)

    with mock.patch.object(chat_agent.llm_agent, "stream", fake_stream), \
         mock.patch.object(chat_agent.query, "parse_index", return_value={}):
        asyncio.run(chat_agent._run("q", model="m", system="S", key="k", session_id=None, history=None, emit=lambda e: None,
                                    stop_event=None, log=print, agent_mode=True, skills=["query-knowledge"]))
    assert seen["req"].skills == ("kbd:query-knowledge",) and seen["policy"] is False

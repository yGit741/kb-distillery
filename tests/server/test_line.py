"""POST /api/line/route and its service: each intent, the command check, and every failure reading as a page search.
The LLM is faked; no test reaches a real backend."""
import json
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.server.app import create_app
from kb_distillery.server.models.line import LineRouteResponse
from kb_distillery.services import line_route

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
COMMANDS = [{"id": "zoom-out", "label": "Zoom out"}, {"id": "filters", "label": "Filters"}]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    with TestClient(create_app()) as c:
        yield c


def fake_ask(monkeypatch, reply, **result):
    seen = []

    def ask(prompt, backend=None, fallback=None, run_kw=None, **kw):
        seen.append({"prompt": prompt, "backend": backend, "fallback": fallback, **kw})
        if isinstance(reply, Exception):
            raise reply
        return llm.Result(id="line-route", text=reply if isinstance(reply, str) else json.dumps(reply),
                          backend=backend, backend_used=backend, **result)
    monkeypatch.setattr(llm, "ask", ask)
    return seen


def post(client, text, **body):
    r = client.post("/api/line/route", json={"text": text, "commands": COMMANDS, **body}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    LineRouteResponse.model_validate(r.json())
    return r.json()


@pytest.mark.parametrize("intent", ["search", "view", "ask"])
def test_each_intent_passes_through_with_its_text(client, monkeypatch, intent):
    fake_ask(monkeypatch, {"intent": intent, "text": "hide blog posts with degree 1"})
    got = post(client, "filter out all blogs that are with degree 1")
    assert got["intent"] == intent and got["text"] == "hide blog posts with degree 1"
    assert "command" not in got and got["backend"] == "subscription"


def test_a_command_answer_carries_a_known_command_id(client, monkeypatch):
    seen = fake_ask(monkeypatch, {"intent": "command", "text": "zoom out", "command": "zoom-out"})
    got = post(client, "make everything look further away")
    assert got["intent"] == "command" and got["command"] == "zoom-out"
    # the prompt is tiny: the four intents and the command names, nothing about the kb
    assert "zoom-out: Zoom out" in seen[0]["prompt"] and len(seen[0]["prompt"]) < 1500
    assert seen[0]["model"] == line_route.MODEL and seen[0]["max_tokens"] == line_route.MAX_TOKENS


def test_a_command_the_line_does_not_offer_reads_as_a_search(client, monkeypatch):
    fake_ask(monkeypatch, {"intent": "command", "text": "x", "command": "delete-everything"})
    got = post(client, "do the thing")
    assert got["intent"] == "search" and got["text"] == "do the thing" and "delete-everything" in got["reason"]


@pytest.mark.parametrize("reply", ["no json here", {"intent": "dance"}, {"text": "x"}])
def test_an_unusable_answer_reads_as_a_search(client, monkeypatch, reply):
    fake_ask(monkeypatch, reply)
    got = post(client, "something long and unclear here")
    assert got["intent"] == "search" and got["reason"].startswith("the answer was not usable")


def test_a_backend_failure_reads_as_a_search_never_an_error(client, monkeypatch):
    fake_ask(monkeypatch, llm.HTTPFail(503, "overloaded"))
    got = post(client, "something long and unclear here")
    assert got["intent"] == "search" and "failed" in got["reason"]


def test_an_error_result_reads_as_a_search(client, monkeypatch):
    fake_ask(monkeypatch, "", error="claude: not logged in")
    got = post(client, "something long and unclear here")
    assert got["intent"] == "search" and "not logged in" in got["reason"]


def test_a_slow_backend_reads_as_a_search_within_the_deadline(monkeypatch):
    def slow(*a, **k):
        time.sleep(1)
        return llm.Result(id="line-route", text='{"intent": "ask"}')
    monkeypatch.setattr(llm, "ask", slow)
    got = line_route.route("why is the sky blue today then", COMMANDS, timeout_s=0.05)
    assert got["intent"] == "search" and "did not answer" in got["reason"]


def test_backend_is_selectable_per_request_and_defaults_to_subscription_without_fallback(client, monkeypatch):
    seen = fake_ask(monkeypatch, {"intent": "ask", "text": "q"})
    post(client, "a line")
    post(client, "a line", backend="api")
    monkeypatch.setenv(llm.ENV_BACKEND, "api")
    post(client, "a line")
    assert [(s["backend"], s["fallback"]) for s in seen] == [("subscription", None), ("api", None), ("api", None)]


def test_an_unknown_env_backend_reads_as_a_search(client, monkeypatch):
    seen = fake_ask(monkeypatch, {"intent": "ask"})
    monkeypatch.setenv(llm.ENV_BACKEND, "carrier-pigeon")
    got = post(client, "a line")
    assert got["intent"] == "search" and not seen


def test_empty_text_asks_nobody(monkeypatch):
    with mock.patch.object(llm, "ask") as ask:
        assert line_route.route("   ")["intent"] == "search"
    ask.assert_not_called()


def test_the_route_refuses_a_foreign_origin(client):
    r = client.post("/api/line/route", json={"text": "x"}, headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_a_read_only_server_refuses_the_route(client, monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    with mock.patch.object(llm, "ask") as ask:
        r = client.post("/api/line/route", json={"text": "x"}, headers=ORIGIN)
    assert r.status_code == 405
    ask.assert_not_called()

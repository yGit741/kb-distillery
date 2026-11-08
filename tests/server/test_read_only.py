"""A read-only server (KB_READ_ONLY=1: the shared site's server side) refuses every route a visitor must never reach:
the writes (favorites, views, recent steps) and everything that spends a model call or opens a chat. Reads keep working."""
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.graph import layers_translate
from kb_distillery.server.app import create_app

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    with TestClient(create_app()) as c:
        yield c


CALLS = [
    ("POST", "/api/favorites", {"slug": "alpha"}),
    ("DELETE", "/api/favorites/alpha", None),
    ("POST", "/api/views", {"name": "x"}),
    ("PATCH", "/api/views/x", {"name": "y"}),
    ("DELETE", "/api/views/x", None),
    ("POST", "/api/recent", {"text": "x"}),
    ("DELETE", "/api/recent", None),
    ("POST", "/api/graph/layers", {"text": "show papers", "op": "replace"}),
    ("POST", "/api/graph/shape", {"text": "papers"}),
    ("GET", "/api/search/similar?q=attention", None),
    ("POST", "/api/chat", {"question": "hi"}),
    ("POST", "/api/chat/answer", {"session": "s", "id": "i", "answers": {}}),
]


@pytest.mark.parametrize("method,path,body", CALLS, ids=[f"{m} {p}" for m, p, _ in CALLS])
def test_a_read_only_server_answers_405_and_never_reaches_a_model(client, method, path, body):
    with mock.patch.object(llm, "ask", side_effect=AssertionError("a model was called")):
        r = client.request(method, path, json=body, headers=LOOPBACK)
    assert r.status_code == 405, r.text
    assert "read-only" in r.text


def test_reads_still_work_on_a_read_only_server(client):
    assert client.get("/api/views", headers=LOOPBACK).status_code == 200
    assert client.get("/api/views/ready", headers=LOOPBACK).status_code == 200
    assert client.get("/api/favorites", headers=LOOPBACK).status_code == 200


def test_the_same_routes_are_not_refused_when_the_server_is_not_read_only(monkeypatch):
    monkeypatch.delenv("KB_READ_ONLY", raising=False)
    fail = layers_translate.LayersError("fake backend failure", 502)
    with TestClient(create_app()) as c, mock.patch.object(layers_translate, "translate", side_effect=fail):
        r = c.post("/api/graph/layers", json={"text": "show papers", "op": "replace"}, headers=LOOPBACK)
    assert r.status_code == 502

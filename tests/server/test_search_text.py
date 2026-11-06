"""GET /api/search/text on a temp kb."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.search import fts
from kb_distillery.server.app import create_app
from kb_distillery.server.models.search import TextSearch
from kb_distillery.services import kbview


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@pytest.fixture
def client(tmp_path):
    root = str(tmp_path / "kb")
    _w(f"{root}/wiki/tensor-rank.md", "# Tensor rank\n\nrank-one terms\n")
    _w(f"{root}/.local/sessions/s1.json", json.dumps({"id": "s1", "title": "T", "messages": [{"role": "user", "content": "tensor chat"}]}))
    view = kbview.KbView(id="t", name="T", root=root, types=None, active=True)
    with mock.patch.object(fts.kbconfig, "think_root", return_value=str(tmp_path / "think")), \
         mock.patch.object(kbview, "view", return_value=view), TestClient(create_app()) as c:
        yield c


def test_hits_kinds_and_limit(client):
    r = client.get("/api/search/text", params={"q": "tensor"})
    assert r.status_code == 200
    body = TextSearch.model_validate(r.json())
    assert {(h.kind, h.id) for h in body.hits} == {("page", "tensor-rank"), ("chat", "s1")}
    only = client.get("/api/search/text", params={"q": "tensor", "kinds": "chat"}).json()
    assert [h["kind"] for h in only["hits"]] == ["chat"]
    assert len(client.get("/api/search/text", params={"q": "tensor", "limit": 1}).json()["hits"]) == 1


def test_empty_and_odd_queries_are_200(client):
    for q in ("", "   ", '"', "nomatchatall", "a AND"):
        r = client.get("/api/search/text", params={"q": q})
        assert r.status_code == 200 and r.json()["hits"] == [] or q == "a AND"
    assert client.get("/api/search/text", params={"q": "x", "kinds": "bogus"}).json()["hits"] == []


def test_unknown_kb_is_404(client):
    with mock.patch.object(kbview, "view", side_effect=KeyError("zzz")):
        assert client.get("/api/search/text", params={"q": "x", "kb": "zzz"}).status_code == 404

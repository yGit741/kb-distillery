"""POST /api/graph/layers and the layer models: the model-valid response, status codes, loopback origin, fixture parity
with the TypeScript model (web/src/features/graph/layers/parity.test.ts reads the same files). The LLM is faked."""
import glob
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.graph import layers_translate as lt
from kb_distillery.graph import query as cypher
from kb_distillery.server.app import create_app
from kb_distillery.server.models.layers import Layer, LayersResponse, ViewStack

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
FIXTURES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "fixtures", "layers", "*.json")))
SNAP = {
    "nodes": [{"id": "a", "title": "Learning theory", "type": "idea", "layer": "concept"},
              {"id": "b", "title": "Attention", "type": "paper", "layer": "source"}],
    "links": [{"source": "b", "target": "a", "kind": "wikilink"}],
}
GOOD = {"layers": [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "type", "value": "paper"}]}}], "explanation": "papers"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    with mock.patch.object(cypher, "current_graph", return_value=cypher.to_graph(SNAP)), TestClient(create_app()) as c:
        yield c


def fake_ask(monkeypatch, *replies, **result):
    seen, queue = [], list(replies)

    def ask(prompt, backend=None, fallback=None, run_kw=None, **kw):
        seen.append({"backend": backend, "fallback": fallback})
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return llm.Result(id="layers", text=r if isinstance(r, str) else json.dumps(r), backend=backend,
                          backend_used=backend, **result)
    monkeypatch.setattr(llm, "ask", ask)
    return seen


# ---- models
def test_there_are_fixtures():
    assert len(FIXTURES) >= 2


@pytest.mark.parametrize("path", FIXTURES, ids=os.path.basename)
def test_fixture_stacks_validate_and_print_the_lines_the_typescript_printer_expects(path):
    with open(path, encoding="utf-8") as f:
        fx = json.load(f)
    stack = ViewStack.model_validate(fx["stack"])
    assert [lt.print_layer(l) for l in stack.layers] == fx["lines"]
    # the JSON the API sends is the JSON the fixture holds (no key added, none lost)
    assert json.loads(stack.model_dump_json(exclude_none=True)) == fx["stack"]


@pytest.mark.parametrize("bad", [
    {"v": 1, "layers": []},
    {"v": 2, "layers": [{"id": "L1", "kind": "show", "target": "nodes", "text": "", "subgraph": {"nodes": [{"t": "degree", "op": "~", "n": 1}]}}]},
    {"v": 2, "layers": [{"id": "L1", "kind": "show", "target": "nodes", "text": "", "subgraph": {"edges": [{"t": "nope"}]}}]},
    {"v": 2, "layers": [{"id": "L1", "kind": "show", "target": "nodes", "text": "", "subgraph": {}, "cypher": "MATCH (n)"}]},
])
def test_what_the_typescript_model_does_not_allow_is_refused(bad):
    with pytest.raises(ValueError):
        ViewStack.model_validate(bad)


# ---- route
def test_a_sentence_becomes_layers(client, monkeypatch):
    seen = fake_ask(monkeypatch, GOOD, usd=0.0)
    r = client.post("/api/graph/layers", headers=ORIGIN, json={"text": "just the papers"})
    assert r.status_code == 200
    body = LayersResponse.model_validate(r.json())
    assert body.lines == ["show nodes type paper"] and body.backend == "subscription" and body.fallback_from is None
    assert isinstance(body.layers[0], Layer) and body.warnings == []
    assert seen == [{"backend": "subscription", "fallback": "api"}]


def test_backend_and_fallback_are_passed_and_the_cost_echoed(client, monkeypatch):
    seen = fake_ask(monkeypatch, GOOD, usd=0.0012)
    r = client.post("/api/graph/layers", headers=ORIGIN, json={"text": "papers", "backend": "api", "fallback": "none", "op": "stack"})
    assert r.status_code == 200 and r.json()["usd"] == 0.0012 and r.json()["backend"] == "api"
    assert seen == [{"backend": "api", "fallback": None}]


def test_unknown_backend_is_400(client, monkeypatch):
    fake_ask(monkeypatch)
    assert client.post("/api/graph/layers", headers=ORIGIN, json={"text": "x", "backend": "nope"}).status_code == 422   # not in the enum
    monkeypatch.setenv(llm.ENV_BACKEND, "nope")
    r = client.post("/api/graph/layers", headers=ORIGIN, json={"text": "x"})
    assert r.status_code == 400 and "unknown backend" in r.json()["detail"]


def test_unparsable_answer_is_422_with_the_raw_text(client, monkeypatch):
    fake_ask(monkeypatch, "MATCH (n) RETURN n")
    r = client.post("/api/graph/layers", headers=ORIGIN, json={"text": "x"})
    assert r.status_code == 422 and "MATCH (n) RETURN n" in r.json()["detail"]


def test_backend_failure_is_502(client, monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: llm.Result(id="layers", error="boom", backend="subscription"))
    r = client.post("/api/graph/layers", headers=ORIGIN, json={"text": "x"})
    assert r.status_code == 502 and "boom" in r.json()["detail"]


def test_a_mutation_needs_a_loopback_origin(client, monkeypatch):
    fake_ask(monkeypatch, GOOD)
    assert client.post("/api/graph/layers", headers={"Origin": "http://evil.example"}, json={"text": "x"}).status_code == 403


def test_the_route_is_in_the_openapi(client):
    assert "/api/graph/layers" in client.get("/openapi.json").json()["paths"]

"""POST /api/graph/shape: the model-valid response, status codes, loopback origin; the LLM is faked."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.graph import query as cypher
from kb_distillery.server.app import create_app
from kb_distillery.server.models.shape import ShapeResponse

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
SNAP = {
    "nodes": [{"id": "a", "title": "A", "type": "idea", "layer": "concept"},
              {"id": "b", "title": "B", "type": "paper", "layer": "source"}],
    "links": [{"source": "b", "target": "a", "kind": "wikilink"}],
}
GOOD = 'MATCH (p:Paper)-[:MENTIONS]->(i:Idea) RETURN p.slug, i.slug'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    with mock.patch.object(cypher, "current_graph", return_value=cypher.to_graph(SNAP)), \
         mock.patch.object(cypher, "REJECTED_LOG", str(tmp_path / "rejected.jsonl")), \
         TestClient(create_app()) as c:
        yield c


def fake_llm(monkeypatch, *texts):
    seen, queue = [], list(texts)

    def run(requests, backend=None, **kw):
        seen.append(backend)
        return [llm.Result(id=requests[0].id, text=queue.pop(0), backend=llm.resolve_backend(backend))]
    monkeypatch.setattr(llm, "run", run)
    return seen


def reply(cy=GOOD, style="colour by type"):
    return json.dumps({"cypher": cy, "style_text": style, "explanation": "ok"})


def test_raw_cypher_passthrough(client, monkeypatch):
    fake_llm(monkeypatch)                                           # an LLM call would pop from an empty queue
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": GOOD + "\n-- layout grid"})
    assert r.status_code == 200
    body = ShapeResponse.model_validate(r.json())
    assert body.source == "cypher" and body.cypher == GOOD and body.style.layout == "grid"
    assert body.rows == [["b", "a"]] and body.columns == ["p.slug", "i.slug"] and body.backend is None


def test_pure_style_has_no_cypher(client):
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": "colour by degree"})
    body = ShapeResponse.model_validate(r.json())
    assert r.status_code == 200 and body.cypher is None and body.style.colour_by.by == "degree"


def test_llm_with_backend_override(client, monkeypatch):
    seen = fake_llm(monkeypatch, reply())
    r = client.post("/api/graph/shape", headers=ORIGIN,
                    json={"text": "papers that mention ideas, colour by type", "backend": "api", "limit": 10})
    body = ShapeResponse.model_validate(r.json())
    assert r.status_code == 200 and body.source == "llm" and body.backend == "api" and seen == ["api"]
    assert body.rows == [["b", "a"]] and body.style.colour_by.name == "type"


def test_unknown_backend_value_is_rejected(client):
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": "papers", "backend": "gpt"})
    assert r.status_code == 422


def test_bad_llm_cypher_retries_then_422_with_hint(client, monkeypatch):
    bad = reply("MATCH (a)-[r]-(b) RETURN b.slug")
    seen = fake_llm(monkeypatch, bad, bad)
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": "things next to things"})
    assert r.status_code == 422 and "neighbourhood" in r.json()["detail"] and len(seen) == 2


def test_unknown_style_clause_hint(client):
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": GOOD + "\nstyle: sparkle all nodes"})
    assert r.status_code == 422
    assert "unknown style clause `sparkle all nodes`" in r.json()["detail"] and "layout <force" in r.json()["detail"]


def test_llm_backend_failure_is_502(client, monkeypatch):
    monkeypatch.setattr(llm, "run", lambda reqs, backend=None, **kw: [llm.Result(id="shape", error="boom", backend="api")])
    r = client.post("/api/graph/shape", headers=ORIGIN, json={"text": "papers please", "backend": "api"})
    assert r.status_code == 502 and "boom" in r.json()["detail"]


def test_needs_loopback_origin(client):
    r = client.post("/api/graph/shape", json={"text": "layout grid"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403

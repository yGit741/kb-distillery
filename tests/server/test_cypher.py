"""POST /api/graph/cypher, GET/POST /api/graph/queries: model-valid tables, 400 with a hint on rejection."""
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.cypher import NamedQuery, QueryTable
from kb_distillery.graph import query as cypher

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
SNAP = {
    "nodes": [{"id": "a", "title": "A", "type": "idea", "layer": "concept"},
              {"id": "b", "title": "B", "type": "paper", "layer": "source"}],
    "links": [{"source": "b", "target": "a", "kind": "wikilink"}],
}


@pytest.fixture
def client(tmp_path):
    with mock.patch.object(cypher, "current_graph", return_value=cypher.to_graph(SNAP)), \
         mock.patch.object(cypher, "REJECTED_LOG", str(tmp_path / "rejected.jsonl")), \
         TestClient(create_app()) as c:
        yield c


def test_cypher_returns_a_table(client):
    r = client.post("/api/graph/cypher", headers=ORIGIN,
                    json={"query": "MATCH (p:Paper)-[:MENTIONS]->(i:Idea) RETURN p.slug, i.slug"})
    assert r.status_code == 200
    body = QueryTable.model_validate(r.json())
    assert body.columns == ["p.slug", "i.slug"] and body.rows == [["b", "a"]]


def test_cypher_rejection_is_400_with_hint(client):
    r = client.post("/api/graph/cypher", headers=ORIGIN, json={"query": "MATCH (a)-[r]-(b) RETURN b"})
    assert r.status_code == 400
    assert "neighbourhood" in r.json()["detail"]


def test_cypher_needs_loopback_origin(client):
    r = client.post("/api/graph/cypher", json={"query": "MATCH (n) RETURN n.slug"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_named_queries(client):
    r = client.get("/api/graph/queries")
    assert r.status_code == 200
    names = {NamedQuery.model_validate(q).name for q in r.json()}
    assert {"gaps", "shortest-path", "neighbourhood"} <= names
    assert "unaddressed-questions" not in names           # the kb declares no ADDRESSES / OPEN_PROBLEM_IN edges
    r = client.post("/api/graph/queries/unaddressed-questions", headers=ORIGIN, json={})
    assert r.status_code == 400 and "needs the edge kinds" in r.json()["detail"]
    r = client.post("/api/graph/queries/neighbourhood", headers=ORIGIN, json={"params": {"slug": "a"}})
    assert r.status_code == 200
    assert QueryTable.model_validate(r.json()).rows[0][0]["slug"] == "b"
    r = client.post("/api/graph/queries/bogus", headers=ORIGIN, json={})
    assert r.status_code == 400 and "unknown named query" in r.json()["detail"]

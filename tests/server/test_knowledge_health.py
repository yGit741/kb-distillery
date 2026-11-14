"""GET /api/health/knowledge: model-valid response, query params, validation."""
from unittest import mock

from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.knowledge_health import KnowledgeHealth

SNAP = {
    "nodes": [{"id": "s1", "title": "S1", "layer": "source", "depth": "listed"},
              {"id": "s2", "title": "S2", "layer": "source", "depth": "full"},
              {"id": "s3", "title": "S3", "layer": "source", "depth": "full"},
              {"id": "a", "title": "A", "layer": "concept"}, {"id": "b", "title": "B", "layer": "concept"}],
    "links": [{"source": s, "target": c} for s in ("s1", "s2", "s3") for c in ("a", "b")],
}


def get(url):
    with mock.patch("kb_distillery.graph.cache.cached_graph_snapshot", return_value=SNAP), TestClient(create_app()) as c:
        return c.get(url)


def test_shape_and_values():
    r = get("/api/health/knowledge")
    assert r.status_code == 200
    body = KnowledgeHealth.model_validate(r.json())
    assert body.undigested_sources.count == 1
    assert body.missing_links.items[0].shared == ["s1", "s2", "s3"] and body.missing_links.items[0].score == 1.0


def test_params():
    assert get("/api/health/knowledge?limit=0").json()["missing_links"] == {"count": 1, "items": []}
    assert get("/api/health/knowledge?min_jaccard=2").status_code == 422

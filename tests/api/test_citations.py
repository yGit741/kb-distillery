"""GET /api/citations: valid model on the real vault, canned data, and the legacy key set."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.citations import CitationGraph
from kb_distillery.services import corpus


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_citations_on_the_real_vault_match_the_service(client):
    r = client.get("/api/citations")
    assert r.status_code == 200
    body = r.json()
    CitationGraph.model_validate(body)
    legacy = corpus.build_citations()
    assert set(body) >= set(legacy)
    assert body["nodes"] == legacy["nodes"] and body["links"] == legacy["links"]


def test_citations_from_a_canned_cache(client, tmp_path):
    cache = tmp_path / "citations.json"
    cache.write_text(json.dumps({"papers": {
        "p1": {"slug": "paper-a", "title": "A", "year": 2020, "citationCount": 5, "references": ["p2", "zz"]},
        "p2": {"slug": "paper-b", "year": 2019},
        "p3": {"title": "not in the vault"}}}))
    with mock.patch.object(corpus, "CITATIONS_CACHE", str(cache)):
        body = client.get("/api/citations").json()
    graph = CitationGraph.model_validate(body)
    assert [n.id for n in graph.nodes] == ["paper-a", "paper-b"]
    assert graph.nodes[1].title == "paper-b" and graph.nodes[1].citationCount == 0
    assert body["links"] == [{"source": "paper-a", "target": "paper-b"}]
    assert "missing" not in body or body["missing"] is None


def test_citations_without_a_cache(client, tmp_path):
    with mock.patch.object(corpus, "CITATIONS_CACHE", str(tmp_path / "none.json")):
        body = client.get("/api/citations").json()
    assert body == {"nodes": [], "links": [], "missing": True}

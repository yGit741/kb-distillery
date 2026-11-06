"""GET /api/search/similar with the qmd service mocked: hits, the page's own card as query, 404/422/503."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.search import qmd_client
from kb_distillery.server.app import create_app
from kb_distillery.server.models.search import SimilarResult
from kb_distillery.services import similar as svc

PAGES = {
    "idea-margin": ("", {"type": "idea", "description": '"Large margins generalize."'}, "# Margin\n"),
    "idea-norm": ("", {"type": "idea"}, "# Norm bounds\n"),
    "paper-x": ("", {"type": "paper"}, "# Paper X\n"),
}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(svc, "load_pages", lambda: PAGES)
    with TestClient(create_app()) as c:
        yield c


@pytest.mark.flag("semantic-search", True)
def test_phrase_returns_typed_hits(client, monkeypatch):
    seen = {}

    def fake(q, limit=10, **kw):
        seen.update(q=q, limit=limit)
        return [("idea-norm", 0.9), ("gone", 0.8), ("paper-x", 0.5)]

    monkeypatch.setattr(qmd_client, "search", fake)
    r = client.get("/api/search/similar", params={"q": "overfitting", "k": 2})
    assert r.status_code == 200
    body = SimilarResult.model_validate(r.json())
    assert [(h.slug, h.title, h.score) for h in body.hits] == [("idea-norm", "Norm bounds", 90), ("paper-x", "Paper X", 50)]
    assert seen == {"q": "overfitting", "limit": 3}


@pytest.mark.flag("semantic-search", True)
def test_slug_uses_its_own_card_and_skips_itself(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(qmd_client, "search", lambda q, limit=10, **kw: (seen.update(q=q), [("idea-margin", 1.0), ("idea-norm", 0.7)])[1])
    r = client.get("/api/search/similar", params={"slug": "idea-margin"})
    assert [h["slug"] for h in r.json()["hits"]] == ["idea-norm"]
    assert "Margin" in seen["q"] and "Large margins generalize." in seen["q"]


@pytest.mark.flag("semantic-search", True)
def test_errors(client, monkeypatch):
    monkeypatch.setattr(qmd_client, "search", lambda *a, **k: None)
    assert client.get("/api/search/similar").status_code == 422
    assert client.get("/api/search/similar", params={"slug": "nope"}).status_code == 404
    r = client.get("/api/search/similar", params={"q": "x"})
    assert r.status_code == 503 and "not running" in r.json()["detail"]


@pytest.mark.flag("semantic-search", False)
def test_flag_off_is_503_without_calling_the_service(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("qmd must not be called")

    monkeypatch.setattr(qmd_client, "search", boom)
    r = client.get("/api/search/similar", params={"q": "x"})
    assert r.status_code == 503 and r.json()["detail"] == "semantic search is off"

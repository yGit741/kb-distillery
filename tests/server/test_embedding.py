"""GET /api/embedding: the typed report over the service."""
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.embedding import EmbeddingReport
from kb_distillery.server.routers import embedding as router

REPORT = {
    "built": True, "ok": False, "line": "2 vectors for 3 cards, behind (1 missing)", "model": "m", "dim": 2, "cards": 3, "vectors": 2,
    "missing": [{"slug": "c", "title": "C"}], "changed": [], "removed": [], "duplicate_cosine": 0.97,
    "duplicates": [{"a": {"slug": "a", "title": "A"}, "b": {"slug": "b", "title": "B"}, "cosine": 0.99}],
    "k": 1, "silhouette": 0.0, "clusters": [{"id": 0, "size": 2, "cohesion": 0.9, "central": [{"slug": "a", "title": "A"}]}],
    "points": [{"slug": "a", "title": "A", "x": 0.0, "y": 0.5, "cluster": 0}, {"slug": "b", "title": "B", "x": 1.0, "y": 0.5, "cluster": 0}],
}


def test_report_validates_against_the_model(monkeypatch):
    monkeypatch.setattr(router, "build_embedding_report", lambda: REPORT)
    with TestClient(create_app()) as c:
        r = c.get("/api/embedding")
    assert r.status_code == 200
    body = EmbeddingReport.model_validate(r.json())
    assert body.missing[0].slug == "c" and body.clusters[0].central[0].title == "A" and body.points[1].x == 1.0


def test_no_store_is_a_200_that_says_so(monkeypatch, tmp_path):
    from kb_distillery.services import embedding as svc
    monkeypatch.setattr(router, "build_embedding_report", lambda: svc.build_embedding_report(str(tmp_path / "no.sqlite"), str(tmp_path / "cards")))
    with TestClient(create_app()) as c:
        r = c.get("/api/embedding")
    assert r.status_code == 200 and EmbeddingReport.model_validate(r.json()).built is False

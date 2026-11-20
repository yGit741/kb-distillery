"""GET /api/artifacts?kb=: the artifact layer of a knowledge base, 404 when it has none or is unknown."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.app import create_app
from kb_distillery.server.models.artifacts import ArtifactGraph
from kb_distillery.services import kbview

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "artifacts" / "kb-code"


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "kb-code"
    shutil.copytree(FIXTURE, root)
    monkeypatch.setattr(kbconfig, "discover", lambda: {"code": str(root)})
    kbview._views.clear()
    with TestClient(create_app()) as c:
        yield c
    kbview._views.clear()


def test_a_kb_with_an_artifact_layer_serves_it_with_the_cites(client):
    r = client.get("/api/artifacts", params={"kb": "code"})
    assert r.status_code == 200
    g = ArtifactGraph.model_validate(r.json())
    assert [v.id for v in g.views] == ["dependencies"]
    assert g.cites == {"buffer-copy": ["F0a1b2", "F3c4d5"], "build-graph": ["F3c4d5"]}
    # a field the builder added and the model does not list comes through
    assert r.json()["nodes"][3]["doc"] == "a field a builder adds"


def test_the_active_kb_without_one_is_a_404(client):
    r = client.get("/api/artifacts")
    assert r.status_code == 404
    assert "no artifact layer" in r.json()["detail"]


def test_an_unknown_kb_is_a_404(client):
    r = client.get("/api/artifacts", params={"kb": "nope"})
    assert r.status_code == 404
    assert "unknown knowledge base" in r.json()["detail"]


def test_the_route_is_in_the_schema(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/artifacts" in paths

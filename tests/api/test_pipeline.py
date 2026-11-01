"""GET /api/pipeline — canned snapshot (the real build runs lint, which rewrites index.md and corpus.tsv)."""
from unittest import mock

from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.pipeline import PipelineSnapshot

CANNED = {"generated_at": "2026-10-24T00:00:00Z", "items": [{"path": "raw/printed-docs/2020-a.pdf", "depth": "easy"}],
          "inbox": [], "recent": [{"dest": "x"}], "coherence": [], "counts": {"queued": 1}, "legacy_extra": True}


def test_pipeline_model_and_passthrough():
    with TestClient(create_app()) as c, \
         mock.patch("kb_distillery.services.pipeline.build_digestion_snapshot", return_value=CANNED):
        r = c.get("/api/pipeline")
    assert r.status_code == 200
    PipelineSnapshot.model_validate(r.json())
    assert r.json() == CANNED                      # the typed route is a superset: same JSON as legacy


"""GET /api/relations/proposals: accepted and low-confidence proposals, filtered by range and kind, read-only."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from kb import paths
from kb.api.app import create_app
from kb.api.models.relations import RelationProposals


def row(a, b, kind, conf, **kw):
    return {"from": a, "to": b, "kind": kind, "note": kw.get("note", ""), "confidence": conf,
            "evidence": kw.get("evidence", "e"), "origin": "llm", "run": "r1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    cache = tmp_path / ".cache"
    (cache / "relations-propose" / "r1").mkdir(parents=True)
    accepted = [row("a", "b", "uses", 0.9), row("a", "c", "extends", 0.6), row("b", "c", "uses", 1.0)]
    (cache / "relations-proposals.jsonl").write_text("".join(json.dumps(r) + "\n" for r in accepted))
    rejected = [{**row("c", "a", "uses", 0.35), "reason": "confidence 0.35 < 0.5"},
                {**row("c", "b", "extends", 0.05), "reason": "confidence 0.05 < 0.5"},
                {**row("c", "a", "addresses", 0.4), "reason": "addresses does not join paper → idea"},
                {**row("a", "b", "uses", 0.3), "reason": "confidence 0.3 < 0.5"}]            # same key as an accepted one
    state = {"run": "r1", "subjects": {"c": {"status": "done", "proposals": [], "rejected": rejected}}}
    (cache / "relations-propose" / "r1" / "state.json").write_text(json.dumps(state))
    monkeypatch.setattr(paths, "ROOT", str(tmp_path))
    monkeypatch.setattr("kb.services.relation_proposals._titles", lambda slugs: {s: s.upper() for s in slugs})
    with TestClient(create_app()) as c:
        yield c


def get(client, **params):
    r = client.get("/api/relations/proposals", params=params)
    assert r.status_code == 200, r.text
    body = RelationProposals.model_validate(r.json())
    return r.json(), body


def test_everything_is_returned_best_first_with_the_json_key_from(client):
    raw, body = get(client)
    assert body.total == body.shown == 5                      # 3 accepted + 2 low-confidence; structural + duplicate dropped
    assert [r["confidence"] for r in raw["rows"]] == [1.0, 0.9, 0.6, 0.35, 0.05]
    assert raw["rows"][0]["from"] == "b" and raw["rows"][0]["from_title"] == "B"


def test_a_range_picks_rows_and_keeps_totals(client):
    raw, _ = get(client, min=0.9, max=1.0)
    assert [r["confidence"] for r in raw["rows"]] == [1.0, 0.9]
    assert raw["total"] == 5 and raw["shown"] == 2
    raw, _ = get(client, min=0.0, max=0.1)
    assert [r["confidence"] for r in raw["rows"]] == [0.05]
    assert raw["rows"][0]["status"] == "low-confidence"


def test_a_kind_narrows_rows_total_and_histogram(client):
    raw, _ = get(client, kind="extends")
    assert raw["total"] == 2 and raw["shown"] == 2
    assert sum(raw["histogram"]) == 2 and raw["kinds"] == ["extends", "uses"]


def test_the_histogram_has_ten_buckets_and_one_point_zero_lands_in_the_last(client):
    raw, _ = get(client)
    assert len(raw["histogram"]) == 10 and sum(raw["histogram"]) == 5
    assert raw["histogram"][9] == 2 and raw["histogram"][0] == 1      # 0.9 and 1.0 ; 0.05


def test_accepted_wins_over_a_low_confidence_duplicate(client):
    raw, _ = get(client, min=0.0, max=1.0, kind="uses")
    assert sorted(r["confidence"] for r in raw["rows"]) == [0.35, 0.9, 1.0]       # 0.3 duplicate of a->b uses dropped


def test_out_of_range_parameters_are_a_422(client):
    assert client.get("/api/relations/proposals", params={"min": 1.5}).status_code == 422


def test_no_proposals_at_all_is_an_empty_answer(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", str(tmp_path / "empty"))
    raw, _ = get(client)
    assert raw == {"rows": [], "total": 0, "shown": 0, "kinds": [], "histogram": [0] * 10}

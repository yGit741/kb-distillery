"""POST /api/proposals/{id}/checks/semantic and the `semantic` flag, with a fake model; read-only mode refuses."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.server.app import create_app
from kb_distillery.server.models.proposals import Proposal, SemanticResult, SuggestionList
from tests.proposals.conftest import kb, read  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _body(kb, **extra):  # noqa: F811
    new = read(kb, "alpha").replace("is strong.", "is certainly true.")
    return {"title": "Strengthen", "ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new}], **extra}


def _fake(hunk_id):
    row = {"code": "overclaim", "severity": "warning", "message": "Too strong.", "hunk_id": hunk_id,
           "evidence": "More text here.", "neighbour_slug": "beta"}
    return llm.Result(id="r0", text=json.dumps({"findings": [row]}))


def test_endpoint_runs_tier2_and_the_proposal_carries_it(client, kb):  # noqa: F811
    p = Proposal.model_validate(client.post("/api/proposals", json=_body(kb), headers=LOOPBACK).json())
    with mock.patch.object(llm, "ask", return_value=_fake(p.hunks[0].id)) as ask:
        r = client.post(f"/api/proposals/{p.id}/checks/semantic", json={"backend": "api"}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = SemanticResult.model_validate(r.json())
    assert out.findings[0].code == "overclaim" and out.findings[0].neighbour_slug == "beta"
    assert ask.call_args.kwargs["backend"] == "api"
    got = Proposal.model_validate(client.get(f"/api/proposals/{p.id}").json())
    assert [f.code for f in got.checks.tier2] == ["overclaim"] and got.check_counts.blocking == 0


def test_semantic_flag_on_create_and_revision(client, kb):  # noqa: F811
    with mock.patch.object(llm, "ask", side_effect=lambda *a, **k: llm.Result(id="r0", text='{"findings": []}')) as ask:
        r = client.post("/api/proposals", json=_body(kb, semantic=True, backend="batch"), headers=LOOPBACK)
        pid = r.json()["id"]
        client.post(f"/api/proposals/{pid}/revisions", json={"ops": _body(kb)["ops"], "semantic": True},
                    headers=LOOPBACK)
    assert r.status_code == 200 and ask.call_count == 2 and ask.call_args_list[0].kwargs["backend"] == "batch"


def test_bad_backend_is_rejected_and_unknown_proposal_is_404(client, kb):  # noqa: F811
    p = client.post("/api/proposals", json=_body(kb), headers=LOOPBACK).json()
    assert client.post(f"/api/proposals/{p['id']}/checks/semantic", json={"backend": "magic"},
                       headers=LOOPBACK).status_code == 422
    assert client.post("/api/proposals/abcd1234/checks/semantic", headers=LOOPBACK).status_code == 404


def test_read_only_refuses_without_calling_a_model(client, kb, monkeypatch):  # noqa: F811
    p = client.post("/api/proposals", json=_body(kb), headers=LOOPBACK).json()
    monkeypatch.setenv("KB_READ_ONLY", "1")
    with mock.patch.object(llm, "ask", side_effect=AssertionError("a model was called")):
        r = client.post(f"/api/proposals/{p['id']}/checks/semantic", headers=LOOPBACK)
    assert r.status_code == 405


def test_suggestions_endpoint_lists_nightly_records(client, kb):  # noqa: F811
    from kb_distillery.proposals import nightly
    nightly._suggest(kb, {"kind": "oversized", "slugs": ["alpha"], "detail": "big"}, "Split it.")
    got = SuggestionList.model_validate(client.get("/api/proposals/suggestions").json())
    assert got.suggestions[0].finding == "oversized" and got.suggestions[0].slugs == ["alpha"]

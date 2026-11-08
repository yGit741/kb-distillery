"""/api/proposals over HTTP on a temp kb repo (tests/proposals/conftest.py builds it); the real kb is never written."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.proposals import (ApplyResult, Proposal, ProposalList, ProposalRender)
from tests.ops.test_view import commits
from tests.proposals.conftest import kb, read  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _create(client, kb):  # noqa: F811
    new = read(kb, "alpha").replace("is strong.", "may hold.").replace("More text here.", "Other text.")
    body = {"title": "Soften alpha", "producer": {"kind": "chat", "instruction": "soften this"},
            "ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new, "reason": "too strong"}]}
    r = client.post("/api/proposals", json=body, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    return Proposal.model_validate(r.json())


def test_full_flow(client, kb):  # noqa: F811
    p = _create(client, kb)
    assert p.status == "open" and p.revision == 1 and len(p.hunks) == 2 and p.hunks[0].reason == "too strong"

    listed = ProposalList.model_validate(client.get("/api/proposals").json()).proposals
    assert [s.id for s in listed] == [p.id] and listed[0].counts.hunks == 2 and listed[0].pages == ["alpha"]
    assert client.get("/api/proposals?status=applied").json() == {"proposals": []}

    got = Proposal.model_validate(client.get(f"/api/proposals/{p.id}").json())
    assert got.stale is False and [h.id for h in got.hunks] == [h.id for h in p.hunks]

    rendered = ProposalRender.model_validate(client.get(f"/api/proposals/{p.id}/render").json())
    page = rendered.pages[0]
    assert page.slug == "alpha" and {h.id for h in page.hunks} == {h.id for h in p.hunks}
    assert all(0 <= h.at < len(page.blocks) for h in page.hunks) and "Mine, keep me." in page.my_notes

    first, second = p.hunks
    r = client.post(f"/api/proposals/{p.id}/decisions", json={"hunk_id": first.id, "decision": "accept"}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["decisions"][first.id]["decision"] == "accept"
    r = client.post(f"/api/proposals/{p.id}/decisions", headers=LOOPBACK,
                    json={"decisions": [{"hunk_id": second.id, "decision": "reject", "comment": "keep"}]})
    assert r.json()["counts"] == {"hunks": 2, "accepted": 1, "rejected": 1, "corrected": 0}

    n = commits(kb)
    r = client.post(f"/api/proposals/{p.id}/apply", headers=LOOPBACK)
    assert r.status_code == 200, r.text
    assert ApplyResult.model_validate(r.json()).kb_version.startswith("kb-") and commits(kb) == n + 1
    assert "may hold." in read(kb, "alpha") and "More text here." in read(kb, "alpha")
    assert client.post(f"/api/proposals/{p.id}/apply", headers=LOOPBACK).status_code == 409


def test_revision_and_reject(client, kb):  # noqa: F811
    p = _create(client, kb)
    new = read(kb, "alpha").replace("is strong.", "might hold.")
    r = client.post(f"/api/proposals/{p.id}/revisions", headers=LOOPBACK,
                    json={"ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new}], "note": "gentler"})
    assert r.status_code == 200 and r.json()["revision"] == 2 and len(r.json()["revisions"]) == 2
    r = client.post(f"/api/proposals/{p.id}/reject", json={"reason": "not now"}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["rejected"]["reason"] == "not now"
    assert client.post(f"/api/proposals/{p.id}/decisions", headers=LOOPBACK,
                       json={"hunk_id": "x", "decision": "accept"}).status_code == 409


def test_error_shapes(client, kb):  # noqa: F811
    assert client.get("/api/proposals/deadbeef").status_code == 404
    assert client.get("/api/proposals/..%2Fx").status_code == 404
    bad = client.post("/api/proposals", headers=LOOPBACK, json={"title": "x", "ops": [{"kind": "edit_page", "slug": "nope", "new_text": "a"}]})
    assert bad.status_code == 400 and "no page" in bad.json()["detail"]
    assert client.post("/api/proposals", headers=LOOPBACK, json={"title": "x", "ops": [{"kind": "zap"}]}).status_code == 422
    p = _create(client, kb)
    assert client.post(f"/api/proposals/{p.id}/apply", headers=LOOPBACK).status_code == 400      # nothing accepted
    assert client.post(f"/api/proposals/{p.id}/decisions", headers=LOOPBACK, json={}).status_code == 400
    assert client.post(f"/api/proposals/{p.id}/decisions", headers=LOOPBACK,
                       json={"hunk_id": "nohunk", "decision": "accept"}).status_code == 404


def test_blocking_checks_422_and_stale_409(client, kb):  # noqa: F811
    new = read(kb, "alpha").replace("More text here.", "See [X](nope.md).")
    r = client.post("/api/proposals", headers=LOOPBACK, json={"title": "bad", "ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new}]})
    p = Proposal.model_validate(r.json())
    assert p.check_counts.errors >= 1
    client.post(f"/api/proposals/{p.id}/decisions", headers=LOOPBACK, json={"hunk_id": p.hunks[0].id, "decision": "accept"})
    r = client.post(f"/api/proposals/{p.id}/apply", headers=LOOPBACK)
    assert r.status_code == 422 and r.json()["blocking"]

    q = _create(client, kb)
    client.post(f"/api/proposals/{q.id}/decisions", headers=LOOPBACK, json={"hunk_id": q.hunks[0].id, "decision": "accept"})
    with open(f"{kb}/wiki/alpha.md", "a", encoding="utf-8") as f:
        f.write("\n")
    assert client.get(f"/api/proposals/{q.id}").json()["stale"] is True
    r = client.post(f"/api/proposals/{q.id}/apply", headers=LOOPBACK)
    assert r.status_code == 409 and r.json()["stale"] == ["alpha"]


def test_read_only_server_rejects_writes(client, kb, monkeypatch):  # noqa: F811
    p = _create(client, kb)
    monkeypatch.setenv("KB_READ_ONLY", "1")
    for path, body in (("/api/proposals", {"title": "x", "ops": []}), (f"/api/proposals/{p.id}/apply", None),
                       (f"/api/proposals/{p.id}/reject", {}),
                       (f"/api/proposals/{p.id}/decisions", {"hunk_id": p.hunks[0].id, "decision": "accept"}),
                       (f"/api/proposals/{p.id}/revisions", {"ops": []})):
        assert client.post(path, json=body, headers=LOOPBACK).status_code == 405, path
    assert client.get(f"/api/proposals/{p.id}").status_code == 200

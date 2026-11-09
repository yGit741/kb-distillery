"""Trust, feed, undo and suggestion endpoints over HTTP on the temp kb repo (nothing real is written)."""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.proposals import Feed, Proposal, SuggestionList, TrustTiers
from tests.proposals.conftest import kb, read  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _typo(client, kb, slug="alpha", **extra):  # noqa: F811
    new = read(kb, slug).replace("is strong.", "is strng.")
    body = {"title": "Typo", "producer": {"kind": "lint"}, "ops": [{"kind": "edit_page", "slug": slug, "new_text": new}], **extra}
    r = client.post("/api/proposals", json=body, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    return Proposal.model_validate(r.json())


def test_trust_endpoint(client, kb):  # noqa: F811
    t = TrustTiers.model_validate(client.get("/api/proposals/trust").json())
    assert t.source == "default" and t.auto_apply == ["links", "format", "typos"] and "tombstone" in t.explicit
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[proposals]\nauto_apply = ["links"]\n')
    t = TrustTiers.model_validate(client.get("/api/proposals/trust").json())
    assert t.source == "kb.toml" and t.auto_apply == ["links"]


def test_auto_apply_feed_and_undo(client, kb):  # noqa: F811
    open_one = _typo(client, kb)
    assert open_one.status == "open" and open_one.hunks[0].klass == "typos"
    assert open_one.decisions[open_one.hunks[0].id].suggested is True
    assert Feed.model_validate(client.get("/api/proposals/feed").json()).feed == []

    p = _typo(client, kb, "beta", auto=True)
    assert p.status == "applied" and p.applied.auto is True
    feed = Feed.model_validate(client.get("/api/proposals/feed").json()).feed
    assert [i.id for i in feed] == [p.id] and feed[0].undoable and feed[0].classes == ["typos"] and feed[0].hunks == 1
    assert client.get("/api/proposals/feed?since=2999-01-01T00:00:00%2B00:00").json() == {"feed": []}

    r = client.post(f"/api/proposals/{p.id}/undo", headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["status"] == "undone" and "is strong." in read(kb, "beta")
    assert client.post(f"/api/proposals/{p.id}/undo", headers=LOOPBACK).status_code == 409
    assert client.post("/api/proposals/deadbeef/undo", headers=LOOPBACK).status_code == 404


def test_undo_409_names_the_page(client, kb):  # noqa: F811
    p = _typo(client, kb, auto=True)
    q = _typo(client, kb)                      # a second typo-like change cannot apply twice: edit another sentence
    new = read(kb, "alpha").replace("More text here.", "Other text.")
    r = client.post(f"/api/proposals/{q.id}/revisions", headers=LOOPBACK,
                    json={"ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new}]})
    hid = r.json()["hunks"][0]["id"]
    client.post(f"/api/proposals/{q.id}/decisions", headers=LOOPBACK, json={"hunk_id": hid, "decision": "accept"})
    assert client.post(f"/api/proposals/{q.id}/apply", headers=LOOPBACK).status_code == 200
    r = client.post(f"/api/proposals/{p.id}/undo", headers=LOOPBACK)
    assert r.status_code == 409 and r.json()["pages"] == ["alpha"] and "alpha" in r.json()["detail"]


def test_suggestions_and_dismiss(client, kb):  # noqa: F811
    from kb_distillery.proposals import nightly
    os.makedirs(os.path.join(kb, "meta"), exist_ok=True)
    with open(os.path.join(kb, "meta", "coherence-warnings.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tscore\tkind\tslugs\tsummary\tstatus\nw1\t60\tinternal\talpha,beta\tpolarity clash\topen\n")
    nightly.suggest_from_coherence(kb)
    got = SuggestionList.model_validate(client.get("/api/proposals/suggestions").json()).suggestions
    assert len(got) == 1 and got[0].finding == "contradiction" and got[0].draft
    r = client.post(f"/api/proposals/suggestions/{got[0].id}/dismiss", headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert client.get("/api/proposals/suggestions").json()["suggestions"][0]["status"] == "dismissed"
    assert client.post("/api/proposals/suggestions/deadbeef/dismiss", headers=LOOPBACK).status_code == 404


def test_read_only_refuses_undo_and_dismiss_but_reads_work(client, kb, monkeypatch):  # noqa: F811
    p = _typo(client, kb, auto=True)
    monkeypatch.setenv("KB_READ_ONLY", "1")
    assert client.post(f"/api/proposals/{p.id}/undo", headers=LOOPBACK).status_code == 405
    assert client.post("/api/proposals/suggestions/deadbeef/dismiss", headers=LOOPBACK).status_code == 405
    assert client.get("/api/proposals/trust").status_code == 200
    assert client.get("/api/proposals/feed").status_code == 200

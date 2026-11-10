"""The review inbox over HTTP: status filter, grouping, class and tier counts, stale and rebase."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.proposals import ProposalList, RebaseResult
from tests.proposals.conftest import kb, read, write  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _post(client, title, ops, **kw):
    r = client.post("/api/proposals", json={"title": title, "ops": ops, **kw}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    return r.json()


def _seed(client, kb):  # noqa: F811
    a = read(kb, "alpha")
    claim = _post(client, "Soften alpha", [{"kind": "edit_page", "slug": "alpha", "new_text": a.replace("is strong.", "may hold.")}])
    link = _post(client, "Retarget beta link", [{"kind": "edit_page", "slug": "beta",
                 "new_text": read(kb, "beta").replace("[Beta](beta.md)", "[Beta](gamma.md)")}])
    multi = _post(client, "Touch two pages", [
        {"kind": "edit_page", "slug": "gamma", "new_text": read(kb, "gamma").replace("More text here.", "Other text.")},
        {"kind": "edit_page", "slug": "alpha", "new_text": a.replace("More text here.", "Other text.")}])
    return claim, link, multi


def test_counts_by_class_and_tier(client, kb):  # noqa: F811
    claim, link, multi = _seed(client, kb)
    rows = {s.id: s for s in ProposalList.model_validate(client.get("/api/proposals").json()).proposals}
    assert rows[claim["id"]].classes == {"claims": 1} and rows[claim["id"]].tiers["review"] == 1
    assert rows[claim["id"]].top_class == "claims"
    assert rows[link["id"]].classes == {"links": 1} and rows[link["id"]].tiers["auto_apply"] == 1
    assert sorted(rows[multi["id"]].pages) == ["alpha", "gamma"]


def test_group_by_page_class_time(client, kb):  # noqa: F811
    claim, link, multi = _seed(client, kb)
    by = lambda g: {x["key"]: sorted(p["id"] for p in x["proposals"])  # noqa: E731
                    for x in client.get(f"/api/proposals?group={g}").json()["groups"]}
    pages = by("page")
    assert pages["alpha"] == sorted([claim["id"], multi["id"]]) and pages["beta"] == [link["id"]]
    assert pages["gamma"] == [multi["id"]]
    classes = client.get("/api/proposals?group=class").json()["groups"]
    keys = [g["key"] for g in classes]
    assert keys.index("claims") < keys.index("links") and by("class")["links"] == [link["id"]]
    assert sorted(by("class")["claims"]) == sorted([claim["id"], multi["id"]]) and sum(g["count"] for g in classes) == 3
    days = client.get("/api/proposals?group=time").json()["groups"]
    assert len(days) >= 1 and sum(g["count"] for g in days) == 3
    assert client.get("/api/proposals?group=nope").status_code == 400


def test_status_filter_open_includes_stale(client, kb):  # noqa: F811
    claim, link, _ = _seed(client, kb)
    client.post(f"/api/proposals/{link['id']}/reject", json={}, headers=LOOPBACK)
    write(kb, "alpha", read(kb, "alpha").replace("# alpha", "# alpha\n\nIntro."))
    ids = lambda s: {p["id"] for p in client.get(f"/api/proposals?status={s}").json()["proposals"]}  # noqa: E731
    assert claim["id"] in ids("open") and claim["id"] in ids("stale") and link["id"] not in ids("open")
    assert link["id"] in ids("rejected") and ids("applied") == set() and len(ids("all")) == 3
    assert client.get("/api/proposals?status=zzz").status_code == 400


def test_stale_flips_and_rebase_endpoint(client, kb):  # noqa: F811
    a = read(kb, "alpha")
    p = _post(client, "Two", [{"kind": "edit_page", "slug": "alpha",
                               "new_text": a.replace("is strong.", "may hold.").replace("More text here.", "Other text.")}])
    assert client.get(f"/api/proposals/{p['id']}").json()["stale_pages"] == []
    write(kb, "alpha", a.replace("More text here.", "Rewritten."))
    got = client.get(f"/api/proposals/{p['id']}").json()
    assert got["stale"] is True and got["stale_pages"] == ["alpha"]
    r = client.post(f"/api/proposals/{p['id']}/rebase", headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = RebaseResult.model_validate(r.json())
    assert len(out.dropped) == 1 and out.dropped[0].slug == "alpha" and out.proposal.stale is False
    assert len(out.proposal.hunks) == 1 and out.proposal.revisions[-1].dropped[0].hunk_id == out.dropped[0].hunk_id
    assert client.post("/api/proposals/deadbeef/rebase", headers=LOOPBACK).status_code == 404


def test_feed_names_the_pages_that_block_an_undo(client, kb):  # noqa: F811
    def typo(slug):
        new = read(kb, slug).replace("is strong.", "is strng.")
        return client.post("/api/proposals", headers=LOOPBACK, json={
            "title": "Typo", "producer": {"kind": "lint"}, "auto": True,
            "ops": [{"kind": "edit_page", "slug": slug, "new_text": new}]}).json()
    first, other = typo("alpha"), typo("beta")
    assert first["status"] == "applied" and other["status"] == "applied"
    rows = {i["id"]: i for i in client.get("/api/proposals/feed").json()["feed"]}
    assert rows[first["id"]]["undoable"] is True and rows[first["id"]]["blocked_by"] == []
    # a later knowledge step on alpha blocks the undo of the first one
    new = read(kb, "alpha").replace("More text here.", "Other text.")
    q = client.post("/api/proposals", headers=LOOPBACK, json={"title": "Later", "ops": [{"kind": "edit_page", "slug": "alpha", "new_text": new}]}).json()
    client.post(f"/api/proposals/{q['id']}/decisions", headers=LOOPBACK, json={"hunk_id": q["hunks"][0]["id"], "decision": "accept"})
    assert client.post(f"/api/proposals/{q['id']}/apply", headers=LOOPBACK).status_code == 200
    rows = {i["id"]: i for i in client.get("/api/proposals/feed").json()["feed"]}
    assert rows[first["id"]]["undoable"] is False and rows[first["id"]]["blocked_by"] == ["alpha"]
    assert rows[other["id"]]["undoable"] is True

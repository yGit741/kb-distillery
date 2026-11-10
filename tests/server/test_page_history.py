"""/api/pages/{slug}/history|compare|restore on a temp kb with a few commits; the real kb is never read or written."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.page_history import PageCompare, PageHistory, RestoreResult
from kb_distillery.server.models.proposals import Proposal
from tests.ops.test_view import commits, git
from tests.proposals.conftest import kb, read, write  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


def _commit(root, subject):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", subject)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def versions(kb):  # noqa: F811
    """alpha edited twice after its first commit: (first, softened, expanded)."""
    first = git(kb, "rev-parse", "HEAD")
    write(kb, "alpha", read(kb, "alpha").replace("is strong.", "may hold."))
    soft = _commit(kb, "kb(refine): soften alpha (kb-1.0.1)")
    write(kb, "alpha", read(kb, "alpha").replace("More text here.", "Other text here."))
    exp = _commit(kb, "wip: tweak details")
    return first, soft, exp


def test_history_newest_first_with_kinds(client, versions):
    first, soft, exp = versions
    r = client.get("/api/pages/alpha/history")
    assert r.status_code == 200, r.text
    got = PageHistory.model_validate(r.json())
    assert [v.sha for v in got.versions] == [exp, soft, first]
    assert [v.kind for v in got.versions] == ["other", "refine", "other"]
    assert got.versions[0].short == exp[:len(got.versions[0].short)] and got.versions[1].subject.startswith("kb(refine):")
    assert got.versions[1].date[:2] == "20"


def test_history_of_a_page_without_commits_is_empty(client):
    assert client.get("/api/pages/nope/history").json()["versions"] == []
    assert client.get("/api/pages/..%2Fx/history").status_code in (400, 404)


def test_compare_two_versions_and_working(client, versions):
    first, soft, exp = versions
    r = client.get("/api/pages/alpha/compare", params={"from": first, "to": soft})
    assert r.status_code == 200, r.text
    got = PageCompare.model_validate(r.json())
    assert got.from_ == first and got.to == soft and len(got.hunks) == 1
    h = got.hunks[0]
    assert "is strong." in h.before and "may hold." in h.after and h.klass and h.tokens
    assert got.page.blocks and 0 <= h.at < len(got.page.blocks)
    assert r.json()["from"] == first
    assert len(client.get("/api/pages/alpha/compare", params={"from": first}).json()["hunks"]) == 2   # to defaults to working
    assert client.get("/api/pages/alpha/compare", params={"from": exp, "to": "working"}).json()["hunks"] == []


def test_unknown_sha_is_404(client, versions):
    first = versions[0]
    assert client.get("/api/pages/alpha/compare", params={"from": "0" * 40, "to": first}).status_code == 404
    assert client.get("/api/pages/alpha/compare", params={"from": first, "to": "deadbeef"}).status_code == 404
    assert client.get("/api/pages/alpha/compare", params={"from": "--oneline"}).status_code == 404
    assert client.post("/api/pages/alpha/restore", json={"sha": "0" * 40}, headers=LOOPBACK).status_code == 404


def test_restore_makes_a_proposal_and_never_writes(client, kb, versions):  # noqa: F811
    first, soft, exp = versions
    before, n = read(kb, "alpha"), commits(kb)
    r = client.post("/api/pages/alpha/restore", json={"sha": first}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    pid = RestoreResult.model_validate(r.json()).proposal_id
    assert read(kb, "alpha") == before and commits(kb) == n
    p = Proposal.model_validate(client.get(f"/api/proposals/{pid}").json())
    assert p.status == "open" and p.producer.kind == "restore" and p.producer.context["sha"] == first
    assert p.revisions[0].ops[0].kind == "edit_page" and len(p.hunks) == 2
    assert {h.slug for h in p.hunks} == {"alpha"} and all(h.klass for h in p.hunks)


def test_restore_chosen_block_only_and_keeps_my_notes(client, kb, versions):  # noqa: F811
    first, soft, exp = versions
    hunks = client.get("/api/pages/alpha/compare", params={"from": first}).json()["hunks"]
    strong = next(h["id"] for h in hunks if "is strong." in h["before"])
    r = client.post("/api/pages/alpha/restore", json={"sha": first, "blocks": [strong]}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    p = Proposal.model_validate(client.get(f"/api/proposals/{r.json()['proposal_id']}").json())
    assert len(p.hunks) == 1 and "is strong." in p.hunks[0].after and "may hold." in p.hunks[0].before
    new = p.revisions[0].ops[0].new_text
    assert "Other text here." in new and "Mine, keep me." in new
    bad = client.post("/api/pages/alpha/restore", json={"sha": first, "blocks": ["nope"]}, headers=LOOPBACK)
    assert bad.status_code == 400


def test_restore_of_the_current_text_is_409_and_needs_loopback(client, versions):
    exp = versions[2]
    assert client.post("/api/pages/alpha/restore", json={"sha": exp}, headers=LOOPBACK).status_code == 409
    assert client.post("/api/pages/alpha/restore", json={"sha": exp}).status_code in (403, 400)


def test_block_restore_against_an_older_version_is_refused(client, versions):
    first, soft, exp = versions
    hunks = client.get("/api/pages/alpha/compare", params={"from": first, "to": soft}).json()["hunks"]
    r = client.post("/api/pages/alpha/restore", json={"sha": first, "blocks": [hunks[0]["id"]], "to": soft}, headers=LOOPBACK)
    assert r.status_code == 400

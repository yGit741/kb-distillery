"""Merge / split / extract producers on the temp kb (tests/proposals/conftest.py); no model, no network."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.proposals import restructure, service
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.app import create_app
from kb_distillery.server.models.proposals import RestructureResult
from tests.ops.test_view import git
from tests.proposals.conftest import kb, read, write  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}

LONG = ("---\ntype: idea\nlayer: concept\ntitle: Long\ndescription: A long one.\n---\n\n# Long\n\nPart one text.\n\n"
        "Part one more.\n\n## Middle\n\nMiddle text.\n\n## End\n\nEnd text.\n\n## My notes\n\nMine, keep me.\n")


@pytest.fixture
def pages(kb):  # noqa: F811
    write(kb, "alpha", "---\ntype: idea\nlayer: concept\ndescription: Alpha.\ntags: [x, y]\naliases: [old-alpha]\n---\n\n"
                       "# Alpha\n\nAlpha claim.\n\n## My notes\n\nAlpha mine.\n")
    write(kb, "beta", "---\ntype: idea\nlayer: concept\ndescription: Beta.\ntags: [y, z]\n---\n\n"
                      "# Beta\n\nBeta claim.\n\n## Detail\n\nBeta detail.\n\n## My notes\n\nBeta mine.\n")
    write(kb, "gamma", "---\ntype: idea\nlayer: concept\ndescription: Gamma.\n---\n\n# Gamma\n\nSee [Beta](beta.md) and "
                        "[again](beta.md#detail). Also [Alpha](alpha.md).\n\n## My notes\n\nIn notes [Beta](beta.md).\n")
    write(kb, "long", LONG)
    write(kb, "ref", "---\ntype: idea\nlayer: concept\n---\n\n# Ref\n\nPoints at [Long](long.md).\n")
    git(kb, "add", "-A")
    git(kb, "commit", "-q", "-m", "chore: pages (retro)")
    return kb


def ops_of(p, kind):
    return [o for o in p["revisions"][p["current"]]["ops"] if o["kind"] == kind]


def test_merge_concatenates_and_keeps_my_notes(pages):
    p = restructure.merge(["alpha", "beta"], "alpha")
    edit = ops_of(p, "edit_page")[0]
    assert edit["slug"] == "alpha"
    text = edit["new_text"]
    assert "Alpha claim." in text and "## Beta\n\nBeta claim." in text and "### Detail" in text
    assert text.rstrip().endswith("Alpha mine.")                       # the survivor's own notes stay last, untouched
    assert "### From Beta\n\nBeta mine." in text                       # the other page's notes are carried, not dropped
    assert "tags: [x, y, z]" in text and "old-alpha" in text and "beta" in text.split("---")[1]
    assert "description: Alpha." in text                                # the survivor wins on scalars
    assert p["producer"]["kind"] == "restructure" and p["producer"]["context"]["action"] == "merge"


def test_merge_tombstone_redirect_and_ripple(pages):
    p = restructure.merge(["alpha", "beta"], "alpha")
    tomb = ops_of(p, "tombstone_page")
    assert [(o["slug"], o["redirect_to"]) for o in tomb] == [("beta", "alpha")]
    rw = ops_of(p, "rewrite_link")
    assert [(o["slug"], o["from_slug"], o["to_slug"]) for o in rw] == [("gamma", "beta", "alpha")]
    assert p["ripple"] == [{"slug": "gamma", "links": 2}]               # the link inside My notes is not counted
    assert p["status"] == "open" and not p["checks"]["tier1"]


def test_merge_applies_end_to_end(pages):
    p = restructure.merge(["alpha", "beta"], "alpha")
    for h in p["hunks"]:
        service.decide(p["id"], [{"hunk_id": h["id"], "decision": "accept"}], root=pages)
    service.apply(p["id"], root=pages)
    assert "[Beta](alpha.md)" in read(pages, "gamma") and "[again](alpha.md#detail)" in read(pages, "gamma")
    assert "In notes [Beta](beta.md)." in read(pages, "gamma")          # My notes never rewritten
    tomb = read(pages, "beta")
    assert "redirect_to: alpha.md" in tomb and "This page moved to [Alpha](alpha.md)." in tomb and "Beta mine." in tomb
    assert "Beta claim." in read(pages, "alpha")


def test_merge_validation(pages):
    for args in ((["alpha"], "alpha"), (["alpha", "beta"], "gamma"), (["alpha", "nope"], "alpha")):
        with pytest.raises(ProposalError) as e:
            restructure.merge(*args)
        assert e.value.status in (400, 404)


def test_merge_with_llm_pass(pages, monkeypatch):
    seen = {}

    def fake_ask(prompt, **kw):
        seen["backend"] = kw.get("backend")
        return llm.Result(id="r1", text="# Alpha\n\nTidy merged claim, see [[gamma]].\n")
    monkeypatch.setattr(llm, "ask", fake_ask)
    p = restructure.merge(["alpha", "beta"], "alpha", backend="api")
    text = ops_of(p, "edit_page")[0]["new_text"]
    assert seen["backend"] == "api" and "Tidy merged claim" in text and "[Gamma](gamma.md)" in text
    assert text.startswith("---\n") and "tags: [x, y, z]" in text and text.rstrip().endswith("Alpha mine.")


def test_split_pieces_and_continued_links(pages):
    p = restructure.split("long", [5, 7], ["Middle part", "End part"])
    creates = ops_of(p, "create_page")
    assert [o["slug"] for o in creates] == ["middle-part", "end-part"]
    assert "title: \"Middle part\"" in creates[0]["text"] and "# Middle part" in creates[0]["text"]
    assert "Middle text." in creates[0]["text"] and "End text." in creates[1]["text"]
    edit = ops_of(p, "edit_page")[0]["new_text"]
    assert "Part one more." in edit and "Middle text." not in edit
    assert "## Continued in\n\n- [Middle part](middle-part.md)\n- [End part](end-part.md)" in edit
    assert edit.rstrip().endswith("Mine, keep me.")
    assert p["ripple"] == [{"slug": "ref", "links": 1}]
    assert p["producer"]["context"]["action"] == "split"


def test_split_slug_collision_gets_suffix(pages):
    p = restructure.split("long", [5, 7], ["Alpha", "Alpha"][:1] + ["Other"])
    assert [o["slug"] for o in ops_of(p, "create_page")] == ["alpha-2", "other"]


def test_extract_range_and_link_left_behind(pages):
    p = restructure.extract("long", 5, 6, "Middle bit")
    new = ops_of(p, "create_page")[0]
    assert new["slug"] == "middle-bit" and "## Middle" in new["text"] and "Middle text." in new["text"]
    edit = ops_of(p, "edit_page")[0]["new_text"]
    assert "[Middle bit](middle-bit.md)" in edit and "Middle text." not in edit and "End text." in edit
    assert edit.rstrip().endswith("Mine, keep me.") and p["ripple"] == [{"slug": "ref", "links": 1}]


def test_extract_and_split_apply(pages):
    p = restructure.extract("long", 5, 6, "Middle bit")
    for h in p["hunks"]:
        service.decide(p["id"], [{"hunk_id": h["id"], "decision": "accept"}], root=pages)
    service.apply(p["id"], root=pages)
    assert "Middle text." in read(pages, "middle-bit") and "Middle text." not in read(pages, "long")
    assert "Mine, keep me." in read(pages, "long")


@pytest.mark.parametrize("cuts,titles", [([], []), ([5], []), ([5], ["A", "B"]), ([0], ["A"]), ([2], ["A"]),
                                          ([99], ["A"]), ([7, 5], ["A", "B"]), ([5, 5], ["A", "B"]), ([5], [""]),
                                          ([5, 7], ["Same", "same"]), (["x"], ["A"])])
def test_split_invalid_cuts(pages, cuts, titles):
    with pytest.raises(ProposalError) as e:
        restructure.split("long", cuts, titles)
    assert e.value.status == 400


@pytest.mark.parametrize("a,b,title", [(0, 3, "T"), (6, 5, "T"), (3, 99, "T"), (3, 4, " ")])
def test_extract_invalid_range(pages, a, b, title):
    with pytest.raises(ProposalError) as e:
        restructure.extract("long", a, b, title)
    assert e.value.status == 400


def test_http_endpoints(pages):
    with TestClient(create_app()) as c:
        r = c.post("/api/proposals/restructure/merge", json={"slugs": ["alpha", "beta"], "survivor": "alpha"},
                   headers=LOOPBACK)
        assert r.status_code == 200, r.text
        got = RestructureResult.model_validate(r.json())
        assert got.ripple[0].slug == "gamma" and got.producer.kind == "restructure"
        r = c.post("/api/proposals/restructure/split", json={"slug": "long", "cuts": [5], "titles": ["Part two"]},
                   headers=LOOPBACK)
        assert r.status_code == 200 and r.json()["ripple"] == [{"slug": "ref", "links": 1}]
        r = c.post("/api/proposals/restructure/extract",
                   json={"slug": "long", "from_at": 5, "to_at": 5, "title": "Mid"}, headers=LOOPBACK)
        assert r.status_code == 200
        bad = c.post("/api/proposals/restructure/split", json={"slug": "long", "cuts": [2], "titles": ["x"]},
                     headers=LOOPBACK)
        assert bad.status_code == 400
        assert c.post("/api/proposals/restructure/merge", json={"slugs": ["alpha"], "survivor": "alpha"},
                      headers=LOOPBACK).status_code == 400


def test_blocks_and_merge_preview_endpoints(pages):
    with TestClient(create_app()) as c:
        r = c.get("/api/proposals/restructure/blocks", params={"slug": "long"})
        assert r.status_code == 200
        got = r.json()
        assert got["first"] == 2 and got["blocks"][5]["text"].startswith("## Middle") and len(got["blocks"]) == 9
        assert c.get("/api/proposals/restructure/blocks", params={"slug": "nope"}).status_code == 404
        r = c.get("/api/proposals/restructure/merge-preview", params={"slugs": "alpha,beta", "survivor": "alpha"})
        assert r.status_code == 200 and r.json() == {"ripple": [{"slug": "gamma", "links": 2}]}
        assert c.get("/api/proposals/restructure/merge-preview", params={"slugs": "alpha", "survivor": "alpha"}).status_code == 400

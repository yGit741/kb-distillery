"""Stale detection and rebase: hunks are recomputed against the changed page, vanished ones dropped, decisions kept."""
import pytest

from kb_distillery.proposals import service
from kb_distillery.proposals.model import ProposalError
from tests.proposals.conftest import kb, read, write  # noqa: F401  (the fixture)


def _edit(kb_root, title="Two edits"):
    new = read(kb_root, "alpha").replace("is strong.", "may hold.").replace("More text here.", "Other text.")
    return service.create(title, [{"kind": "edit_page", "slug": "alpha", "new_text": new}], root=kb_root)


def _by_text(p, needle):
    return next(h for h in p["hunks"] if needle in h["after"])


def test_stale_flips_after_an_edit_and_names_the_page(kb):  # noqa: F811
    p = _edit(kb)
    assert p["status"] == "open" and p["stale_pages"] == []
    write(kb, "alpha", read(kb, "alpha").replace("# alpha", "# alpha\n\nIntro added."))
    got = service.get(p["id"], root=kb)
    assert got["status"] == "stale" and got["stale"] is True and got["stale_pages"] == ["alpha"]
    row = service.list_proposals("open", root=kb)[0]
    assert row["status"] == "stale" and row["stale_pages"] == ["alpha"]


def test_rebase_without_a_change_is_a_no_op(kb):  # noqa: F811
    p = _edit(kb)
    out = service.rebase(p["id"], root=kb)
    assert out["dropped"] == [] and out["proposal"]["revision"] == 1


def test_rebase_keeps_surviving_hunks_and_decisions_and_drops_the_vanished(kb):  # noqa: F811
    p = _edit(kb)
    soften, other = _by_text(p, "may hold"), _by_text(p, "Other text")
    service.decide(p["id"], [{"hunk_id": soften["id"], "decision": "accept"},
                             {"hunk_id": other["id"], "decision": "reject", "comment": "keep"}], root=kb)
    # the owner rewrote the "More text" paragraph and added an intro elsewhere
    write(kb, "alpha", read(kb, "alpha").replace("More text here.", "Rewritten by hand.").replace(
        "# alpha", "# alpha\n\nIntro added."))
    out = service.rebase(p["id"], root=kb)
    q = out["proposal"]
    assert [d["hunk_id"] for d in out["dropped"]] == [other["id"]]
    assert out["dropped"][0]["klass"] and out["dropped"][0]["before"].startswith("More text here.")
    assert q["status"] == "open" and q["stale_pages"] == [] and q["revision"] == 2
    assert [h["id"] for h in q["hunks"]] == [soften["id"]]
    assert q["decisions"][soften["id"]]["decision"] == "accept" and other["id"] not in q["decisions"]
    assert q["revisions"][-1]["dropped"][0]["hunk_id"] == other["id"]
    service.apply(p["id"], root=kb)
    text = read(kb, "alpha")
    assert "may hold." in text and "Intro added." in text and "Rewritten by hand." in text and "Mine, keep me." in text


def test_rebase_refuses_when_nothing_survives(kb):  # noqa: F811
    new = read(kb, "alpha").replace("More text here.", "Other text.")
    p = service.create("One edit", [{"kind": "edit_page", "slug": "alpha", "new_text": new}], root=kb)
    write(kb, "alpha", read(kb, "alpha").replace("More text here.", "Gone."))
    with pytest.raises(ProposalError) as e:
        service.rebase(p["id"], root=kb)
    assert e.value.status == 409 and len(e.value.extra["dropped"]) == 1


def test_rebase_drops_a_create_page_whose_page_now_exists(kb):  # noqa: F811
    new = read(kb, "alpha").replace("is strong.", "may hold.")
    p = service.create("New and edit", [
        {"kind": "edit_page", "slug": "alpha", "new_text": new},
        {"kind": "create_page", "slug": "delta", "text": "---\ntype: idea\nlayer: concept\ndescription: D.\n---\n\n# delta\n\nBody.\n"}],
        root=kb)
    assert sorted(p["base"]) == ["alpha", "delta"]
    write(kb, "delta")
    out = service.rebase(p["id"], root=kb)
    assert [d["slug"] for d in out["dropped"]] == ["delta"] and out["dropped"][0]["klass"] == "new_page"
    assert [h["slug"] for h in out["proposal"]["hunks"]] == ["alpha"]


def test_rebase_anchors_on_the_copy_nearest_the_original_position(kb):  # noqa: F811
    twice = read(kb, "alpha").replace("More text here.", "Same line.\n\n## Again\n\nSame line.")
    write(kb, "alpha", twice)
    p = service.create("Second copy", [{"kind": "edit_page", "slug": "alpha",
                                        "new_text": twice[::-1][::-1].replace("Same line.\n\n## My notes", "Changed line.\n\n## My notes")}], root=kb)
    assert len(p["hunks"]) == 1 and p["hunks"][0]["before"].startswith("Same line.")
    write(kb, "alpha", twice.replace("# alpha", "# alpha\n\nIntro."))
    out = service.rebase(p["id"], root=kb)
    text = out["proposal"]["hunks"][0]["after"]
    assert out["dropped"] == [] and text.startswith("Changed line.")
    service.decide(p["id"], [{"hunk_id": out["proposal"]["hunks"][0]["id"], "decision": "accept"}], root=kb)
    service.apply(p["id"], root=kb)
    body = read(kb, "alpha")
    assert body.index("Same line.") < body.index("## Again") < body.index("Changed line.")

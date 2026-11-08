"""Apply goes through ops begin/commit on a temp kb repo: one commit, only accepted hunks, My notes kept; stale refuses."""
import pytest

from kb_distillery.config.flags.runtime import effective
from kb_distillery.proposals import service
from kb_distillery.proposals.model import ProposalError
from tests.ops.test_view import commits, git, head_files
from tests.proposals.conftest import read, write


def _two_hunks(kb):
    new = read(kb, "alpha").replace("is strong.", "may hold.").replace("More text here.", "Other text.")
    return service.create("Soften alpha", [{"kind": "edit_page", "slug": "alpha", "new_text": new}],
                          {"kind": "chat", "instruction": "soften this"})


def test_apply_accepted_hunks_as_one_commit(kb):
    p = _two_hunks(kb)
    first, second = p["hunks"]
    service.decide(p["id"], [{"hunk_id": first["id"], "decision": "accept"},
                             {"hunk_id": second["id"], "decision": "reject"}])
    n = commits(kb)
    out = service.apply(p["id"])
    assert commits(kb) == n + 1 and out["commit"] and out["kb_version"].startswith("kb-")
    subject = git(kb, "log", "-1", "--format=%s")
    assert subject.startswith("kb(refine): propose: Soften alpha (1 hunks)")
    assert head_files(kb) == {"wiki/alpha.md", "wiki/log.md"}       # .local/proposals is never committed
    text = read(kb, "alpha")
    assert "may hold." in text and "More text here." in text
    assert text.endswith("## My notes\n\nMine, keep me. [[gamma]]\n")
    assert service.get(p["id"])["status"] == "applied"
    with pytest.raises(ProposalError) as e:
        service.apply(p["id"])
    assert e.value.status == 409


def test_stale_page_refuses_apply(kb):
    p = _two_hunks(kb)
    service.decide(p["id"], [{"hunk_id": p["hunks"][0]["id"], "decision": "accept"}])
    write(kb, "alpha", read(kb, "alpha").replace("# alpha", "# alpha (edited by hand)"))
    assert service.get(p["id"])["stale"] is True
    n = commits(kb)
    with pytest.raises(ProposalError) as e:
        service.apply(p["id"])
    assert e.value.status == 409 and commits(kb) == n


def test_blocking_check_refuses_until_its_hunk_is_rejected(kb):
    new = read(kb, "alpha").replace("is strong.", "may hold.").replace("More text here.", "See [X](nope.md).")
    p = service.create("bad link", [{"kind": "edit_page", "slug": "alpha", "new_text": new}])
    good, bad = p["hunks"]
    service.decide(p["id"], [{"hunk_id": good["id"], "decision": "accept"}, {"hunk_id": bad["id"], "decision": "accept"}])
    with pytest.raises(ProposalError) as e:
        service.apply(p["id"])
    assert e.value.status == 422
    service.decide(p["id"], [{"hunk_id": bad["id"], "decision": "reject"}])
    assert service.apply(p["id"])["commit"]
    assert "nope.md" not in read(kb, "alpha")


def test_revision_keeps_decisions_of_unchanged_hunks(kb):
    p = _two_hunks(kb)
    first, second = p["hunks"]
    service.decide(p["id"], [{"hunk_id": first["id"], "decision": "accept"},
                             {"hunk_id": second["id"], "decision": "correct", "comment": "gentler"}])
    new = read(kb, "alpha").replace("is strong.", "may hold.").replace("More text here.", "Slightly other text.")
    p2 = service.revise(p["id"], [{"kind": "edit_page", "slug": "alpha", "new_text": new}], "the owner's correction")
    assert p2["revision"] == 2 and list(p2["decisions"]) == [first["id"]]


@pytest.mark.flag("ui.proposals", True)
def test_flag_on_proposals_ui(kb):
    assert effective("ui.proposals") is True
    assert service.list_proposals() == []


@pytest.mark.flag("ui.proposals", False)
def test_flag_off_core_still_works(kb):
    assert effective("ui.proposals") is False
    assert service.create("t", [{"kind": "set_frontmatter", "slug": "beta", "key": "maturity", "value": "draft"}])["id"]

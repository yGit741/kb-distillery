"""Tier-1 checks on a temp kb: unresolved links and privacy terms block apply, a rejected hunk unblocks."""
import pytest

from kb_distillery.proposals import checks, service
from tests.proposals.conftest import read


def _edit(kb, old, new):
    return [{"kind": "edit_page", "slug": "alpha", "new_text": read(kb, "alpha").replace(old, new)}]


def test_clean_edit_has_no_errors(kb):
    p = service.create("soften", _edit(kb, "is strong.", "may hold."))
    assert [f for f in p["checks"]["tier1"] if f["severity"] == "error"] == []


def test_unresolved_link_blocks_and_rejecting_its_hunk_unblocks(kb):
    p = service.create("link", _edit(kb, "More text here.", "See [Nowhere](no-such-page.md)."))
    errs = [f for f in p["checks"]["tier1"] if f["severity"] == "error"]
    assert errs and errs[0]["code"] == "link" and errs[0]["hunk_id"] == p["hunks"][0]["id"]
    assert checks.blocking(p["checks"]["tier1"], {}) == errs
    assert checks.blocking(p["checks"]["tier1"], {errs[0]["hunk_id"]: {"decision": "reject"}}) == []


def test_link_to_a_page_created_in_the_same_proposal_resolves(kb):
    ops = _edit(kb, "More text here.", "See [New](new-idea.md).")
    ops.append({"kind": "create_page", "slug": "new-idea", "text": "---\ntype: idea\nlayer: concept\n---\n\n# new-idea\n"})
    p = service.create("link", ops)
    assert [f for f in p["checks"]["tier1"] if f["code"] == "link"] == []


def test_privacy_term_blocks(kb):
    p = service.create("leak", _edit(kb, "More text here.", "Written by Zorblaxquux at home."))
    errs = [f for f in p["checks"]["tier1"] if f["code"] == "privacy"]
    assert len(errs) == 1 and errs[0]["hunk_id"] == p["hunks"][0]["id"]


def test_frontmatter_must_parse(kb):
    p = service.create("fm", [{"kind": "edit_page", "slug": "alpha", "new_text": "# no frontmatter\n\nText.\n"}])
    assert any(f["code"] == "frontmatter" and f["severity"] == "error" for f in p["checks"]["tier1"])


def test_wikilink_outside_my_notes_is_a_lint_error(kb):
    p = service.create("wl", _edit(kb, "More text here.", "See [[beta]]."))
    assert any(f["severity"] == "error" and "wikilink" in f["message"] for f in p["checks"]["tier1"])

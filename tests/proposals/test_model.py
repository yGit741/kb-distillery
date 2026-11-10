"""Hunks, the word diff and composition (pure functions, no repo)."""
import pytest

from kb_distillery.proposals import diff
from kb_distillery.proposals.model import ProposalError, validate_ops
from tests.proposals.conftest import PAGE

OLD = PAGE.format(n="alpha")


def edit(new_text, slug="alpha"):
    return validate_ops([{"kind": "edit_page", "slug": slug, "new_text": new_text, "reason": "soften"}])


def test_split_blocks_covers_text_exactly():
    blocks = diff.split_blocks(OLD)
    assert "".join(b["raw"] for b in blocks) == OLD
    assert blocks[0]["kind"] == "fm" and [b["kind"] for b in blocks].count("heading") == 3


def test_word_tokens():
    assert diff.word_tokens("The claim is strong.", "The claim is weak.") == [
        ["equal", "The claim is "], ["delete", "strong"], ["insert", "weak"], ["equal", "."]]


def test_hunks_one_per_changed_block_with_kinds_and_links():
    new = OLD.replace("is strong.", "may hold.").replace("## Details", "## Evidence").replace(
        "More text here.", "More text, see [Gamma](gamma.md).")
    hunks, results = diff.build({"alpha": OLD}, edit(new))
    assert len(hunks) == 2                       # the claim; the heading + its paragraph (one replaced run)
    prose, struct = hunks
    assert prose["kind"] == "prose" and ["delete", "strong"] in prose["tokens"]
    assert struct["kind"] == "structure" and struct["links_added"] == ["gamma"]
    assert prose["reason"] == "soften" and len({h["id"] for h in hunks}) == 2
    assert results["alpha"].endswith("## My notes\n\nMine, keep me. [[gamma]]\n")


def test_hunk_ids_are_stable_content_hashes():
    new = OLD.replace("is strong.", "may hold.")
    a, _ = diff.build({"alpha": OLD}, edit(new))
    b, _ = diff.build({"alpha": OLD}, edit(new))
    assert [h["id"] for h in a] == [h["id"] for h in b]


def test_compose_mixed_accept_reject_keeps_my_notes():
    new = OLD.replace("is strong.", "may hold.").replace("More text here.", "Other text.")
    ops = edit(new)
    hunks, _ = diff.build({"alpha": OLD}, ops)
    first, second = hunks
    out = diff.compose({"alpha": OLD}, ops, hunks, {first["id"]})["alpha"]
    assert "may hold." in out and "More text here." in out and "Other text." not in out
    assert out.endswith("## My notes\n\nMine, keep me. [[gamma]]\n")
    assert diff.compose({"alpha": OLD}, ops, hunks, set()) == {}


def test_producer_cannot_touch_my_notes():
    new = OLD.replace("Mine, keep me.", "Rewritten by an agent.")
    hunks, results = diff.build({"alpha": OLD}, edit(new))
    assert hunks == [] and results["alpha"] == OLD


def test_create_set_frontmatter_rewrite_link():
    ops = validate_ops([
        {"kind": "create_page", "slug": "delta", "text": "---\ntype: idea\n---\n\n# delta\n"},
        {"kind": "set_frontmatter", "slug": "alpha", "key": "maturity", "value": "draft"},
        {"kind": "rewrite_link", "slug": "alpha", "from_slug": "beta", "to_slug": "delta"},
    ])
    hunks, _ = diff.build({"alpha": OLD, "delta": None}, ops)
    assert [h["op"] for h in hunks] == ["create_page", "set_frontmatter", "rewrite_link"]
    assert all(h["kind"] == "structure" for h in hunks)
    out = diff.compose({"alpha": OLD, "delta": None}, ops, hunks, {h["id"] for h in hunks})
    assert "maturity: draft" in out["alpha"] and "[Beta](delta.md)" in out["alpha"]
    assert "[[gamma]]" in out["alpha"] and out["delta"].startswith("---")


def test_move_block_validates_but_does_not_apply_yet():
    ops = validate_ops([{"kind": "move_block", "from_slug": "alpha", "to_slug": "beta", "block_id": "b1"}])
    hunks, _ = diff.build({"alpha": OLD}, ops)
    with pytest.raises(ProposalError) as e:
        diff.compose({"alpha": OLD}, ops, hunks, {hunks[0]["id"]})
    assert e.value.status == 501


def test_validation_errors():
    for bad in ([], [{"kind": "nope"}], [{"kind": "edit_page", "slug": "../x", "new_text": ""}],
                [{"kind": "set_frontmatter", "slug": "a", "key": "k", "value": "a\nb"}]):
        with pytest.raises(ProposalError) as e:
            validate_ops(bad)
        assert e.value.status == 400
    with pytest.raises(ProposalError):
        diff.build({"alpha": None}, edit(OLD))

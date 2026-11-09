"""Trust tiers, auto-apply with undo and coherence suggestions on a temp kb repo; no model, nothing leaves the machine."""
import json
import os
from unittest import mock

import pytest

from kb_distillery import llm
from kb_distillery.proposals import nightly, service, store, trust
from kb_distillery.proposals.model import ProposalError
from tests.ops.test_view import commits
from tests.proposals.conftest import read, write


def _edit(kb, slug, *pairs, **kw):
    text = read(kb, slug)
    for a, b in pairs:
        assert a in text, a
        text = text.replace(a, b)
    return [{"kind": "edit_page", "slug": slug, "new_text": text}]


def _create(kb, ops, **kw):
    return service.create("t", ops, producer={"kind": "chat"}, root=kb, **kw)


def klasses(p):
    return [h["klass"] for h in p["hunks"]]


# ---- classification

@pytest.mark.parametrize("pair,expected", [
    (("A [Beta](beta.md) b.", "A [Beta](gamma.md) b."), "links"),
    (("A Beta b.", "A [Beta](beta.md) b."), "links"),
    (("A [Beta](beta.md) b.", "A Beta b."), "links"),
    (("A [Beta](beta.md) b.", "A [the beta page](beta.md) b."), "claims"),   # the words the reader sees changed
    (("A [Beta](beta.md) b.", "A b."), "claims"),                            # a link deleted with its text
    (("The first claim is strong.", "The   first claim is strong!"), "format"),
    (("- one\n- two\n", "* one\n* two\n"), "format"),
    (("## Details\n", "### Details\n"), "format"),
    (("It grew 3.5% a year.", "It grew 35% a year."), "claims"),             # punctuation inside a number
    (("A fall of -5 points.", "A fall of 5 points."), "claims"),
    (("The first claim is strong.", "The first claim is strng."), "typos"),
    (("The result was reproducible.", "The result was reproducable."), "typos"),
    (("This is not true.", "This is now true."), "claims"),                  # short words flip meaning
    (("It was never shown.", "It was newer shown."), "claims"),              # negations are never typos
    (("The first claim is strong.", "The first claim may hold."), "claims"),
    (("It grew 12 percent.", "It grew 13 percent."), "claims"),
    (("## Details\n", "## Notes\n"), "structure"),
    (("", "## New\n"), "structure"),
    (("---\ntype: idea\n---\n", "---\ntype: topic\n---\n"), "structure"),
])
def test_classify_text(pair, expected):
    assert trust.classify_text(*pair) == expected


def test_classes_on_real_hunks(kb):
    p = _create(kb, _edit(kb, "alpha", ("is strong.", "is strng."), ("More text here.", "Other text.")))
    assert sorted(klasses(p)) == ["claims", "typos"]
    lk = _create(kb, _edit(kb, "alpha", ("[Beta](beta.md)", "[Beta](gamma.md)")))
    assert klasses(lk) == ["links"] and lk["hunks"][0]["kind"] == "structure"
    s = _create(kb, [{"kind": "set_frontmatter", "slug": "beta", "key": "description", "value": "New."}])
    assert klasses(s) == ["structure"]
    n = _create(kb, [{"kind": "create_page", "slug": "delta", "text": "---\ntype: idea\nlayer: concept\n---\n\n# Delta\n"}])
    assert klasses(n) == ["new_page"]
    t = _create(kb, [{"kind": "tombstone_page", "slug": "beta", "redirect_to": "gamma"}])
    assert klasses(t) == ["tombstone"]


def test_old_proposal_file_without_klass_still_loads(kb):
    p = _create(kb, _edit(kb, "alpha", ("is strong.", "is strng.")))
    raw = store.load(kb, p["id"])
    for rev in raw["revisions"]:
        for h in rev["hunks"]:
            h.pop("klass")
    store.save(kb, raw)
    assert klasses(service.get(p["id"], root=kb)) == ["typos"]


# ---- tiers from the kit default and kb.toml

def test_tiers_default_and_override(kb):
    t = service.trust_tiers(root=kb)
    assert t == {"auto_apply": ["links", "format", "typos"], "review": ["claims", "structure", "new_page"],
                 "explicit": ["tombstone", "merge", "split", "rename"], "source": "default"}
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[proposals]\nauto_apply = ["links"]\nreview = ["claims", "typos"]\n')
    t = service.trust_tiers(root=kb)
    assert t["auto_apply"] == ["links"] and t["review"] == ["claims", "typos"] and t["source"] == "kb.toml"
    assert t["explicit"] == ["tombstone", "merge", "split", "rename"]          # unset keys keep the default
    assert trust.tier_of("typos", t) == "review" and trust.tier_of("rename", t) == "explicit"


# ---- auto-apply

TYPO = ("is strong.", "is strng.")


def test_auto_apply_needs_the_flag_all_auto_classes_and_no_tier1_error(kb):
    # default: not requested, so only pre-marked
    p = _create(kb, _edit(kb, "alpha", TYPO))
    assert p["status"] == "open" and p["decisions"][p["hunks"][0]["id"]]["suggested"]
    # requested + all auto classes: applied at once
    q = _create(kb, _edit(kb, "beta", TYPO), auto=True)
    assert q["status"] == "applied" and q["applied"]["auto"] is True and "strng" in read(kb, "beta")
    # requested but a claim is mixed in: never applied, the boring hunk is pre-marked
    n = commits(kb)
    m = _create(kb, _edit(kb, "gamma", TYPO, ("More text here.", "Other text.")), auto=True)
    assert m["status"] == "open" and commits(kb) == n
    by = {h["klass"]: m["decisions"].get(h["id"]) for h in m["hunks"]}
    assert by["typos"]["decision"] == "accept" and by["typos"]["suggested"] and by["claims"] is None
    # requested, all auto classes, but tier 1 finds a broken link: stays open
    b = _create(kb, _edit(kb, "alpha", ("[Beta](beta.md)", "[Beta](nope.md)")), auto=True)
    assert b["status"] == "open" and b["check_counts"]["errors"] >= 1 and commits(kb) == n


def test_owner_decision_replaces_the_suggestion(kb):
    p = _create(kb, _edit(kb, "alpha", TYPO))
    hid = p["hunks"][0]["id"]
    got = service.decide(p["id"], [{"hunk_id": hid, "decision": "reject"}], root=kb)
    assert got["decisions"][hid]["decision"] == "reject" and not got["decisions"][hid].get("suggested")


def test_revise_with_auto(kb):
    p = _create(kb, _edit(kb, "alpha", ("is strong.", "may hold.")))
    q = service.revise(p["id"], _edit(kb, "alpha", TYPO), "smaller", root=kb, auto=True)
    assert q["status"] == "applied" and q["applied"]["auto"]


def test_kb_toml_changes_what_auto_applies(kb, tmp_path):
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[proposals]\nauto_apply = []\nreview = ["typos"]\n')
    p = _create(kb, _edit(kb, "alpha", TYPO), auto=True)
    assert p["status"] == "open" and p["decisions"] == {}


# ---- feed and undo

def test_feed_lists_applied_newest_first_and_undo_reverts(kb):
    a = _create(kb, _edit(kb, "alpha", TYPO), auto=True)
    before_feed = service.feed(root=kb)
    assert [i["id"] for i in before_feed] == [a["id"]]
    item = before_feed[0]
    assert item["pages"] == ["alpha"] and item["hunks"] == 1 and item["classes"] == ["typos"] and item["auto"]
    assert item["undoable"] is True and item["commit"] and item["applied_at"]
    assert service.feed(since="2999-01-01T00:00:00+00:00", root=kb) == []

    n = commits(kb)
    u = service.undo(a["id"], root=kb)
    assert u["status"] == "undone" and u["undone"]["at"] and commits(kb) == n + 1
    assert "is strong." in read(kb, "alpha") and "strng" not in read(kb, "alpha")
    again = service.feed(root=kb)[0]
    assert again["status"] == "undone" and again["undoable"] is False
    with pytest.raises(ProposalError) as e:
        service.undo(a["id"], root=kb)
    assert e.value.status == 409


def test_undo_refused_when_a_later_commit_touched_the_page(kb):
    a = _create(kb, _edit(kb, "alpha", TYPO), auto=True)
    b = _create(kb, _edit(kb, "alpha", ("More text here.", "Other text.")))
    service.decide(b["id"], [{"hunk_id": h["id"], "decision": "accept"} for h in b["hunks"]], root=kb)
    service.apply(b["id"], root=kb)                                       # a manual apply, later commit on alpha
    assert {f["id"]: f for f in service.feed(root=kb)}[a["id"]]["undoable"] is False   # by id: both applies may share a second
    n = commits(kb)
    with pytest.raises(ProposalError) as e:
        service.undo(a["id"], root=kb)
    assert e.value.status == 409 and "alpha" in str(e.value) and e.value.extra["pages"] == ["alpha"]
    assert commits(kb) == n and "strng" in read(kb, "alpha")
    # the manually applied one can be undone (nothing after it), the first only afterwards
    assert service.undo(b["id"], root=kb)["status"] == "undone"
    assert service.undo(a["id"], root=kb)["status"] == "undone"
    assert "is strong." in read(kb, "alpha")


def test_undo_open_proposal_is_409(kb):
    p = _create(kb, _edit(kb, "alpha", TYPO))
    with pytest.raises(ProposalError) as e:
        service.undo(p["id"], root=kb)
    assert e.value.status == 409


# ---- coherence suggestions

def _warnings(kb, rows):
    os.makedirs(os.path.join(kb, "meta"), exist_ok=True)
    with open(os.path.join(kb, "meta", "coherence-warnings.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tscore\tkind\tslugs\tsummary\tstatus\n" + "".join("\t".join(r) + "\n" for r in rows))


ROWS = [("w1", "60", "internal", "alpha,beta", "polarity clash on shared topic (4 tokens)", "open"),
        ("w2", "25", "cosmetic", "beta,gamma", "near-duplicate one-liner", "open"),
        ("w3", "80", "internal", "alpha", "raw re-queued", "open"),                # one page: not a pair
        ("w4", "60", "internal", "alpha,gamma", "polarity clash on shared topic (3 tokens)", "fixed"),
        ("w5", "20", "cosmetic", "alpha,beta", "asymmetric link to theme", "open")]  # not a conflict


def test_suggest_from_coherence_dedupes_and_dismiss_persists(kb):
    _warnings(kb, ROWS)
    made = nightly.suggest_from_coherence(kb)
    recs = {r["coherence_id"]: r for r in nightly.list_suggestions(kb)}
    assert len(made) == 2 and set(recs) == {"w1", "w2"}
    assert recs["w1"]["finding"] == "contradiction" and recs["w2"]["finding"] == "duplicate"
    assert recs["w1"]["slugs"] == ["alpha", "beta"] and "polarity" in recs["w1"]["detail"]
    assert recs["w1"]["draft"] == "ask the agent to draft a fix" and recs["w1"]["source"] == "coherence"
    assert nightly.suggest_from_coherence(kb) == []
    done = service.dismiss_suggestion(recs["w1"]["id"], root=kb)
    assert done["status"] == "dismissed"
    assert nightly.suggest_from_coherence(kb) == []                              # dismissed stays dismissed
    assert {r["coherence_id"]: r["status"] for r in service.suggestions(root=kb)} == {"w1": "dismissed", "w2": "open"}
    with pytest.raises(ProposalError) as e:
        service.dismiss_suggestion("deadbeef", root=kb)
    assert e.value.status == 404


def test_nightly_run_produces_both(kb):
    _warnings(kb, ROWS)
    with mock.patch.object(llm, "submit", return_value="msgbatch_9"):
        out = nightly.submit(kb)
    assert out["coherence_suggestions"] == 2 and out["batch"] == "msgbatch_9"
    assert json.load(open(os.path.join(kb, ".local", "proposals-nightly", "msgbatch_9.json")))["candidates"]

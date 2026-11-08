"""Tier-2 scoped semantic check on a temp kb; the model call is always a fake (kb_distillery.llm.ask)."""
import json
from unittest import mock

import pytest

from kb_distillery import llm
from kb_distillery.proposals import checks, checks_semantic, service
from tests.proposals.conftest import PAGE, read, write


def _create(kb, **kw):
    new = read(kb, "alpha").replace("is strong.", "is certainly true everywhere.")
    return service.create("soften", [{"kind": "edit_page", "slug": "alpha", "new_text": new}], **kw)


def _reply(findings):
    return llm.Result(id="r0", text="Here you go\n" + json.dumps({"findings": findings}), backend="subscription")


def test_scope_is_touched_plus_direct_neighbours_capped(kb):
    write(kb, "delta", PAGE.format(n="delta").replace("[Beta](beta.md)", "[Alpha](alpha.md)"))   # links in to alpha
    write(kb, "far", PAGE.format(n="far").replace("[Beta](beta.md)", "[Delta](delta.md)"))        # two hops away
    from kb_distillery.vault import pages as vp
    pages = vp.load_wiki_pages(kb)
    assert checks_semantic.neighbours(pages, "alpha") == ["beta", "delta"]
    scope, near = checks_semantic.select_scope(pages, ["alpha"], cap=10)
    assert scope == ["alpha", "beta", "delta"] and "far" not in scope and near == {"alpha": ["beta", "delta"]}
    scope, near = checks_semantic.select_scope(pages, ["alpha"], cap=2)
    assert scope == ["alpha", "beta"] and near == {"alpha": ["beta"]}


def test_one_call_per_touched_page_with_the_after_text_and_neighbour_excerpts(kb):
    p = _create(kb)
    hid = p["hunks"][0]["id"]
    with mock.patch.object(llm, "ask", return_value=_reply([])) as ask:
        out = service.semantic(p["id"], backend="api")
    assert ask.call_count == 1 and ask.call_args.kwargs["backend"] == "api"
    prompt = ask.call_args.args[0]
    assert "is certainly true everywhere." in prompt and hid in prompt and "[page: beta]" in prompt
    assert out["findings"] == [] and out["revision"] == 1


def test_findings_are_parsed_persisted_as_warnings_and_unknown_hunks_dropped(kb):
    p = _create(kb)
    hid = p["hunks"][0]["id"]
    rows = [{"code": "contradiction", "severity": "error", "message": "Beta says otherwise.", "hunk_id": hid,
             "evidence": "More text here.", "neighbour_slug": "beta"},
            {"code": "overclaim", "severity": "info", "message": "Too strong.", "hunk_id": hid, "evidence": "",
             "neighbour_slug": "nowhere"},
            {"code": "duplicate", "severity": "warning", "message": "Ghost.", "hunk_id": "deadbeef"},
            {"code": "weird", "severity": "warning", "message": "Bad code.", "hunk_id": hid}]
    with mock.patch.object(llm, "ask", return_value=_reply(rows)):
        out = service.semantic(p["id"])
    got = out["findings"]
    assert [f["code"] for f in got] == ["contradiction", "overclaim"]
    assert got[0]["severity"] == "warning" and got[0]["neighbour_slug"] == "beta" and got[0]["source"] == "tier2"
    assert "neighbour_slug" not in got[1]
    saved = service.get(p["id"])
    assert saved["checks"]["tier2"] == got and saved["check_counts"]["warnings"] == 1
    with mock.patch.object(llm, "ask", return_value=_reply([])):
        service.semantic(p["id"])
    assert service.get(p["id"])["checks"]["tier2"] == []                      # replaced, not appended


def test_tier2_never_blocks_apply(kb):
    p = _create(kb)
    row = {"code": "contradiction", "severity": "error", "message": "x", "hunk_id": p["hunks"][0]["id"]}
    with mock.patch.object(llm, "ask", return_value=_reply([row])):
        service.semantic(p["id"])
    got = service.get(p["id"])
    assert checks.blocking(got["checks"]["tier1"] + got["checks"]["tier2"], got["decisions"]) == []
    service.decide(p["id"], [{"hunk_id": got["hunks"][0]["id"], "decision": "accept"}])
    assert service.apply(p["id"])["commit"]


def test_coherence_warning_on_a_touched_page_passes_through_without_a_model_call(kb):
    import os
    os.makedirs(os.path.join(kb, "meta"), exist_ok=True)
    with open(os.path.join(kb, "meta", "coherence-warnings.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tscore\tkind\tslugs\tsummary\tstatus\n"
                "a1\t80\tinternal\talpha,beta\tAlpha and Beta disagree\topen\n"
                "a2\t80\tinternal\tbeta,gamma\tNot touched\topen\n"
                "a3\t80\tinternal\talpha,gamma\tAlready dismissed\tdismissed\n")
    p = _create(kb)
    with mock.patch.object(llm, "ask", return_value=_reply([])):
        out = service.semantic(p["id"])
    assert [(f["code"], f["slug"], f["neighbour_slug"]) for f in out["findings"]] == [("coherence", "alpha", "beta")]


def test_semantic_flag_on_create_runs_tier2_and_a_failed_call_leaves_an_info_finding(kb):
    with mock.patch.object(llm, "ask", return_value=_reply([])) as ask:
        p = _create(kb, semantic=True)
    assert ask.call_count == 1 and p["checks"]["tier2"] == []
    with mock.patch.object(llm, "ask", return_value=llm.Result(id="r0", error="rate limited")):
        p = _create(kb, semantic=True)
    assert [f["code"] for f in p["checks"]["tier2"]] == ["semantic-unavailable"] and p["checks"]["tier2"][0]["severity"] == "info"


def test_no_semantic_call_unless_asked(kb):
    with mock.patch.object(llm, "ask", side_effect=AssertionError("a model was called")):
        _create(kb)

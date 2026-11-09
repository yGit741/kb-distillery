"""Tier-3 nightly suggestions on a temp kb; llm.submit / collect / ask are fakes, nothing leaves the machine."""
import json
import os
from unittest import mock

import pytest

from kb_distillery import llm
from kb_distillery.proposals import __main__ as cli
from kb_distillery.proposals import nightly, service, store
from tests.proposals.conftest import PAGE, read, write


def _seed(kb):
    os.makedirs(os.path.join(kb, "meta"), exist_ok=True)
    with open(os.path.join(kb, "meta", "coherence-warnings.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tscore\tkind\tslugs\tsummary\tstatus\nw1\t70\tinternal\talpha,beta\tThey disagree\topen\n"
                "w2\t70\tinternal\tbeta,gamma\tDone\tfixed\n")
    write(kb, "huge", PAGE.format(n="huge").replace("More text here.", "Filler sentence. " * 400))
    write(kb, "alpha-two", PAGE.format(n="alpha").replace("# alpha", "# alpha"))   # same title as alpha


def test_scan_finds_coherence_overlap_and_oversized_pages(kb):
    _seed(kb)
    kinds = {(c["kind"], tuple(c["slugs"])) for c in nightly.scan(kb)}
    assert ("coherence", ("alpha", "beta")) in kinds and ("coherence", ("beta", "gamma")) not in kinds
    assert ("oversized", ("huge",)) in kinds
    assert ("overlap", ("alpha", "alpha-two")) in kinds


def test_dry_run_prints_candidates_and_calls_nothing(kb, capsys):
    _seed(kb)
    with mock.patch.object(llm, "submit", side_effect=AssertionError("called")), \
            mock.patch.object(llm, "ask", side_effect=AssertionError("called")):
        assert cli.main(["nightly", "--kb", kb, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "request(s) would be sent; nothing was called" in out and "oversized" in out


def test_submit_sends_one_batch_and_collect_writes_a_lint_proposal_and_a_suggestion(kb):
    _seed(kb)
    cands = nightly.scan(kb)
    with mock.patch.object(llm, "submit", return_value="msgbatch_1") as sub:
        out = nightly.submit(kb)
    assert sub.call_count == 1 and len(sub.call_args.args[0]) == len(cands) == out["candidates"]
    assert os.path.isfile(os.path.join(kb, ".local", "proposals-nightly", "msgbatch_1.json"))

    edit = read(kb, "alpha").replace("is strong.", "may hold.")
    results = []
    for c in cands:
        if c["kind"] == "coherence":
            text = json.dumps({"summary": "Soften alpha.", "edit": {"slug": "alpha", "new_text": edit}})
        else:
            text = json.dumps({"summary": f"Look at {c['kind']}.", "edit": None})
        results.append(llm.Result(id=c["id"], text=text, backend="batch"))
    results.append(llm.Result(id="zzz", error="errored"))
    with mock.patch.object(llm, "collect", return_value=results):
        got = nightly.collect(kb, "msgbatch_1")
    assert len(got["proposals"]) == 1 and len(got["suggestions"]) == len(cands) - 1
    p = service.get(got["proposals"][0], root=kb)
    assert p["status"] == "open" and p["producer"]["kind"] == "lint" and p["hunks"]
    assert read(kb, "alpha") != edit                                            # nothing was applied
    assert {s["finding"] for s in nightly.list_suggestions(kb)} == {"overlap", "oversized"}
    assert not os.path.isfile(os.path.join(kb, ".local", "proposals-nightly", "msgbatch_1.json"))


def test_an_edit_for_a_page_outside_the_finding_becomes_a_suggestion(kb):
    _seed(kb)
    c = [x for x in nightly.scan(kb) if x["kind"] == "oversized"]
    r = llm.Result(id=c[0]["id"], text=json.dumps({"summary": "s", "edit": {"slug": "gamma", "new_text": "x"}}))
    got = nightly.write(kb, c, [r])
    assert got["proposals"] == [] and len(got["suggestions"]) == 1 and store.all_ids(kb) == []


def test_a_second_run_does_not_repeat_open_findings_and_a_pending_batch_is_kept(kb):
    _seed(kb)
    cands = nightly.scan(kb)
    ok = [llm.Result(id=c["id"], text=json.dumps({"summary": "s", "edit": None})) for c in cands]
    first = nightly.write(kb, cands, ok)
    again = nightly.write(kb, cands, ok)
    assert len(first["suggestions"]) == len(cands) and again["suggestions"] == []
    with mock.patch.object(llm, "submit", return_value="msgbatch_2"):
        nightly.submit(kb)
    pending = [llm.Result(id=c["id"], error="batch still in_progress") for c in cands]
    with mock.patch.object(llm, "collect", return_value=pending):
        assert nightly.collect(kb, "msgbatch_2")["failed"] == len(cands)
    assert os.path.isfile(os.path.join(kb, ".local", "proposals-nightly", "msgbatch_2.json"))

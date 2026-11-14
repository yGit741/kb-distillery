"""Parser + reader + judge -> a marked transcript. The engine and the model are fakes: no MinerU, no LLM, no network."""
import json
import os

import pytest

from kb_distillery import llm
from kb_distillery.parse import cli, compare, judge, reader, store, transcribe

from . import pdfs

SHA = "ab" * 20
PARSER = {1: "Intro text.\n\nWe have $x _ { i } ^ { 2 } + y$ and $\\alpha \\leq \\beta _ { 1 }$ here.\n\n$$\na = b - c \\tag {1.1}\n$$\n\nEnd of page.\n",
          2: "Second page with $f ( w )$ only.\n"}
READER = {1: "Intro text.\n\nWe have $x_i^2 + y$ and $\\alpha \\le \\beta$ here.\n\n$$a = b + c \\tag{1.1}$$\n\nEnd of \\unsure{page}.\n",
          2: "Second page with $f(w)$ only.\n"}


class FakeEngine:
    name = "fake"

    def __init__(self, pages=PARSER):
        self.pages = pages

    def parse(self, pdf, pages, workdir):
        return {p: {"page_idx": p - 1, "text": self.pages[p]} for p in pages if p in self.pages}

    def markdown(self, rec):
        return rec["text"]

    def figures(self, rec, width, height):
        return []

    def boxes(self, rec):
        out, pos = [], 0
        for n, chunk in enumerate(rec["text"].strip().split("\n\n")):
            out.append((pos, pos + len(chunk), (0.1, 0.1 + 0.1 * n, 0.9, 0.18 + 0.1 * n)))
            pos += len(chunk) + 2
        return out


class FakeLLM:
    """Answers reader requests from READER and judge requests from `verdicts` {page: [(verdict, sure, fix)]}."""

    def __init__(self, verdicts=None, reader_pages=READER, findings=None):
        self.verdicts, self.reader_pages, self.calls = verdicts or {}, reader_pages, []
        self.findings = findings or {}                                   # {page: [finding dicts]} or {page: None}

    def __call__(self, requests, backend=None, **kw):
        out = []
        for r in requests:
            self.calls.append(r.id)
            assert all(os.path.exists(p) for p in r.images), "the page images are rendered before the call"
            page = int(r.id[1:])
            if r.id.startswith("p"):
                text = self.reader_pages.get(page)
                out.append(llm.Result(r.id, text="<<<PAGE\n%sPAGE>>>" % text if text else "", error="" if text else "no reply",
                                      usd=0.03, stop_reason="end_turn"))
            elif r.id.startswith("a"):
                f = self.findings.get(page, [])
                out.append(llm.Result(r.id, text="no json here" if f is None else json.dumps({"findings": f}), usd=0.02,
                                      stop_reason="end_turn"))
            else:
                rows = [{"id": n + 1, "verdict": v, "sure": s, "fix": f} for n, (v, s, f) in enumerate(self.verdicts.get(page, []))]
                out.append(llm.Result(r.id, text=json.dumps({"items": rows}), usd=0.01, stop_reason="end_turn"))
        return out


@pytest.fixture
def pdf(tmp_path):
    path = str(tmp_path / "doc.pdf")
    pdfs.build(path)
    return path


def run(pdf, tmp_path, monkeypatch, fake, pages=(1, 2), engine=None, backend="api"):
    monkeypatch.setattr(llm, "run", fake)
    return transcribe.transcribe(pdf, list(pages), str(tmp_path / "work"), str(tmp_path / "store"), SHA,
                                 engine=engine if engine is not None else FakeEngine(), backend=backend,
                                 page_count=3, log=lambda *_: None)


def test_items_are_whole_formulas_and_agreement_asks_nothing():
    al = compare.align(PARSER[1], READER[1])
    its = judge.items(al)
    assert [i.transcript for i in its] == ["$\\alpha \\le \\beta$", "$$a = b + c \\tag{1.1}$$"]
    assert its[0].other == "$\\alpha \\leq \\beta _ { 1 }$" and "<<HERE>>" in its[0].where
    assert judge.items(compare.align(PARSER[2], READER[2])) == []


def test_bold_the_parser_dropped_is_not_asked_about():
    assert judge.items(compare.align("so $w$ holds", "so $\\mathbf{w}$ holds")) == []
    assert len(judge.items(compare.align("so $\\mathbf{w}$ holds", "so $w$ holds"))) == 1


def test_sure_transcript_stands_unmarked_and_a_sure_fix_is_applied_with_one_mark(pdf, tmp_path, monkeypatch):
    fake = FakeLLM({1: [("transcript", True, ""), ("other", True, "$$a = b - c \\tag{1.1}$$")]})
    res = run(pdf, tmp_path, monkeypatch, fake)
    assert res["pages"] == {1: "marked", 2: "verified"} and res["failed"] == {}
    rec = store.read_page(str(tmp_path / "store"), SHA, 1)
    md = rec["markdown"]
    assert "$\\alpha \\le \\beta$ here" in md                                # kept, no mark
    assert "$$a = b - c \\tag{1.1}$$\n\n[!](mark:%s/p0001/1)" % SHA[:12] in md   # fixed, marked after the block
    assert "\\unsure" not in md and "End of page [!](mark:%s/p0001/2)" % SHA[:12] in md
    m1, m2 = rec["marks"]
    assert m1["level"] == "!" and m1["was"] == "$$a = b + c \\tag{1.1}$$" and "a = b - c" in m1["text"]
    assert m1["other"].startswith("$$") and m1["crop"] == "p0001-1.png"
    assert os.path.exists(os.path.join(str(tmp_path / "store"), SHA, "crops", "p0001-1.png"))
    assert m2["reason"].startswith("the reader marked")
    assert res["marks"] == {"!": 2, "!!": 0}
    assert res["usd"] == pytest.approx(0.03 * 2 + 0.01 + 0.02 * 2)           # page 2 agreed: no judge call for it
    assert fake.calls == ["p0001", "p0002", "j0001", "a0001", "a0002"]


def test_an_unsure_or_missing_verdict_is_a_double_mark(pdf, tmp_path, monkeypatch):
    fake = FakeLLM({1: [("transcript", False, ""), ("neither", False, "$$a = b \\pm c \\tag{1.1}$$")]})
    run(pdf, tmp_path, monkeypatch, fake, pages=(1,))
    rec = store.read_page(str(tmp_path / "store"), SHA, 1)
    assert [m["level"] for m in rec["marks"]][:2] == ["!", "!!"] and "b \\pm c" in rec["markdown"]
    fake = FakeLLM({})                                                       # the judge answers nothing
    monkeypatch.setattr(llm, "run", fake)
    res = transcribe.transcribe(pdf, [1], str(tmp_path / "w2"), str(tmp_path / "s2"), SHA, engine=FakeEngine(),
                                backend="api", log=lambda *_: None)
    assert res["marks"]["!!"] == 2
    assert "$$a = b + c \\tag{1.1}$$\n\n[!!](mark:" in store.read_page(str(tmp_path / "s2"), SHA, 1)["markdown"]


OK = {1: [("transcript", True, ""), ("transcript", True, "")]}


def test_the_auditor_fixes_and_marks(pdf, tmp_path, monkeypatch):
    f = {1: [{"snippet": "$x_i^2 + y$", "fix": "$x_i^2 - y$", "page_says": "a minus sign", "severity": "serious", "sure": True},
             {"snippet": "Intro text.", "fix": "Intro text. A lost line.", "page_says": "one more line", "severity": "serious", "sure": False},
             {"snippet": "nowhere in the page", "fix": "x", "page_says": "something", "severity": "minor", "sure": True}],
         2: None}
    res = run(pdf, tmp_path, monkeypatch, FakeLLM(OK, findings=f))
    rec = store.read_page(str(tmp_path / "store"), SHA, 1)
    md = rec["markdown"]
    by = {m["id"]: m for m in rec["marks"]}
    assert md.startswith("[!!](mark:%s/p0001/1)\n\nIntro text. A lost line. [!!](mark:%s/p0001/2)" % (SHA[:12], SHA[:12]))
    assert "$x_i^2 - y$ [!](mark:%s/p0001/3)" % SHA[:12] in md
    assert "nowhere in the page" in by[1]["reason"] and by[1]["text"] == ""
    assert by[3]["was"] == "$x_i^2 + y$" and by[3]["text"] == "$x_i^2 - y$" and "minus sign" in by[3]["reason"]
    assert by[3]["crop"] == "p0001-3.png"                                   # placed through the alignment with the parser
    assert res["marks"] == {"!": 3, "!!": 2}                                 # + the reader's own \\unsure, + page 2 unaudited
    two = store.read_page(str(tmp_path / "store"), SHA, 2)
    assert two["status"] == "marked" and "no readable answer" in two["marks"][0]["reason"]


def test_the_auditor_can_be_switched_off(pdf, tmp_path, monkeypatch):
    fake = FakeLLM(OK)
    monkeypatch.setattr(llm, "run", fake)
    transcribe.transcribe(pdf, [1, 2], str(tmp_path / "w"), str(tmp_path / "s"), SHA, engine=FakeEngine(), backend="api",
                          audit_model=None, log=lambda *_: None)
    assert not [c for c in fake.calls if c.startswith("a")]


def test_edits_move_later_offsets():
    text, remap = transcribe.apply_edits("0123456789", [(2, 4, "ab-cd"), (7, 8, "")])
    assert text == "01ab-cd456" + "89" and [remap(p) for p in (1, 2, 3, 4, 6, 8, 10)] == [1, 2, 7, 7, 9, 10, 12]


def test_one_reading_only_marks_the_whole_page(pdf, tmp_path, monkeypatch):
    res = run(pdf, tmp_path, monkeypatch, FakeLLM(), engine=FakeEngine({1: PARSER[1]}))        # no parser page 2
    rec = store.read_page(str(tmp_path / "store"), SHA, 2)
    assert rec["markdown"].startswith("[!](mark:%s/p0002/0)" % SHA[:12]) and rec["marks"][0]["id"] == 0
    assert res["pages"][2] == "marked"
    res = run(pdf, tmp_path / "b", monkeypatch, FakeLLM(reader_pages={1: READER[1]}))          # the reader fails on page 2
    rec = store.read_page(str(tmp_path / "b" / "store"), SHA, 2)
    assert rec["markdown"].startswith("[!](mark:") and "checked by the auditor" in rec["marks"][0]["reason"] and 2 in res["failed"]
    assert "Second page with $f ( w )$ only." in rec["markdown"]                              # the parser's page stands in
    f = {2: [{"snippet": "$f ( w )$", "fix": "$f ( \\mathbf{w} )$", "page_says": "bold w", "severity": "minor", "sure": True}]}
    run(pdf, tmp_path / "c", monkeypatch, FakeLLM(reader_pages={1: READER[1]}, findings=f))
    rec = store.read_page(str(tmp_path / "c" / "store"), SHA, 2)
    assert "$f ( \\mathbf{w} )$ [!](mark:" in rec["markdown"] and len(rec["marks"]) == 2            # audited and fixed
    run(pdf, tmp_path / "d", monkeypatch, FakeLLM(reader_pages={1: READER[1]}, findings={2: None}))
    rec = store.read_page(str(tmp_path / "d" / "store"), SHA, 2)
    assert rec["markdown"].startswith("[!!](mark:") and len(rec["marks"]) == 1 and "reader:none" in rec["engine"]   # not audited


def test_resume_reads_and_judges_nothing_twice(pdf, tmp_path, monkeypatch):
    v = {1: [("transcript", True, ""), ("transcript", True, "")]}
    run(pdf, tmp_path, monkeypatch, FakeLLM(v))
    again = FakeLLM(v)
    res = run(pdf, tmp_path, monkeypatch, again)
    assert again.calls == [] and res["usd"] == 0.0 and res["pages"][1] == "marked"         # the \unsure mark remains


def test_subscription_runs_report_no_cost(pdf, tmp_path, monkeypatch):
    res = run(pdf, tmp_path, monkeypatch, FakeLLM({1: [("transcript", True, ""), ("transcript", True, "")]}), backend="subscription")
    assert res["usd"] == 0.0


def test_transcript_and_marks_read_back(pdf, tmp_path, monkeypatch):
    run(pdf, tmp_path, monkeypatch, FakeLLM({1: [("transcript", True, ""), ("transcript", True, "")]}))
    root = str(tmp_path / "store")
    text = store.transcript(root, SHA, [1, 2])
    assert text.index("Intro text") < text.index("Second page") and transcribe.MARK_LINK.search(text)
    assert store.transcript(root, SHA, [1, 3]) is None
    assert [(m["page"], m["id"]) for m in store.marks(root, SHA)] == [(1, 1)]
    assert store.read_manifest(root, SHA)["status"] == {"verified": 1, "repaired": 0, "marked": 1, "needs-human": 0}


def test_reader_drops_a_code_fence_and_refuses_a_cut_reply(pdf, tmp_path, monkeypatch):
    assert reader.clean("<<<PAGE\n```markdown\n# T\n\ntext\n```\nPAGE>>>") == "# T\n\ntext\n"
    assert reader.clean("I will skip the plan.\n\n<<<PAGE\n# T\nPAGE>>>\nDone.") == "# T\n"
    assert reader.clean("I read both images, so here it is:\n# T") is None
    assert reader.clean("<<<PAGE\r\nhi\r\nPAGE>>>\r\n") == "hi\n"
    assert reader.clean("<<<PAGE\nsee the PAGE>>> marker\nmore text\nPAGE>>>") == "see the PAGE>>> marker\nmore text\n"
    assert reader.clean("<<<PAGE\nPAGE>>>") == "\n"                                   # a blank page is a page

    def chatty(requests, backend=None, **kw):
        return [llm.Result(r.id, text="The task is a single transcription.\n\nSome page text", stop_reason="end_turn") for r in requests]
    monkeypatch.setattr(llm, "run", chatty)
    res = reader.read(pdf, [2], str(tmp_path / "w0"), backend="api", log=lambda *_: None)
    assert res["read"] == [] and "markers" in res["failed"][2]

    def cut(requests, backend=None, **kw):
        return [llm.Result(r.id, text="half a page", stop_reason="max_tokens") for r in requests]
    monkeypatch.setattr(llm, "run", cut)
    res = reader.read(pdf, [1], str(tmp_path / "w"), backend="api", log=lambda *_: None)
    assert res["read"] == [] and "cut" in res["failed"][1]


def test_cli_estimate_and_cap(pdf, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(llm, "run", FakeLLM())
    args = ["transcribe", pdf, "--pages", "1-3", "--store", str(tmp_path / "s"), "--work", str(tmp_path / "w"),
            "--engine", "none", "--backend", "api"]
    with pytest.raises(SystemExit, match="above --max-usd"):
        cli.main(args + ["--max-usd", "0.01"])
    assert cli.main(args + ["--dry-run"]) == 0 and not os.path.exists(str(tmp_path / "s"))
    assert "estimated cost $" in capsys.readouterr().err


def test_a_garbled_judge_reply_is_no_verdict_and_is_not_cached(pdf, tmp_path, monkeypatch):
    its = judge.items(compare.align(PARSER[1], READER[1]))
    assert not any(v.verdict for v in judge.parse_reply('{"items":[{"id":[1],"verdict":"other"},{"id":true,"verdict":"other"}]}', its).values())

    def cut(requests, backend=None, **kw):
        return [llm.Result(r.id, text='{"items":[{"id":1,"verdict":"transcript","sure":true}', stop_reason="max_tokens") for r in requests]
    monkeypatch.setattr(llm, "run", cut)
    res, _ = judge.ask({1: its}, {1: ()}, str(tmp_path), backend="api", log=lambda *_: None)
    assert not any(v.verdict for v in res[1].values()) and not os.path.exists(judge.cache_path(str(tmp_path), 1))


def test_cached_answers_are_for_one_model(pdf, tmp_path, monkeypatch):
    fake = FakeLLM(OK)
    run(pdf, tmp_path, monkeypatch, fake)
    again = FakeLLM(OK)
    monkeypatch.setattr(llm, "run", again)
    transcribe.transcribe(pdf, [1, 2], str(tmp_path / "work"), str(tmp_path / "store"), SHA, engine=FakeEngine(),
                          backend="api", judge_model="opus", audit_model="sonnet", log=lambda *_: None)
    assert again.calls == ["j0001", "a0001", "a0002"]


def test_a_fix_that_would_break_a_formula_is_not_applied(pdf, tmp_path, monkeypatch):
    f = {2: [{"snippet": "f(w)$ only", "fix": "g(w) only", "page_says": "g", "severity": "serious", "sure": True}]}
    run(pdf, tmp_path, monkeypatch, FakeLLM(OK, findings=f))
    rec = store.read_page(str(tmp_path / "store"), SHA, 2)
    assert "$f(w)$ only [!!](mark:" in rec["markdown"] and rec["marks"][0]["was"] == ""
    text, marks = transcribe.audited("a $x$ b", [], [{"snippet": "x$ b", "fix": "y", "page_says": "y", "severity": "serious", "sure": True}])
    assert text == "a $x$ b" and marks[0]["level"] == "!!"


def test_a_mark_never_lands_inside_a_word(pdf, tmp_path, monkeypatch):
    f = {2: [{"snippet": "Second pa", "fix": "Sekond pa", "page_says": "Sekond", "severity": "minor", "sure": True}]}
    run(pdf, tmp_path, monkeypatch, FakeLLM(OK, findings=f))
    assert store.read_page(str(tmp_path / "store"), SHA, 2)["markdown"].startswith("Sekond page [!](mark:")


def test_a_wrapper_cut_by_a_judged_place_leaves_no_stray_command():
    md = "so \\unsure{$a$ and more words} then $b$ ok"
    it = judge.Item(1, (md.index("$a$"), md.index("$a$") + 3), (0, 3), "$a$", "$c$")
    text, marks = transcribe.judged(md, [it], {1: judge.Verdict(1, "other", True, "$c$")})
    assert "\\unsure" not in text and text.startswith("so $c$ and more words then") and len(marks) == 1


def test_a_ceiling_skips_the_stage_that_would_cross_it(pdf, tmp_path, monkeypatch):
    fake = FakeLLM(OK)
    monkeypatch.setattr(llm, "run", fake)
    res = transcribe.transcribe(pdf, [1, 2], str(tmp_path / "w"), str(tmp_path / "s"), SHA, engine=FakeEngine(),
                                backend="api", max_usd=0.065, log=lambda *_: None)
    assert res["skipped"] == ["judge", "auditor"] and fake.calls == ["p0001", "p0002"]
    assert res["marks"]["!!"] == 2                                           # unjudged differences


def test_deep_or_broken_latex_never_crashes():
    for src in ("{" * 3000 + "x" + "}" * 3000, "x_", "x^", "\\frac{", "\\begin", "a\\", "\\sqrt[", "}}}{{{", ""):
        compare.math_tokens(src)
    assert compare.dollars("a $x$ \\$5") == 2


def test_cli_target_by_pages_or_by_chapter(pdf, tmp_path, monkeypatch):
    import argparse
    from kb_distillery.vault import books
    kb = tmp_path / "kb"
    (kb / "raw").mkdir(parents=True)
    os.rename(pdf, str(kb / "raw" / "book.pdf"))
    monkeypatch.setattr(books, "chapters", lambda root, raw: [
        books.Chapter("front", "Front", 1, 1, "skip"), books.Chapter("ch1", "One", 2, 2, "—"), books.Chapter("ch2", "Two", 3, 3, "—")])

    def ns(**kw):
        return argparse.Namespace(**{"pdf": "raw/book.pdf", "pages": "", "chapter": "", "kb": str(kb), "store": "", **kw})
    path, pages, st = cli._target(ns(chapter="1-2"))
    assert path == str(kb / "raw" / "book.pdf") and pages == "2-2,3-3" and st == str(kb / "meta" / "parsed")
    assert cli._target(ns(chapter="all"))[1] == "2-2,3-3"                                  # skip rows are left out
    assert cli._target(ns(pages="1-2", store=str(tmp_path / "s")))[2] == str(tmp_path / "s")
    for bad in (ns(), ns(pages="1", chapter="1"), ns(chapter="1", kb="", pdf=str(kb / "raw" / "book.pdf"), store="x"),
                ns(chapter="9"), ns(pdf="raw/none.pdf", pages="1")):
        with pytest.raises(SystemExit):
            cli._target(bad)


def test_coverage_counts_stored_pages_and_marks(tmp_path):
    root = str(tmp_path)
    store.write_transcript_page(root, SHA, 2, "x", [{"id": 1, "level": "!"}, {"id": 2, "level": "!!"}])
    store.write_transcript_page(root, SHA, 3, "y", [])
    assert store.coverage(root, SHA, 2, 5) == {"pages": 2, "of": 4, "!": 1, "!!": 1}


def test_a_fix_about_another_place_is_not_applied():
    assert transcribe.sane_fix("$\\hat{p} \\in \\mathbb{R}^{\\hat{d}}$", "$\\hat{p} \\in \\mathbb{R}^{d}$")
    assert not transcribe.sane_fix("$\\hat{p} \\in \\mathbb{R}^{\\hat{d}}$", "$\\hat{p}_i = \\hat{C}_i \\hat{B}_i$")
    assert transcribe.sane_fix("Intro text.", "Intro text. A lost line.")                 # additions keep everything
    it = judge.Item(1, (0, 12), (0, 12), "$a + b c d$", "$a - b c d$")
    level, fix, _ = transcribe.decide(it, judge.Verdict(1, "neither", True, "$x_i = y_i z_i w$"))
    assert level == "!!" and fix is None
    text, marks = transcribe.audited("so $a + b c d$ holds", [], [{"snippet": "$a + b c d$", "fix": "$q = r s t$", "page_says": "q",
                                                                   "severity": "serious", "sure": True}])
    assert text == "so $a + b c d$ holds" and marks[0]["level"] == "!!"
    assert transcribe.sane_fix("$a$", "$c$")                                              # one symbol: nothing to compare


def test_a_failed_request_is_tried_once_more(pdf, tmp_path, monkeypatch):
    state = {"n": 0, "backends": []}
    good = FakeLLM(OK)

    def flaky(requests, backend=None, **kw):
        state["n"] += 1
        state["backends"].append(backend)
        if state["n"] in (1, 3, 5):                                  # first reader, first judge, first audit call fail
            return [llm.Result(r.id, text="", error="blocked", stop_reason="") if r.id.startswith("p")
                    else llm.Result(r.id, text="not json", stop_reason="end_turn") for r in requests]
        return good(requests, backend=backend, **kw)
    monkeypatch.setattr(llm, "run", flaky)
    res = transcribe.transcribe(pdf, [1], str(tmp_path / "w"), str(tmp_path / "s"), SHA, engine=FakeEngine(), backend="batch",
                                retry_backend="subscription", log=lambda *_: None)
    assert res["failed"] == {} and res["pages"][1] == "marked" and res["marks"] == {"!": 1, "!!": 0}
    assert state["backends"] == ["batch", "subscription"] * 3


def test_retries_respect_the_ceiling_and_force(pdf, tmp_path, monkeypatch):
    calls = []

    def failing(requests, backend=None, **kw):
        calls.append((requests[0].id[0], backend))
        return [llm.Result(r.id, text="", error="blocked") for r in requests]
    monkeypatch.setattr(llm, "run", failing)
    res = transcribe.transcribe(pdf, [1], str(tmp_path / "w"), str(tmp_path / "s"), SHA, engine=FakeEngine(), backend="subscription",
                                retry_backend="api", max_usd=0.01, log=lambda *_: None)
    assert ("p", "api") not in calls and "reader retry" in res["skipped"]                 # the paid retry would cross $0.01
    assert calls[0] == ("p", "subscription") and ("a", "subscription") in calls          # the parser's page is audited, free
    assert "auditor" not in res["skipped"]
    stale = tmp_path / "w2" / "reader"
    stale.mkdir(parents=True)
    (stale / "p0001.md").write_text("an old page\n")
    res = transcribe.transcribe(pdf, [1], str(tmp_path / "w2"), str(tmp_path / "s2"), SHA, engine=FakeEngine({}), backend="api",
                                force=True, log=lambda *_: None)
    assert 1 in res["failed"] and "old page" not in json.dumps(res)                      # the stale file is not passed off as read

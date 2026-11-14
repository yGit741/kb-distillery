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

    def __init__(self, verdicts=None, reader_pages=READER):
        self.verdicts, self.reader_pages, self.calls = verdicts or {}, reader_pages, []

    def __call__(self, requests, backend=None, **kw):
        out = []
        for r in requests:
            self.calls.append(r.id)
            assert all(os.path.exists(p) for p in r.images), "the page images are rendered before the call"
            page = int(r.id[1:])
            if r.id.startswith("p"):
                text = self.reader_pages.get(page)
                out.append(llm.Result(r.id, text=text or "", error="" if text else "no reply", usd=0.03, stop_reason="end_turn"))
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
    assert res["usd"] == pytest.approx(0.03 * 2 + 0.01)                      # page 2 agreed: no judge call for it
    assert fake.calls == ["p0001", "p0002", "j0001"]


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


def test_one_reading_only_marks_the_whole_page(pdf, tmp_path, monkeypatch):
    res = run(pdf, tmp_path, monkeypatch, FakeLLM(), engine=FakeEngine({1: PARSER[1]}))        # no parser page 2
    rec = store.read_page(str(tmp_path / "store"), SHA, 2)
    assert rec["markdown"].startswith("[!](mark:%s/p0002/0)" % SHA[:12]) and rec["marks"][0]["id"] == 0
    assert res["pages"][2] == "marked"
    res = run(pdf, tmp_path / "b", monkeypatch, FakeLLM(reader_pages={1: READER[1]}))          # the reader fails on page 2
    rec = store.read_page(str(tmp_path / "b" / "store"), SHA, 2)
    assert rec["markdown"].startswith("[!!](mark:") and 2 in res["failed"]


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
    assert reader.clean("```markdown\n# T\n\ntext\n```") == "# T\n\ntext\n"

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

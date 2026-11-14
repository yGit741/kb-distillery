"""Figures of a transcribed page: paired with the parser's regions, cut, linked, described, counted. Fake model only."""
import json
import os

from kb_distillery import llm
from kb_distillery.parse import complete, figures, store, transcribe

from . import pdfs
from .test_transcribe import SHA, FakeEngine, FakeLLM

S12 = SHA[:12]
MD = ("See Figure 3.1.\n\n![](figure)\n\n**Figure 3.1.** A decision tree\n\nMore text.\n\n![](figure)\n"
      "Figure 3.2: Second one.\n")


def test_place_pairs_placeholders_with_regions_in_order_and_reads_captions():
    md, figs = figures.place(MD, [(0.3, 0.2, 0.7, 0.4), (0.78, 0.33, 0.79, 0.34), (0.2, 0.5, 0.8, 0.7)], SHA, 73)
    assert "![Figure 3.1](figure:%s/p0073/1)" % S12 in md and "![Figure 3.2](figure:%s/p0073/2)" % S12 in md
    assert "![](figure)" not in md and "**Figure 3.1.** A decision tree" in md          # the caption stays as text
    assert [f["box"] for f in figs] == [[0.3, 0.2, 0.7, 0.4], [0.2, 0.5, 0.8, 0.7]]      # a glyph-sized region is no figure
    assert figs[0]["caption"] == "**Figure 3.1.** A decision tree" and not any(f["problem"] for f in figs)


def test_a_placeholder_without_region_and_a_region_without_placeholder_both_carry_a_problem():
    md, figs = figures.place("Text.\n\n![](figure)\n", [], SHA, 5)
    assert figs[0]["box"] is None and "whole page" in figs[0]["problem"]
    md, figs = figures.place("Only text.\n", [(0.2, 0.2, 0.8, 0.6)], SHA, 5)
    assert md.rstrip().endswith("![Figure](figure:%s/p0005/1)" % S12) and "did not place" in figs[0]["problem"]


def test_with_descriptions_follows_each_link_with_what_it_shows():
    md, figs = figures.place(MD, [(0.3, 0.2, 0.7, 0.4), (0.2, 0.5, 0.8, 0.7)], SHA, 73)
    figs[0]["description"] = "A binary tree\nwith root $x_1$."
    out = figures.with_descriptions(md, {(S12, 73, f["id"]): f for f in figs})
    assert "(figure:%s/p0073/1)\n\n*[What the figure shows, described from its image: A binary tree with root $x_1$.]*" % S12 in out
    assert out.count("What the figure shows") == 1


def test_reply_needs_its_markers():
    assert figures.reply_text("The machine is busy.\n<<<FIGURE\nA plot of\n$y=x$.\nFIGURE>>>\n") == "A plot of $y=x$."
    assert figures.reply_text("A plot without markers.") is None


class FigLLM(FakeLLM):
    """FakeLLM plus figure descriptions (ids `f…`); `bad` answers without markers."""

    def __init__(self, bad=False, **kw):
        super().__init__(**kw)
        self.bad = bad

    def __call__(self, requests, backend=None, **kw):
        figs = [r for r in requests if r.id.startswith("f")]
        rest = [r for r in requests if not r.id.startswith("f")]
        out = {r.id: x for r, x in zip(rest, super().__call__(rest, backend)) } if rest else {}
        for r in figs:
            self.calls.append(r.id)
            assert all(os.path.exists(p) for p in r.images)
            text = "no markers" if self.bad else "<<<FIGURE\nA tree with root $x_1$.\nFIGURE>>>"
            out[r.id] = llm.Result(r.id, text=text, usd=0.02, stop_reason="end_turn")
        return [out[r.id] for r in requests]


class FigEngine(FakeEngine):
    def figures(self, rec, width, height):
        return [(0.2, 0.3, 0.8, 0.6)] if rec["page_idx"] == 0 else []


def _run(tmp_path, monkeypatch, fake, **kw):
    path = str(tmp_path / "doc.pdf")
    pdfs.build(path)
    monkeypatch.setattr(llm, "run", fake)
    reader_pages = {1: "Intro text.\n\n![](figure)\n\n**Figure 1.1.** A tree\n", 2: "Second page with $f(w)$ only.\n"}
    fake.reader_pages = reader_pages
    eng = FigEngine({1: "Intro text.\n\n![](image)\n\nFigure 1.1. A tree\n", 2: "Second page with $f ( w )$ only.\n"})
    res = transcribe.transcribe(path, [1, 2], str(tmp_path / "work"), str(tmp_path / "store"), SHA, engine=eng,
                                backend="api", page_count=3, log=lambda *_: None, **kw)
    return path, eng, res


def test_transcribe_cuts_links_and_describes_each_figure_once(tmp_path, monkeypatch):
    fake = FigLLM()
    path, eng, res = _run(tmp_path, monkeypatch, fake)
    rec = store.read_page(str(tmp_path / "store"), SHA, 1)
    f = rec["figures"][0]
    assert res["figures"] == 1 and f["label"] == "Figure 1.1" and f["description"] == "A tree with root $x_1$."
    assert "![Figure 1.1](figure:%s/p0001/1)" % S12 in rec["markdown"]
    assert os.path.isfile(os.path.join(str(tmp_path / "store"), SHA, "figures", f["file"]))
    assert store.figures(str(tmp_path / "store"), SHA)[0]["page"] == 1
    n = fake.calls.count("f0001-1")
    _run(tmp_path, monkeypatch, fake)                                    # cached per crop: not asked again
    assert n == 1 and fake.calls.count("f0001-1") == 1


def test_an_unmarked_description_is_retried_then_left_empty(tmp_path, monkeypatch):
    fake = FigLLM(bad=True)
    _path, _eng, _res = _run(tmp_path, monkeypatch, fake)
    assert fake.calls.count("f0001-1") == 2
    assert store.read_page(str(tmp_path / "store"), SHA, 1)["figures"][0]["description"] == ""


def test_descriptions_can_be_switched_off(tmp_path, monkeypatch):
    fake = FigLLM()
    _run(tmp_path, monkeypatch, fake, describe_figures=False)
    assert not [c for c in fake.calls if c.startswith("f")]


def test_a_figure_with_a_problem_gets_a_double_mark(tmp_path, monkeypatch):
    md, marks = transcribe.figure_marks("![Figure](figure:%s/p0005/1)\n" % S12, [{"id": 2, "level": "!"}],
                                        [{"id": 1, "label": "", "box": None, "problem": "no region"}], SHA, 5)
    assert marks[-1]["id"] == 3 and marks[-1]["level"] == "!!" and "figure 1: no region" in marks[-1]["reason"]
    assert "(figure:%s/p0005/1) [!!](mark:%s/p0005/3)" % (S12, S12) in md


def test_complete_finds_a_dropped_display_formula_and_a_missing_figure():
    parser = "Text $a+b$.\n\n$$\nx = y + z\n$$\n\nMore $c$.\n\n$$\n\\sum_i p_i = 1\n$$\n"
    final = "Text $a+b$.\n\n$$x = y + z$$ [!](mark:%s/p0001/1)\n\nMore $c$.\n" % S12
    f = complete.formulas(parser, final)
    assert f["display"] == 2 and f["display_found"] == 1 and "\\sum_i" in f["missing"][0] and f["coverage"] < 1
    rep = complete.page_report({"page": 4, "markdown": final, "figures": []}, parser, [(0.2, 0.2, 0.8, 0.6)], ["2.1"])
    assert any("Figure 2.1" in p for p in rep["problems"]) and any("1 figure region" in p for p in rep["problems"])
    ok = complete.page_report({"page": 4, "markdown": parser, "figures": [{"id": 1, "label": "Figure 2.1", "problem": ""}]},
                              parser, [(0.2, 0.2, 0.8, 0.6)], ["2.1"])
    assert ok["problems"] == [] and ok["formulas"]["display_found"] == 2
    assert "display formulas found 2/2" in complete.render({"pages": [ok], "missing_pages": [], "display": 2,
                                                             "display_found": 2, "math_tokens_coverage": 1.0,
                                                             "figures": 1, "problems": 0})
    json.dumps(rep)

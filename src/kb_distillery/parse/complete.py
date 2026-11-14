"""Is everything on the page in the transcript? Formulas and figures, counted against independent witnesses.

    formulas   every formula the parser (MinerU) read is lined up with the stored transcript token by token; a display
               formula of which less than half is found is listed as possibly missing. `coverage` is the share of
               the parser's maths tokens found in the transcript (both readings of a hard page differ a little, so it
               is a signal, not a proof: a missing formula shows as a dip, a rewritten one does not).
    figures    the parser's figure regions, the figure links in the transcript, and the captions the PDF's own text
               layer prints ("Figure 3.1", "Fig. 2") must agree; a figure with a `problem` (see `figures`) is listed.

Nothing here calls a model; `report` reads the store, the parser cache and the PDF.
"""
from __future__ import annotations

import json
import re

from . import compare, figures, store
from . import run as runner

MARK = re.compile(r"\s?\[!!?\]\(mark:[^)]*\)")
FIG_LINK = re.compile(r"!\[[^\]\n]*\]\(figure:[^)]*\)")
TEXT_CAPTION = re.compile(r"^\s*(Figure|Fig\.|FIGURE)\s*(\d+(?:\.\d+)*)", re.M)
FOUND = 0.5                  # a display formula with less than this share of its tokens found is listed


def _plain(md: str) -> str:
    return FIG_LINK.sub("![](figure)", MARK.sub("", md))


def formulas(parser_md: str, final_md: str) -> dict:
    """{display, display_found, coverage, missing: [parser LaTeX of displays mostly not found]} for one page."""
    al = compare.align(parser_md, _plain(final_md))
    hit = set()
    for op, i1, i2, _j1, _j2 in al.opcodes:
        if op == "equal":
            hit.update(range(i1, i2))
    _toks, spans = compare.page_tokens(al.md_a)
    math_idx = [i for i, t in enumerate(al.ta) if t.math]
    out = {"display": 0, "display_found": 0, "coverage": round(sum(i in hit for i in math_idx) / len(math_idx), 3)
           if math_idx else 1.0, "missing": []}
    for sp in spans:
        if not sp.display:
            continue
        idx = [i for i, t in enumerate(al.ta) if t.math and sp.a <= t.a < sp.b]
        if not idx:
            continue
        out["display"] += 1
        if sum(i in hit for i in idx) / len(idx) >= FOUND:
            out["display_found"] += 1
        else:
            out["missing"].append(al.md_a[sp.a:sp.b].strip())
    return out


def text_captions(pdf: str, page: int) -> list:
    """Figure numbers the PDF's text layer prints at the start of a line on `page` ("Figure 3.1" -> "3.1")."""
    from kb_distillery.storage.pdf import PdfDoc
    with PdfDoc(pdf) as d:
        text = d.page_text(page - 1)
    return [m.group(2) for m in TEXT_CAPTION.finditer(text or "")]


def _num(label: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)*)", label or "")
    return m.group(1) if m else ""


def page_report(rec: dict, parser_md: str | None, regions: list, captions: list) -> dict:
    figs = rec.get("figures", [])
    rep = {"page": rec["page"], "formulas": formulas(parser_md, rec["markdown"]) if parser_md is not None else None,
           "figures": len(figs), "regions": len(figures.regions(regions)), "captions": captions,
           "problems": ["figure %d: %s" % (f["id"], f["problem"]) for f in figs if f.get("problem")]}
    labels = {_num(f.get("label", "")) for f in figs}
    for c in captions:
        if c not in labels:
            rep["problems"].append("the PDF prints a caption 'Figure %s' here but the transcript has no figure with that "
                                   "number" % c)
    if rep["regions"] != len(figs) and not any("did not place" in p or "no figure region" in p for p in rep["problems"]):
        rep["problems"].append("the parser found %d figure region(s), the transcript has %d figure(s)" % (rep["regions"],
                                                                                                       len(figs)))
    return rep


def report(pdf: str, root: str, sha: str, pages: list, work: str, engine=None) -> dict:
    """The completeness report of `pages` of a stored transcript: per page and totals."""
    out = {"pages": [], "missing_pages": [], "display": 0, "display_found": 0, "math_tokens_coverage": None,
           "figures": 0, "problems": 0}
    covs = []
    for p in pages:
        rec = store.read_page(root, sha, p)
        if rec is None:
            out["missing_pages"].append(p)
            continue
        parser_md, regions = None, []
        if engine is not None:
            try:
                with open(runner.cache_path(work, engine.name, p), encoding="utf-8") as f:
                    prec = json.load(f)
                parser_md = engine.body(prec)[0] if hasattr(engine, "body") else engine.markdown(prec)
                regions = [list(b) for b in engine.figures(prec, 1.0, 1.0)] if hasattr(engine, "figures") else []
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        rep = page_report(rec, parser_md, regions, text_captions(pdf, p))
        out["pages"].append(rep)
        if rep["formulas"]:
            out["display"] += rep["formulas"]["display"]
            out["display_found"] += rep["formulas"]["display_found"]
            covs.append(rep["formulas"]["coverage"])
        out["figures"] += rep["figures"]
        out["problems"] += len(rep["problems"]) + (len(rep["formulas"]["missing"]) if rep["formulas"] else 0)
    out["math_tokens_coverage"] = round(sum(covs) / len(covs), 3) if covs else None
    return out


def render(rep: dict) -> str:
    """The report as text: totals, then every page that has something to look at."""
    lines = ["pages %d (%d not stored)  display formulas found %d/%d  maths coverage %s  figures %d  to check %d" % (
        len(rep["pages"]) + len(rep["missing_pages"]), len(rep["missing_pages"]), rep["display_found"], rep["display"],
        rep["math_tokens_coverage"], rep["figures"], rep["problems"])]
    for r in rep["pages"]:
        fm = r["formulas"]
        items = list(r["problems"]) + ["display formula possibly missing: %s" % " ".join(x.split())[:160]
                                       for x in (fm["missing"] if fm else [])]
        if fm and fm["coverage"] < 0.8:
            items.append("only %.0f%% of the parser's maths tokens are in the transcript" % (100 * fm["coverage"]))
        for it in items:
            lines.append("  p%d  %s" % (r["page"], it))
    if rep["missing_pages"]:
        lines.append("  not stored: %s" % ", ".join(map(str, rep["missing_pages"])))
    return "\n".join(lines)

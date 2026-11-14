"""PDF pages -> a marked transcript in the parsed store.

    parser (MinerU, local)  --+
                              +--> compare --> judge (only where they differ) --> auditor (whole page) --> transcript
    reader (vision model)   --+                                                                          with marks

The reader's page is the transcript. The parser is the independent witness: where the two agree symbol for symbol the
text stands. Where they differ the judge looks at the page again, and at the end the auditor reads the whole result
against the page once more. What comes out carries a mark wherever a single voice decided:

    the judge is sure the transcript is right        no mark
    the judge is sure it is wrong and gives a fix    the fix is applied, mark `!`
    the judge hesitates, or gives no answer          mark `!!` (its fix, if any, is applied)
    the reader itself wrote \\unsure{...}             mark `!`
    the auditor finds a difference                   its fix is applied, mark `!`; `!!` when it is unsure, gives no fix,
                                                     or the place cannot be found
    a page with only one reading                     the whole page is marked (`!` reader only, `!!` parser only)

A mark is a Markdown link right after the formula, `[!](mark:<sha12>/p0188/3)`, plus a record in the page's JSON with the
other reading, what was replaced and a crop of that place of the page (`crops/p0188-3.png`).
"""
from __future__ import annotations

import json
import os
import re

from . import audit, compare, judge, reader, store
from . import run as runner
from .engines import EngineError

PAD = 0.012                  # crop padding, as a fraction of the page
CROP_WIDTH = 1600
LEVELS = ("!", "!!")
MARK_LINK = re.compile(r"\[(!!?)\]\(mark:([0-9a-f]{12})/p(\d{4})/(\d+)\)")


def mark_link(level: str, sha: str, page: int, n: int) -> str:
    return "[%s](mark:%s/p%04d/%d)" % (level, sha[:12], page, n)


def _worse(a: str, b: str) -> str:
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def _unwrap(text: str) -> str:
    """`\\unsure{x}` -> `x`, innermost last."""
    while True:
        sp = judge.unsure_spans(text)
        if not sp:
            return text
        s, e, i0, i1 = sp[-1]
        text = text[:s] + text[i0:i1] + text[e:]


def _box_for(boxes: list, a: int, b: int):
    """Union of the parser blocks that cover characters [a, b) of its Markdown; the nearest block when none does."""
    hit = [bx for s, e, bx in boxes if bx and s < max(b, a + 1) and e > a]
    if not hit:
        near = [(min(abs(s - a), abs(e - a)), bx) for s, e, bx in boxes if bx]
        hit = [min(near, key=lambda t: t[0])[1]] if near else []
    if not hit:
        return None
    return [min(x[0] for x in hit), min(x[1] for x in hit), max(x[2] for x in hit), max(x[3] for x in hit)]


def decide(item: judge.Item, v: judge.Verdict | None) -> tuple:
    """(level or "", replacement or None, reason) for one judged place."""
    if v is None or not v.verdict:
        return "!!", None, "the two readings differ and the judge gave no answer"
    if v.verdict == "transcript":
        return ("", None, "") if v.sure else ("!", None, "the two readings differ; the judge kept the transcript but was not sure")
    fix = v.fix.strip() if v.fix and v.fix.strip() and v.fix.strip() != item.transcript.strip() else None
    if fix is not None and compare.dollars(fix) % 2 != compare.dollars(item.transcript) % 2:
        fix = None                                                  # it would open or close a formula: not applied
    if fix is None:
        return "!!", None, "the judge says the transcript is wrong here and gave no usable fix"
    if not v.sure:
        return "!!", fix, "the judge replaced the transcript here but was not sure"
    return "!", fix, "the judge replaced the transcript here (it agreed with %s)" % (
        "the other reading" if v.verdict == "other" else "neither reading")


def apply_edits(md: str, edits: list) -> tuple:
    """Apply non-overlapping `edits` [(start, end, new text)] -> (new Markdown, remap). `remap(pos)` moves an offset of
    the old text to the new one; an offset inside a replaced stretch lands at the end of its replacement."""
    edits = sorted(edits, key=lambda e: e[0])
    out, pos, table, shift = [], 0, [], 0
    for s, e, new in edits:
        out.append(md[pos:s])
        out.append(new)
        pos = e
        shift += len(new) - (e - s)
        table.append((s, e, e + shift))                            # old stretch -> end of its replacement in the new text
    out.append(md[pos:])

    def remap(p: int) -> int:
        delta = 0
        for s, e, end_new in table:
            if p <= s:
                break
            if p < e:
                return end_new
            delta = end_new - e
        return p + delta
    return "".join(out), remap


def judged(md: str, items: list, verdicts: dict) -> tuple:
    """Stage one on the reader's page: (text with the judge's fixes and without \\unsure wrappers, [marks with `pos`])."""
    ops: list = []                                   # (start, end, new text, mark)
    wrappers = judge.unsure_spans(md)
    for it in items:
        level, fix, reason = decide(it, verdicts.get(it.id))
        if level:
            s, e = it.span
            for ws, we, _i0, _i1 in wrappers:                       # a wrapper the place cuts into goes with it, whole
                if ws < e and we > s:
                    s, e = min(s, ws), max(e, we)
            if ops and s < ops[-1][1]:
                s = ops[-1][1]
            new = _unwrap(md[s:it.span[0]] + (fix if fix is not None else md[it.span[0]:it.span[1]]) + md[it.span[1]:e])
            ops.append((s, e, new, {"level": level, "reason": reason, "other": it.other,
                                    "was": md[it.span[0]:it.span[1]] if fix is not None else "",
                                    "a_span": it.other_span}))
    for s, e, i0, i1 in wrappers:
        if any(o[0] < e and o[1] > s for o in ops):
            continue                                                # a marked place already covers it
        if any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2, _a, _b in wrappers):
            continue                                                # nested: the outer wrapper carries the mark
        ops.append((s, e, _unwrap(md[i0:i1]), {"level": "!", "reason": "the reader marked this as hard to read",
                                               "other": "", "was": "", "a_span": None}))
    text, remap = apply_edits(md, [(s, e, new) for s, e, new, _m in ops])
    marks = [dict(m, pos=remap(e)) for _s, e, _new, m in ops]
    return text, marks


def audited(md: str, marks: list, findings: list | None) -> tuple:
    """Stage two: apply the auditor's findings to the text of stage one -> (text, marks with `pos` moved along)."""
    if findings is None:
        return md, marks + [{"level": "!", "reason": "the auditor gave no readable answer for this page", "other": "",
                             "was": "", "a_span": None, "pos": 0}]
    ops, loose = [], []
    for f in findings:
        says = "the auditor: the page says %s" % (f["page_says"] or "something else here")
        span = audit.locate(md, f["snippet"])
        fix = _unwrap(f["fix"]) if f["fix"].strip() and f["fix"].strip() != f["snippet"].strip() else None
        if span is not None and fix is not None and compare.dollars(fix) % 2 != compare.dollars(md[span[0]:span[1]]) % 2:
            fix = None                                              # it would open or close a formula: not applied
        if span is None or any(o[0] < span[1] and o[1] > span[0] for o in ops):
            loose.append({"level": "!!", "reason": says + " (near: %s)" % f["snippet"][:60], "other": "", "was": "",
                          "a_span": None, "pos": span[1] if span else 0})
            continue
        level = "!" if (fix is not None and f["sure"]) else "!!"
        ops.append((span[0], span[1], fix if fix is not None else md[span[0]:span[1]],
                    {"level": level, "reason": says, "other": "", "was": md[span[0]:span[1]] if fix is not None else "",
                     "a_span": None}))
    text, remap = apply_edits(md, [(s, e, new) for s, e, new, _m in ops])
    out = [dict(m, pos=remap(m["pos"])) for m in marks]
    out += [dict(m, pos=remap(e)) for _s, e, _new, m in ops]
    out += [dict(m, pos=remap(m["pos"])) for m in loose]
    return text, out


def finish(md: str, marks: list, parser_md: str | None, boxes: list, sha: str, page: int) -> tuple:
    """Put each mark's link right after its formula (after a display block: on its own line; a mark with no place: on top
    of the page) -> (Markdown, [mark records])."""
    _, spans = compare.page_tokens(md)
    al = None
    grouped: dict = {}
    for m in sorted(marks, key=lambda m: m["pos"]):
        pos = m["pos"]
        encl = [sp for sp in spans if sp.a < pos <= sp.b]
        at = encl[0].b if encl else pos
        while not encl and 0 < at < len(md) and md[at - 1].isalnum() and md[at].isalnum():
            at += 1                                                 # never inside a word
        nxt = [sp for sp in spans if sp.a < at < sp.b]
        if nxt:
            at = nxt[0].b                                           # nor inside the next formula
        text = md[encl[0].a:encl[0].b] if encl else md[max(0, pos - 80):at].strip()
        if at in grouped:
            g = grouped[at]
            g["level"] = _worse(g["level"], m["level"])
            g["reason"] += "; " + m["reason"]
            g["was"] = g["was"] or m["was"]
            g["other"] = g["other"] or m["other"]
            continue
        if m.get("a_span") is not None:
            a_lo, a_hi = m["a_span"]
        elif parser_md is not None and pos > 0:
            al = al or compare.align(parser_md, md)
            a_lo = a_hi = al.b_to_a(max(0, pos - 1))
        else:
            a_lo = a_hi = None
        grouped[at] = {"display": bool(encl and encl[0].display) or any(sp.b == at and sp.display for sp in spans),
                       "level": m["level"], "reason": m["reason"], "text": text if pos > 0 else "", "was": m["was"],
                       "other": m["other"], "box": _box_for(boxes, a_lo, a_hi) if (boxes and a_lo is not None) else None}
    recs = [dict(grouped[at], id=n, at=at) for n, at in enumerate(sorted(grouped), 1)]
    out, pos = [], len(md)
    for r in reversed(recs):
        link = mark_link(r["level"], sha, page, r["id"])
        at = r.pop("at")
        display = r.pop("display")
        if at == 0:
            piece = link + "\n\n"
        elif display:
            piece = "\n\n" + link
        else:
            piece = " " + link
        out.append(md[at:pos])
        out.append(piece)
        pos = at
    out.append(md[:pos])
    return "".join(reversed(out)), recs


def page_mark(md: str, marks: list, level: str, reason: str, sha: str, page: int) -> tuple:
    """A page with one reading only: one more mark for the whole page, on top (id 0, no box: the crop is the page)."""
    return mark_link(level, sha, page, 0) + "\n\n" + md, [{"id": 0, "level": level, "reason": reason, "text": "",
                                                           "was": "", "other": "", "box": None}] + marks


def write_crops(pdf: str, page: int, marks: list, root: str, sha: str) -> None:
    """One PNG per boxed mark under `<root>/<sha>/crops/`; the record gets its file name as `crop`."""
    d = os.path.join(root, sha, "crops")
    if os.path.isdir(d):
        for name in os.listdir(d):                                  # crops of an earlier run of this page
            if name.startswith("p%04d-" % page) and name.endswith(".png"):
                os.unlink(os.path.join(d, name))
    todo = [m for m in marks if m.get("box")]
    if not todo:
        return
    from kb_distillery.storage.pdf import PdfDoc
    os.makedirs(d, exist_ok=True)
    with PdfDoc(pdf) as doc:
        im = doc.render(page - 1, CROP_WIDTH)
    w, h = im.size
    for m in todo:
        x0, y0, x1, y1 = m["box"]
        box = (int(max(0.0, x0 - PAD) * w), int(max(0.0, y0 - PAD) * h),
               int(min(1.0, x1 + PAD) * w), int(min(1.0, y1 + PAD) * h))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            continue
        name = "p%04d-%d.png" % (page, m["id"])
        im.crop(box).save(os.path.join(d, name))
        m["crop"] = name


def _parser_page(engine, work: str, page: int) -> tuple:
    """(Markdown, [(start, end, box)]) of the parser's page: its body without running heads when the engine can tell."""
    with open(runner.cache_path(work, engine.name, page), encoding="utf-8") as f:
        rec = json.load(f)
    if hasattr(engine, "body"):
        return engine.body(rec)
    return engine.markdown(rec), (engine.boxes(rec) if hasattr(engine, "boxes") else [])


def llm_backend(backend: str | None) -> str:
    from kb_distillery import llm
    return llm.resolve_backend(backend)


def estimate(n_pages: int, backend: str, with_audit: bool = True) -> float:
    per = reader.USD_PER_PAGE.get(backend, 0.035) + judge.USD_PER_PAGE.get(backend, 0.012)
    per += audit.USD_PER_PAGE.get(backend, 0.035) if with_audit else 0.0
    return round(n_pages * per, 2)


def transcribe(pdf: str, pages: list, work: str, root: str, sha: str, engine=None, backend: str | None = None,
               model: str = reader.MODEL, judge_model: str = judge.MODEL, audit_model: str | None = audit.MODEL,
               source: str = "", page_count: int = 0, force: bool = False, max_usd: float | None = None,
               log=print) -> dict:
    """Read `pages` of `pdf` with the parser and the reader, judge their differences, audit the result and store the
    marked transcript under `<root>/<sha>/`. `work` holds every intermediate (resumable: nothing already done is done
    again). `audit_model=None` skips the auditor. `max_usd` is a ceiling on the run: a stage whose estimate would cross
    it is skipped (no judge: every difference becomes `!!`; no auditor: pages are stored unaudited) and named in "skipped".
    Returns {"pages": {page: status}, "marks": {"!": n, "!!": n}, "usd": x, "failed": {page: why}}."""
    usd = 0.0
    parsed: set = set()
    if engine is not None:
        try:
            res = runner.run(engine, pdf, pages, work, force=force, log=log)
            parsed = set(res["parsed"]) | set(res["skipped"])
        except EngineError as e:
            log("parser unavailable, pages will carry a single-reader mark: %s" % e)
    r = reader.read(pdf, pages, work, backend=backend, model=model, force=force, log=log)
    usd += r["usd"]
    have = set(r["read"]) | set(r["skipped"])
    parser_md: dict = {}
    boxes: dict = {}
    reader_md: dict = {}
    todo: dict = {}
    images: dict = {}
    for p in pages:
        if p in have:
            with open(reader.page_path(work, p), encoding="utf-8") as f:
                reader_md[p] = f.read()
        if p in have and p in parsed:
            parser_md[p], boxes[p] = _parser_page(engine, work, p)
            todo[p] = judge.items(compare.align(parser_md[p], reader_md[p]))
            if todo[p]:
                images[p] = reader.render(pdf, p, work)
    skipped: list = []
    bk = llm_backend(backend)

    def over(stage_name: str, n: int, per_page: dict) -> bool:
        if max_usd is None or usd + n * per_page.get(bk, 0.0) <= max_usd:
            return False
        log("%s skipped: it would take the run above $%.2f" % (stage_name, max_usd))
        skipped.append(stage_name)
        return True

    verdicts, j_usd = ({}, 0.0) if over("judge", sum(1 for v in todo.values() if v), judge.USD_PER_PAGE) else \
        judge.ask(todo, images, work, backend=backend, model=judge_model, force=force, log=log)
    usd += j_usd
    stage: dict = {}                                                 # page -> (text, marks) after the judge
    for p in reader_md:
        stage[p] = judged(reader_md[p], todo.get(p, []), verdicts.get(p, {}))
    if audit_model and not over("auditor", len(stage), audit.USD_PER_PAGE):
        findings, a_usd = audit.ask({p: t for p, (t, _m) in stage.items()},
                                    {p: reader.render(pdf, p, work) for p in stage},
                                    work, backend=backend, model=audit_model, force=force, log=log)
        usd += a_usd
        for p in stage:
            stage[p] = audited(stage[p][0], stage[p][1], findings.get(p))
    out = {"pages": {}, "marks": {"!": 0, "!!": 0}, "usd": round(usd, 4), "failed": dict(r["failed"]), "skipped": skipped}
    for p in pages:
        if p in stage:
            md, marks = finish(stage[p][0], stage[p][1], parser_md.get(p), boxes.get(p, []), sha, p)
            if p not in parsed:
                md, marks = page_mark(md, marks, "!", "only the reader read this page (no parser output to compare with)",
                                      sha, p)
        elif p in parsed:
            text, _b = _parser_page(engine, work, p)
            md, marks = page_mark(text, [], "!!", "only the parser read this page (the reader failed)", sha, p)
        else:
            out["failed"].setdefault(p, "neither the parser nor the reader produced this page")
            continue
        write_crops(pdf, p, marks, root, sha)
        rec = store.write_transcript_page(root, sha, p, md, marks, engine="reader:%s+%s+audit:%s" % (
            model, engine.name if engine is not None and p in parsed else "none", audit_model or "none"))
        out["pages"][p] = rec["status"]
        for m in marks:
            out["marks"][m["level"]] += 1
    store.write_manifest(root, sha, source or os.path.basename(pdf), page_count,
                         engine="reader+%s" % (engine.name if engine is not None and parsed else "none"))
    return out

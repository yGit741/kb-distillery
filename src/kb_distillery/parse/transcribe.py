"""PDF pages -> a marked transcript in the parsed store.

    parser (MinerU, local)  --+
                              +--> compare --> judge (only where they differ) --> transcript with `!` / `!!` marks
    reader (vision model)   --+

The reader's page is the transcript. The parser is the independent witness: where the two agree symbol for symbol the
text stands unmarked. Where they differ the judge looks at the page again:

    the judge is sure the transcript is right        no mark
    the judge is sure it is wrong and gives a fix    the fix is applied, mark `!`
    the judge hesitates, or gives no answer          mark `!!` (its fix, if any, is applied)
    the reader itself wrote \\unsure{...}             mark `!`
    a page with only one reading                     the whole page is marked (`!` reader only, `!!` parser only)

A mark is a Markdown link right after the formula, `[!](mark:<sha12>/p0188/3)`, plus a record in the page's JSON with the
other reading, what was replaced and a crop of that place of the page (`crops/p0188-3.png`).
"""
from __future__ import annotations

import json
import os
import re

from . import compare, judge, reader, store
from . import run as runner
from .engines import EngineError

PAD = 0.012                  # crop padding, as a fraction of the page
CROP_WIDTH = 1600
LEVELS = ("!", "!!")


def mark_link(level: str, sha: str, page: int, n: int) -> str:
    return "[%s](mark:%s/p%04d/%d)" % (level, sha[:12], page, n)


MARK_LINK = re.compile(r"\[(!!?)\]\(mark:([0-9a-f]{12})/p(\d{4})/(\d+)\)")


def _worse(a: str, b: str) -> str:
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


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
    if fix is None:
        return "!!", None, "the judge says the transcript is wrong here and gave no usable fix"
    if not v.sure:
        return "!!", fix, "the judge replaced the transcript here but was not sure"
    return "!", fix, "the judge replaced the transcript here (it agreed with %s)" % (
        "the other reading" if v.verdict == "other" else "neither reading")


def assemble(al: compare.Alignment | None, md: str, items: list, verdicts: dict, boxes: list, sha: str, page: int) -> tuple:
    """(Markdown with mark links, [mark records]) of one page. `md` is the reader's page; `al` is None without a parser."""
    _, spans = compare.page_tokens(md)
    ops: list = []                                   # (start, end, replacement or None, level, reason, item or None)
    for it in items:
        level, fix, reason = decide(it, verdicts.get(it.id))
        if level or fix is not None:
            ops.append([it.span[0], it.span[1], fix, level or "!", reason, it])
    for s, e, _i0, _i1 in judge.unsure_spans(md):
        over = [o for o in ops if o[0] < e and o[1] > s]
        if over:
            continue                                                # the judged place already carries a mark
        ops.append([s, e, None, "!", "the reader marked this as hard to read", None])
    ops.sort(key=lambda o: o[0])
    marks: list = []
    pending: dict = {}                               # insertion point in the original text -> mark number
    for o in ops:
        s, e, fix, level, reason, it = o
        encl = [sp for sp in spans if sp.a <= s and e <= sp.b]
        at = encl[0].b if encl else e
        text_now = fix if fix is not None else md[s:e]
        if at in pending:                                           # two places in one formula share a mark
            m = marks[pending[at] - 1]
            m["level"] = _worse(m["level"], level)
            m["reason"] += "; " + reason
        else:
            n = len(marks) + 1
            pending[at] = n
            a_lo, a_hi = it.other_span if it is not None else ((al.b_to_a(s),) * 2 if al is not None else (0, 0))
            marks.append({"id": n, "level": level, "reason": reason, "text": _plain(text_now),
                          "was": md[s:e] if fix is not None else "", "other": it.other if it is not None else "",
                          "box": _box_for(boxes, a_lo, a_hi) if boxes else None, "at": at})
    text = _insert_links(md, ops, marks, pending, sha, page)
    for m in marks:
        m.pop("at")
    return _unwrap_unsure(text), marks


def _insert_links(md: str, ops: list, marks: list, pending: dict, sha: str, page: int) -> str:
    """Apply the replacements and put each mark's link right after its formula (after a display block: its own line)."""
    events = [(o[0], 0, o) for o in ops] + [(at, 1, n) for at, n in pending.items()]
    events.sort(key=lambda t: (t[0], t[1]))
    out, pos = [], 0
    for at, kind, payload in events:
        if kind == 0:
            s, e, fix = payload[0], payload[1], payload[2]
            out.append(md[pos:s])
            out.append(fix if fix is not None else md[s:e])
            pos = e
        else:
            if at > pos:
                out.append(md[pos:at])
                pos = at
            m = marks[payload - 1]
            link = mark_link(m["level"], sha, page, m["id"])
            before = "".join(out)[-2:]
            out.append(("\n\n" + link) if before == "$$" else (" " + link))
    out.append(md[pos:])
    return "".join(out)


def _unwrap_unsure(md: str) -> str:
    while True:
        sp = judge.unsure_spans(md)
        if not sp:
            return md
        s, e, i0, i1 = sp[-1]
        md = md[:s] + md[i0:i1] + md[e:]


def _plain(text: str) -> str:
    return _unwrap_unsure(text)


def page_mark(md: str, level: str, reason: str, sha: str, page: int) -> tuple:
    """A page with one reading only: one mark for the whole page, placed on top (no box: the crop is the page)."""
    return mark_link(level, sha, page, 0) + "\n\n" + md, [{"id": 0, "level": level, "reason": reason, "text": "",
                                                           "was": "", "other": "", "box": None}]


def write_crops(pdf: str, page: int, marks: list, root: str, sha: str) -> None:
    """One PNG per boxed mark under `<root>/<sha>/crops/`; the record gets its file name as `crop`."""
    todo = [m for m in marks if m.get("box")]
    if not todo:
        return
    from kb_distillery.storage.pdf import PdfDoc
    d = os.path.join(root, sha, "crops")
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


def estimate(n_pages: int, backend: str) -> float:
    return round(reader.estimate(n_pages, backend) + n_pages * judge.USD_PER_PAGE.get(backend, 0.012), 2)


def transcribe(pdf: str, pages: list, work: str, root: str, sha: str, engine=None, backend: str | None = None,
               model: str = reader.MODEL, judge_model: str = judge.MODEL, source: str = "", page_count: int = 0,
               force: bool = False, log=print) -> dict:
    """Read `pages` of `pdf` with the parser and the reader, judge their differences and store the marked transcript
    under `<root>/<sha>/`. `work` holds every intermediate (resumable: nothing already done is done again).
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
    aligned: dict = {}
    todo: dict = {}
    images: dict = {}
    for p in pages:
        if p in have and p in parsed:
            with open(runner.md_path(work, p), encoding="utf-8") as f:
                md_a = f.read()
            with open(reader.page_path(work, p), encoding="utf-8") as f:
                md_b = f.read()
            al = compare.align(md_a, md_b)
            aligned[p] = al
            todo[p] = judge.items(al)
            if todo[p]:
                images[p] = reader.render(pdf, p, work)
    verdicts, j_usd = judge.ask(todo, images, work, backend=backend, model=judge_model, log=log)
    usd += j_usd
    out = {"pages": {}, "marks": {"!": 0, "!!": 0}, "usd": round(usd, 4), "failed": dict(r["failed"])}
    for p in pages:
        if p in aligned:
            with open(runner.cache_path(work, engine.name, p), encoding="utf-8") as f:
                boxes = engine.boxes(json.load(f)) if hasattr(engine, "boxes") else []
            al = aligned[p]
            md, marks = assemble(al, al.md_b, todo[p], verdicts.get(p, {}), boxes, sha, p)
        elif p in have:
            with open(reader.page_path(work, p), encoding="utf-8") as f:
                text = f.read()
            body, inner = assemble(None, text, [], {}, [], sha, p)
            md, marks = page_mark(body, "!", "only the reader read this page (no parser output to compare with)", sha, p)
            for m in inner:                                          # the reader's own \unsure marks keep their numbers
                marks.append(m)
        elif p in parsed:
            with open(runner.md_path(work, p), encoding="utf-8") as f:
                md, marks = page_mark(f.read(), "!!", "only the parser read this page (the reader failed)", sha, p)
        else:
            out["failed"].setdefault(p, "neither the parser nor the reader produced this page")
            continue
        write_crops(pdf, p, marks, root, sha)
        rec = store.write_transcript_page(root, sha, p, md, marks, engine="reader:%s+%s" % (
            model, engine.name if engine is not None and p in parsed else "none"))
        out["pages"][p] = rec["status"]
        for m in marks:
            out["marks"][m["level"]] += 1
    store.write_manifest(root, sha, source or os.path.basename(pdf), page_count, engine="reader+parser")
    return out

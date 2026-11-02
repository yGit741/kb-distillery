"""Windowed, resumable parse of chosen PDF pages into an output directory (never inside a knowledge base).

    <out>/<engine>/pNNNN.json   the engine's record per page: the resume cache (a page present is not parsed again)
    <out>/pNNNN.md              Markdown of that record
    <out>/timing.json           one entry per window: pages, seconds
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time



def parse_pages(text: str, page_count: int | None = None) -> list:
    """'1-5,8' -> [1,2,3,4,5,8] (1-based, sorted, unique); 'all' needs page_count."""
    text = text.strip().lower()
    if text == "all":
        if not page_count:
            raise ValueError("'all' needs the page count")
        return list(range(1, page_count + 1))
    out: set = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo < 1 or hi < lo or (page_count and hi > page_count):
            raise ValueError("bad page range %r" % part)
        out.update(range(lo, hi + 1))
    if not out:
        raise ValueError("no pages in %r" % text)
    return sorted(out)


def windows(pages: list, size: int) -> list:
    """Split sorted pages into windows of at most `size` pages."""
    return [pages[i:i + size] for i in range(0, len(pages), size)]


def cache_path(out: str, engine: str, page: int) -> str:
    return os.path.join(out, engine, "p%04d.json" % page)


def md_path(out: str, page: int) -> str:
    return os.path.join(out, "p%04d.md" % page)


def done_pages(out: str, engine: str) -> list:
    d = os.path.join(out, engine)
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return []
    return sorted(int(n[1:-5]) for n in names if n[0] == "p" and n.endswith(".json") and n[1:-5].isdigit())


def _atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def run(engine, pdf: str, pages: list, out: str, window: int = 8, force: bool = False, log=print) -> dict:
    """Parse `pages` of `pdf` with `engine` into `out`. Returns {"parsed": [...], "skipped": [...], "seconds": s}.
    Each window is cached the moment it finishes, so a killed run resumes at the next window."""
    have = set() if force else set(done_pages(out, engine.name))
    todo = [p for p in pages if p not in have]
    skipped = [p for p in pages if p in have]
    for p in skipped:                                                 # a page cached before its .md was written
        if not os.path.exists(md_path(out, p)):
            _write_md(engine, out, p)
    tpath = os.path.join(out, "timing.json")
    timing = json.load(open(tpath)) if os.path.exists(tpath) else []
    started = time.time()
    parsed: list = []
    missing_all: list = []
    for win in windows(todo, window):
        t0 = time.time()
        os.makedirs(os.path.join(out, ".work"), exist_ok=True)
        scratch = tempfile.mkdtemp(dir=os.path.join(out, ".work"))
        try:
            recs = engine.parse(pdf, win, scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        missing = [p for p in win if p not in recs]
        missing_all += missing
        for p, rec in sorted(recs.items()):
            if p in win:
                _atomic(cache_path(out, engine.name, p), json.dumps(rec, ensure_ascii=False))
                _write_md(engine, out, p)
                parsed.append(p)
        dt = time.time() - t0
        timing.append({"engine": engine.name, "pages": [p for p in win if p in recs], "seconds": round(dt, 1)})
        _atomic(tpath, json.dumps(timing, indent=1))
        log("window %s: %d page(s) in %.0fs%s" % (win, len(win) - len(missing), dt,
                                                   "  MISSING %s" % missing if missing else ""))
    return {"parsed": parsed, "skipped": skipped, "missing": missing_all,
            "seconds": round(time.time() - started, 1)}


def _write_md(engine, out: str, page: int) -> None:
    rec = json.load(open(cache_path(out, engine.name, page), encoding="utf-8"))
    _atomic(md_path(out, page), engine.markdown(rec))


def status(out: str, engine: str, pages: list | None = None) -> dict:
    done = done_pages(out, engine)
    want = pages if pages is not None else done
    tpath = os.path.join(out, "timing.json")
    timing = json.load(open(tpath)) if os.path.exists(tpath) else []
    timing = [t for t in timing if t.get("engine") == engine]
    secs = sum(t["seconds"] for t in timing)
    n = sum(len(t["pages"]) for t in timing)
    return {"engine": engine, "done": done, "missing": [p for p in want if p not in set(done)],
            "seconds": round(secs, 1), "seconds_per_page": round(secs / n, 1) if n else None}

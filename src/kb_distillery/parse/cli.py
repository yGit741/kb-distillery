"""`pixi run parse -- run|status|check|sample` (dark behind the `parsed-pdf` flag; output goes to a directory you name,
never into a knowledge base).

    parse run <pdf> --pages 1-5,8 --out DIR [--window 8] [--force]   MinerU on those pages, resumable per page
    parse status --out DIR [--pages ...]                              pages done / missing, seconds per page
    parse check <pdf> --out DIR [--pages ...]                         feed the parsed pages through the verifier
    parse sample <pdf> [-n 100] [--seed 7] [--build 60]               stratified page picks, build / unseen
    parse transcribe <pdf> --pages 1-5,8 --store DIR [--work DIR] [--backend subscription|api|batch] [--max-usd N]
                                                                      parser + reader + judge -> marked transcript
    parse marks --store DIR --sha SHA [--pages ...]                   the `!` / `!!` marks of a stored transcript

`transcribe` is the only command that calls a model (the reader and the judge, through kb_distillery.llm); it prints its
cost estimate first and stops when the estimate is above --max-usd. `--store` is a parsed store: a kb's `meta/parsed`,
or any directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import run as runner
from .engines import EngineError


def _engine(name: str):
    if name == "mineru":
        from .engines.mineru import MinerU
        return MinerU()
    raise SystemExit("unknown engine %r (only 'mineru')" % name)


def _page_count(pdf: str) -> int:
    from kb_distillery.storage.pdf import PdfDoc
    with PdfDoc(pdf) as d:
        return d.page_count


def _guard_out(out: str) -> str:
    """The output is a scratch / run directory: refuse a path inside a knowledge base's meta/ or wiki/ or raw/."""
    real = os.path.realpath(os.path.expanduser(out))
    d = real
    while d != os.path.dirname(d):                                    # inside any directory that holds a kb.toml
        if os.path.exists(os.path.join(d, "kb.toml")):
            raise SystemExit("refusing --out %s: it is inside the knowledge base %s" % (out, d))
        d = os.path.dirname(d)
    parts = real.split(os.sep)
    for bad in ("raw", "wiki", "meta", "think"):
        if bad in parts and ("kbs" in parts or "knowledge" in parts):
            raise SystemExit("refusing --out %s: it is inside a knowledge base (%s/)" % (out, bad))
    return real


def cmd_run(a) -> int:
    out = _guard_out(a.out)
    try:
        pages = runner.parse_pages(a.pages, _page_count(a.pdf))
    except ValueError as e:
        raise SystemExit("bad --pages: %s" % e)
    try:
        res = runner.run(_engine(a.engine), os.path.abspath(a.pdf), pages, out, window=a.window, force=a.force,
                         log=lambda m: print(m, file=sys.stderr, flush=True))
    except EngineError as e:
        raise SystemExit("engine failed: %s" % e)
    print(json.dumps({"parsed": len(res["parsed"]), "skipped": len(res["skipped"]), "missing": res["missing"],
                      "seconds": res["seconds"]}))
    return 1 if res["missing"] else 0


def cmd_status(a) -> int:
    out = _guard_out(a.out)
    pages = runner.parse_pages(a.pages) if a.pages else None
    print(json.dumps(runner.status(out, a.engine, pages)))
    return 0


def check_pages(pdf: str, out: str, pages: list, engine: str = "mineru") -> dict:
    """{page: [Flag]} for the parsed `pages`: reconcile plus structure, each page on its own."""
    from . import layer, reconcile, structure
    layers = {l.page: l for l in layer.read_pdf(pdf, pages)}
    absent = [p for p in pages if p not in layers or not os.path.exists(runner.md_path(out, p))]
    if absent:
        raise SystemExit("pages not in the PDF or not parsed yet: %s" % absent)
    eng = _engine(engine)
    for p, l in layers.items():                                  # text drawn inside a figure belongs to the figure
        rec = json.load(open(runner.cache_path(out, eng.name, p), encoding="utf-8"))
        l.figures = list(l.figures) + eng.figures(rec, l.width, l.height)
    res: dict = {}
    for p in pages:
        md = open(runner.md_path(out, p), encoding="utf-8").read()
        res[p] = reconcile.reconcile_page(md, layers[p]) + structure.check_structure([md], [layers[p]], first_page=p)
    return res


def cmd_check(a) -> int:
    out = _guard_out(a.out)
    pages = runner.parse_pages(a.pages) if a.pages else runner.done_pages(out, a.engine)
    res = check_pages(os.path.abspath(a.pdf), out, pages, a.engine)
    for p, fl in res.items():
        print("page %d: %d flag(s)" % (p, len(fl)))
        for f in fl:
            print("   %-16s %s" % (f.kind, f.detail))
    total = sum(len(v) for v in res.values())
    print("flags per page: %.1f over %d page(s)" % (total / max(1, len(res)), len(res)))
    return 0


def cmd_sample(a) -> int:
    from .sample import sample
    print(json.dumps(sample(os.path.abspath(a.pdf), a.n, a.seed, a.build)))
    return 0


def default_work(sha: str) -> str:
    base = os.environ.get("KB_PARSE_WORK") or os.path.join(os.path.expanduser("~"), ".cache", "kb-distillery", "parse")
    return os.path.join(base, sha[:12])


def cmd_transcribe(a) -> int:
    from kb_distillery import llm

    from . import store, transcribe
    pdf = os.path.abspath(a.pdf)
    count = _page_count(pdf)
    try:
        pages = runner.parse_pages(a.pages, count)
    except ValueError as e:
        raise SystemExit("bad --pages: %s" % e)
    with open(pdf, "rb") as f:
        sha = store.sha1_bytes(f.read())
    backend = llm.resolve_backend(a.backend)
    est = transcribe.estimate(len(pages), backend)
    print("transcribe: %d page(s), backend %s, estimated cost $%.2f" % (len(pages), backend, est), file=sys.stderr)
    if a.max_usd is not None and est > a.max_usd:
        raise SystemExit("estimate $%.2f is above --max-usd %.2f: nothing was run" % (est, a.max_usd))
    if a.dry_run:
        return 0
    work = _guard_out(a.work) if a.work else default_work(sha)
    res = transcribe.transcribe(pdf, pages, work, os.path.abspath(a.store), sha,
                                engine=None if a.engine == "none" else _engine(a.engine), backend=backend,
                                model=a.model, judge_model=a.judge_model, page_count=count, force=a.force,
                                log=lambda m: print(m, file=sys.stderr, flush=True))
    by = {}
    for st in res["pages"].values():
        by[st] = by.get(st, 0) + 1
    print(json.dumps({"sha": sha, "pages": by, "marks": res["marks"], "usd": res["usd"],
                      "failed": {str(k): v for k, v in res["failed"].items()}}))
    return 1 if res["failed"] else 0


def cmd_marks(a) -> int:
    from . import store
    pages = runner.parse_pages(a.pages) if a.pages else None
    for m in store.marks(os.path.abspath(a.store), a.sha, pages):
        print("p%04d/%d  %-2s  %s" % (m["page"], m["id"], m["level"], m["reason"]))
        if m.get("was"):
            print("      was:   %s" % m["was"].replace("\n", " ")[:160])
        if m.get("text"):
            print("      now:   %s" % m["text"].replace("\n", " ")[:160])
        if m.get("other"):
            print("      other: %s" % m["other"].replace("\n", " ")[:160])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="parse", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcribe")
    t.set_defaults(fn=cmd_transcribe)
    t.add_argument("pdf")
    t.add_argument("--pages", required=True, help="'1-5,8' or 'all'")
    t.add_argument("--store", required=True, help="parsed store: a kb's meta/parsed, or any directory")
    t.add_argument("--work", default="", help="intermediates (default ~/.cache/kb-distillery/parse/<sha12>)")
    t.add_argument("--engine", default="mineru", help="'mineru' or 'none' (reader only: every page is marked)")
    t.add_argument("--backend", default=None, choices=("subscription", "api", "batch"))
    t.add_argument("--model", default="sonnet")
    t.add_argument("--judge-model", default="sonnet")
    t.add_argument("--max-usd", type=float, default=None)
    t.add_argument("--dry-run", action="store_true", help="print the estimate and stop")
    t.add_argument("--force", action="store_true")
    mk = sub.add_parser("marks")
    mk.set_defaults(fn=cmd_marks)
    mk.add_argument("--store", required=True)
    mk.add_argument("--sha", required=True)
    mk.add_argument("--pages", default="")
    for name, fn in (("run", cmd_run), ("status", cmd_status), ("check", cmd_check), ("sample", cmd_sample)):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        if name in ("run", "check", "sample"):
            s.add_argument("pdf")
        if name != "sample":
            s.add_argument("--out", required=True, help="output directory (not inside a knowledge base)")
            s.add_argument("--pages", default="" if name != "run" else None, help="'1-5,8'")
            s.add_argument("--engine", default="mineru")
        if name == "run":
            s.add_argument("--window", type=int, default=8, help="pages per MinerU process (model load is ~1 min)")
            s.add_argument("--force", action="store_true")
        if name == "sample":
            s.add_argument("-n", type=int, default=100)
            s.add_argument("--seed", type=int, default=7)
            s.add_argument("--build", type=int, default=60)
    a = ap.parse_args(argv)
    if a.cmd == "run" and not a.pages:
        ap.error("run needs --pages")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

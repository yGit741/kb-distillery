"""`pixi run parse -- run|status|check|sample` (dark behind the `parsed-pdf` flag; output goes to a directory you name,
never into a knowledge base).

    parse run <pdf> --pages 1-5,8 --out DIR [--window 8] [--force]   MinerU on those pages, resumable per page
    parse status --out DIR [--pages ...]                              pages done / missing, seconds per page
    parse check <pdf> --out DIR [--pages ...]                         feed the parsed pages through the verifier
    parse sample <pdf> [-n 100] [--seed 7] [--build 60]               stratified page picks, build / unseen
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
    import fitz
    with fitz.open(pdf) as d:
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="parse", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
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

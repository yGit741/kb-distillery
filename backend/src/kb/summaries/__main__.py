"""CLI: python -m kb.summaries plan|run|show|apply (see kb.summaries)."""
import argparse
import collections
import sys

from kb.summaries import pipeline as P


def cmd_plan(a):
    pages = P.load_pages()
    by = collections.Counter(P.status(p) for p in pages)
    print("  ".join(f"{k} {v}" for k, v in sorted(by.items())))
    todo = P.todo(pages)
    kinds = collections.Counter((p["fm"].get("type"), p["fm"].get("depth")) for p in todo)
    for (t, d), n in kinds.most_common():
        print(f"  {n:4}  {t} / {d}")
    print(f"{len(todo)} page(s) need a summary")


def cmd_run(a):
    pages = P.todo(P.load_pages())
    done = P.latest()
    if not a.redo:
        pages = [p for p in pages if not (p["slug"] in done and not done[p["slug"]]["problems"]
                                          and done[p["slug"]]["summary_from"] == P.summary_hash(p["text"]))]
    pages.sort(key=lambda p: p["slug"] in done)           # pages that failed before go last, not first
    if a.slugs:
        want = set(a.slugs.split(","))
        pages = [p for p in pages if p["slug"] in want]
    pages = P.sample(pages, a.batch) if a.sample else pages[:a.batch]
    if not pages:
        print("nothing to do")
        return
    print(f"proposing {len(pages)} summaries with {a.model} ({P.PER_CALL}/call, {P.WORKERS} in flight)")
    rows = P.propose(pages, model=a.model, on_rows=P.save)
    ok = sum(not r["problems"] for r in rows)
    usd = sum(r["usd"] for r in rows)
    print(f"{ok}/{len(rows)} valid · ${usd:.3f} as the CLI reports it (subscription) → {P.PROPOSALS}")
    for r in rows:
        if r["problems"]:
            print(f"  ✗ {r['slug']}: {'; '.join(r['problems'])}" + (f" [{r['error']}]" if r.get("error") else ""))
    sys.exit(0 if ok == len(rows) else 1)


def cmd_show(a):
    props = list(P.latest().values())[-a.last:]
    pages = {p["slug"]: p for p in P.load_pages()}
    for r in props:
        p = pages.get(r["slug"])
        print(f"\n## {r['slug']}  [{p['fm'].get('type')}/{p['fm'].get('depth')}]" if p else f"\n## {r['slug']}")
        if p:
            print(f"   title: {P.title_of(p)}")
        print(f"   → {r['summary'] or '(none)'}  ({len(r['summary'])} chars)")
        for x in r["problems"]:
            print(f"   ✗ {x}")


def cmd_apply(a):
    written = P.apply(set(a.slugs.split(",")) if a.slugs else None)
    print(f"wrote {len(written)} summar{'y' if len(written) == 1 else 'ies'}")


def cmd_judge(a):
    from kb.summaries.judge import judge
    rep = judge(set(a.slugs.split(",")) if a.slugs else None, model=a.model)
    print(f"judge {rep['judge']}: {rep['graded']}/{rep['n']} graded · mean {rep['mean']} · "
          f"{rep['per_criterion']} · faithful fails {len(rep['faithful_fails'])} · "
          f"{'PASS' if rep['pass'] else 'FAIL'} → {rep['path']}")
    for g in sorted(rep["grades"], key=lambda g: g["score"] if g["score"] is not None else 0)[:a.worst]:
        print(f"  {g['score']}  {g['slug']}: {g.get('why', '')}")
    sys.exit(0 if rep["pass"] else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="summarize")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--batch", type=int, default=50)
    r.add_argument("--sample", action="store_true", help="stratified by type/depth, ≥5 Hebrew titles")
    r.add_argument("--slugs", default="")
    r.add_argument("--model", default=P.MODEL)
    r.add_argument("--redo", action="store_true", help="propose again even when a valid proposal exists")
    s = sub.add_parser("show")
    s.add_argument("--last", type=int, default=20)
    ap_ = sub.add_parser("apply")
    ap_.add_argument("--slugs", default="")
    j = sub.add_parser("judge", help="a stronger model grades the proposals (default Fable 5.1)")
    j.add_argument("--slugs", default="")
    j.add_argument("--model", default="claude-fable-5-1")
    j.add_argument("--worst", type=int, default=8)
    a = ap.parse_args(argv)
    {"plan": cmd_plan, "run": cmd_run, "show": cmd_show, "apply": cmd_apply, "judge": cmd_judge}[a.cmd](a)


if __name__ == "__main__":
    main()

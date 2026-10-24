"""Agent metrics: are the agents getting cheaper at the same accuracy?

    pixi run metrics -- ingest [--source DIR …]          session logs → meta/.ops/metrics/sessions.jsonl
    pixi run metrics -- report [--since YYYY-MM-DD] [--json]   per-task cost of real sessions
    pixi run metrics -- golden list | run [task …] --label L [--repeat N] [--ref REF] [--dry-run] [--keep]
    pixi run metrics -- baseline <name> [--golden LABEL] [--since D] [--until D]   freeze a summary
    pixi run metrics -- compare <baseline> [--golden LABEL] [--since D]            later numbers vs it
    pixi run metrics -- d1 init | push [--dry-run]

Two kinds of evidence: real sessions (what you actually spent, by task — noisy, but free) and golden
runs (the same 8 tasks every time, graded — the controlled before/after). Cheaper only counts when the
golden judge score and pass rate hold.
"""
import argparse
import json
import os
import sys

from kb.metrics import d1, golden, sessions, store

BASELINES = "baselines"


def _filter(recs, since=None, until=None):
    return [r for r in recs if (not since or (r.get("start") or "") >= since)
            and (not until or (r.get("start") or "") < until)]


def cmd_ingest(args):
    new = list(sessions.scan(args.source or None))
    allrecs = store.merge_sessions(new)
    print(f"ingested {len(new)} sessions; store holds {len(allrecs)} → {store.path('sessions.jsonl')}")
    return 0


def _table(summary, cols):
    lines = [f"{'task':12}" + "".join(f"{c:>14}" for c in cols)]
    for task, row in summary.items():
        lines.append(f"{task:12}" + "".join(f"{row.get(c)!s:>14}" for c in cols))
    return "\n".join(lines)


SESSION_COLS = ["n", "first_context_med", "usd_med", "usd_sum", "calls_med", "sub_share"]
GOLDEN_COLS = ["n", "usd_med", "first_context_med", "minutes_med", "score_med", "pass_rate", "flagged"]


def cmd_report(args):
    s = store.summarize_sessions(_filter(store.read("sessions.jsonl"), args.since, args.until))
    print(json.dumps(s, indent=2) if args.json else _table(s, SESSION_COLS))
    return 0


def cmd_golden(args):
    if args.action == "list":
        tasks, judge_cfg = golden.load_tasks()
        for t in tasks.values():
            print(f"{t['id']:24} {t.get('kind', ''):10} {t['model']}/{t.get('effort', '-'):7} "
                  f"{'core' if t.get('core', True) else 'extra'}  v{t.get('v', 1)}")
        print(f"judge: {judge_cfg.get('model', 'sonnet')}/{judge_cfg.get('effort', 'medium')} × {judge_cfg.get('samples', 2)}")
        return 0
    recs = golden.run(args.tasks or None, label=args.label, ref=args.ref, repeat=args.repeat,
                      dry_run=args.dry_run, keep=args.keep)
    return 0 if args.dry_run or all(r.get("passed") for r in recs) else 1


def _baseline_path(name):
    return store.path(os.path.join(BASELINES, f"{name}.json"))


def _current(args):
    out = {"sessions": store.summarize_sessions(_filter(store.read("sessions.jsonl"), args.since, args.until))}
    if args.golden:
        out["golden"] = store.summarize_golden([r for r in store.read("golden.jsonl") if r.get("label") == args.golden])
    return out


def cmd_baseline(args):
    p = _baseline_path(args.name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = {"name": args.name, "since": args.since, "until": args.until, "golden_label": args.golden, **_current(args)}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"baseline {args.name} → {p}")
    print(_table(data["sessions"], SESSION_COLS))
    if data.get("golden"):
        print(_table(data["golden"], GOLDEN_COLS))
    return 0


def _delta(old, new, cols):
    lines = [f"{'task':24}" + "".join(f"{c:>22}" for c in cols)]
    for task in sorted(set(old) | set(new)):
        o, n = old.get(task, {}), new.get(task, {})
        cells = []
        for c in cols:
            a, b = o.get(c), n.get(c)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
                cells.append(f"{a:g}→{b:g} ({(b - a) / a:+.0%})")
            else:
                cells.append(f"{a}→{b}")
        lines.append(f"{task:24}" + "".join(f"{c:>22}" for c in cells))
    return "\n".join(lines)


def cmd_compare(args):
    with open(_baseline_path(args.name), encoding="utf-8") as f:
        base = json.load(f)
    cur = _current(args)
    print(f"sessions: baseline {args.name} → now")
    print(_delta(base["sessions"], cur["sessions"], ["n", "first_context_med", "usd_med", "calls_med"]))
    if args.golden and base.get("golden"):
        print(f"\ngolden: {base['golden_label']} → {args.golden}")
        print(_delta(base["golden"], cur["golden"], ["usd_med", "score_med", "pass_rate"]))
    return 0


def cmd_d1(args):
    return d1.init() if args.action == "init" else d1.push(dry_run=args.dry_run)


def main(argv=None):
    p = argparse.ArgumentParser(prog="metrics", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest")
    s.add_argument("--source", action="append", help="a ~/.claude/projects-like dir (repeatable)")
    s.set_defaults(fn=cmd_ingest)
    for name, fn in (("report", cmd_report), ("baseline", cmd_baseline), ("compare", cmd_compare)):
        s = sub.add_parser(name)
        if name != "report":
            s.add_argument("name")
            s.add_argument("--golden", help="golden run label to include")
        s.add_argument("--since")
        s.add_argument("--until")
        s.add_argument("--json", action="store_true")
        s.set_defaults(fn=fn)
    s = sub.add_parser("golden")
    s.add_argument("action", choices=["list", "run"])
    s.add_argument("tasks", nargs="*")
    s.add_argument("--label", default="adhoc")
    s.add_argument("--ref", default="HEAD")
    s.add_argument("--repeat", type=int, default=1)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--keep", action="store_true", help="keep the worktrees for inspection")
    s.set_defaults(fn=cmd_golden)
    s = sub.add_parser("d1")
    s.add_argument("action", choices=["init", "push"])
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_d1)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

"""`python -m kb_distillery.autofix nightly|gate`.

    nightly [--kb-root DIR] [--dry-run]   the last nightly run -> one issue per failure signature (+ the fixer)
    gate [--cwd DIR] [--base REF]         print the diff gate's verdict for a branch
"""
import argparse
import datetime
import json
import os
import sys

from kb_distillery.autofix import detect, gate, issue


def engine_root():
    from kb_distillery.config.kb import checkout_root, primary_root
    return primary_root() or checkout_root() or os.getcwd()


def state_path(root):
    return os.path.join(root, ".cache", "autofix", "state.json")


def load_state(root):
    try:
        with open(state_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(root, state):
    path = state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _log_tail():
    from kb_distillery.ops import notify
    from kb_distillery.ops.core import NIGHTLY_LOG
    return notify.log_tail(NIGHTLY_LOG, n=40)


def nightly(kb_root, dry_run=False, root=None, run_gh=issue.gh, fix=None, out=print):
    """Ticket every failure of the last run; hand the fixable ones to `fix(failure, number)` when given.
    Returns the list of (failure, issue number, outcome)."""
    root = root or engine_root()
    run = detect.last_run(kb_root)
    fails = detect.failures(run)
    if not fails:
        out(f"autofix: last run is {(run or {}).get('status', 'missing')}: nothing to do")
        return []
    tail = _log_tail()
    kb = os.path.basename(os.path.normpath(kb_root))
    state = load_state(root)
    done = []
    for f in fails:
        number, how = issue.open_or_reuse(f, run, root, log_tail=tail, kb=kb, run_gh=run_gh, dry_run=dry_run)
        route = "fixer" if f.fixable else "ticket only"
        out(f"autofix: {f.signature} {f.step}: issue {('#%s' % number) if number else '-'} ({how}); {route}: {f.why}")
        if not dry_run:
            entry = state.setdefault(f.signature, {"first": run.get("started"), "step": f.step})
            entry.update(last=run.get("started"), issue=number or entry.get("issue"), fixable=f.fixable)
        outcome = how
        if f.fixable and fix is not None:
            outcome = fix(f, number or (state.get(f.signature) or {}).get("issue"), state)
            out(f"autofix: {f.signature} fixer: {outcome}")
        done.append((f, number, outcome))
    if not dry_run:
        save_state(root, state)
    return done


def main(argv=None):
    p = argparse.ArgumentParser(prog="autofix", description="nightly failure tickets and fixes")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nightly", help="ticket (and fix) the failures of the last nightly run")
    n.add_argument("--kb-root", default=None, help="the kb whose meta/.ops/runs.jsonl to read (default: $KB's root)")
    n.add_argument("--dry-run", action="store_true", help="print what would happen: no GitHub writes, no LLM calls")
    g = sub.add_parser("gate", help="print the diff gate's verdict")
    g.add_argument("--cwd", default=".")
    g.add_argument("--base", default="origin/main")
    args = p.parse_args(argv)
    if args.cmd == "gate":
        why = gate.measure(args.cwd, args.base)
        print("dramatic: hold for the owner\n  " + "\n  ".join(why) if why else "small: may merge itself")
        return 0
    from kb_distillery.config.paths import vault_root
    kb_root = args.kb_root or vault_root()
    print(f"=== autofix {datetime.datetime.now().isoformat(timespec='seconds')} kb={kb_root}")
    nightly(kb_root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

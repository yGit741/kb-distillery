"""CLI for distill propose / revise / apply / abort / status."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .apply import apply_proposal
from .brief import render_distilled_page, render_summary
from .graph import build_plan
from .paths import (
    ROOT,
    distilled_wiki_rel,
    resolve_think_path,
    think_abs,
    save_session_by_think,
    session_dir_for_think,
    think_basename,
)
from .plan import validate_plan
from .session import abort, begin_apply, close_apply, rollback, run_lint
from .source import read_summary, read_think_body, read_think_body_from_file


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_plan(think_rel):
    plan_path = os.path.join(session_dir_for_think(think_rel), "plan.json")
    if not os.path.isfile(plan_path):
        raise FileNotFoundError("run propose first")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    validate_plan(plan)
    return plan


def _write_plan(think_rel, plan):
    sdir = session_dir_for_think(think_rel)
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")


def _write_distilled(think_rel, plan, summary, applied=False):
    distilled_rel = distilled_wiki_rel(think_rel)
    page = render_distilled_page(plan, think_rel, summary, applied=applied)
    with open(os.path.join(ROOT, distilled_rel), "w", encoding="utf-8") as f:
        f.write(page)
    return distilled_rel


def cmd_propose(think_arg, from_path=None):
    think_rel = resolve_think_path(think_arg)
    think_full = think_abs(think_rel)
    if not os.path.isfile(think_full):
        print(f"missing {think_rel}")
        return 1

    if from_path:
        body = read_think_body_from_file(from_path)
    else:
        body = read_think_body(think_rel)

    if not body.strip() and not from_path:
        print(f"{think_rel}: empty — write in think/ first, or use --from")
        return 1

    plan = build_plan(think_rel, body)
    plan["distilled_at"] = _now()
    validate_plan(plan)
    _write_plan(think_rel, plan)

    summary = render_summary(plan, body)
    distilled_rel = _write_distilled(think_rel, plan, summary)

    save_session_by_think(think_rel, {
        "think_path": think_rel,
        "think_slug": think_basename(think_rel),
        "distilled_path": distilled_rel,
        "status": "open",
        "mode": "propose",
        "opened_at": _now(),
    })

    print(
        f"proposed distill for {think_rel}: {len(plan['proposals'])} edits → {distilled_rel}"
    )
    return 0


def cmd_revise(think_arg):
    think_rel = resolve_think_path(think_arg)
    try:
        plan = _load_plan(think_rel)
    except FileNotFoundError:
        print("run propose first")
        return 1

    body = read_think_body(think_rel)
    distilled_rel = distilled_wiki_rel(think_rel)
    prior_summary = read_summary(distilled_rel)

    new_plan = build_plan(think_rel, body)
    new_plan["distilled_at"] = plan.get("distilled_at") or _now()
    validate_plan(new_plan)
    _write_plan(think_rel, new_plan)

    summary = render_summary(new_plan, body, prior_summary=prior_summary)
    _write_distilled(think_rel, new_plan, summary)
    print(f"revised distill for {think_rel}: {len(new_plan['proposals'])} edits")
    return 0


def cmd_apply(think_arg, only=None, cleanup=False):
    think_rel = resolve_think_path(think_arg)
    try:
        plan = _load_plan(think_rel)
    except FileNotFoundError:
        print("run propose first")
        return 1

    indices = None
    if only:
        indices = {int(x.strip()) for x in only.split(",") if x.strip()}

    proposals = plan.get("proposals", [])
    to_apply = [p for i, p in enumerate(proposals, 1) if indices is None or i in indices]
    if not to_apply:
        print("nothing to apply")
        return 1

    sub_plan = dict(plan)
    sub_plan["proposals"] = to_apply
    begin_apply(think_rel, sub_plan)

    try:
        for p in to_apply:
            target = p["target"]
            if not os.path.isfile(os.path.join(ROOT, target)):
                print(f"skip missing target {target}")
                continue
            apply_proposal(p)
            print(f"applied {p['action']} → {target}")

        if run_lint() != 0:
            rollback(think_rel, "rolled_back")
            print("lint failed — rolled back")
            return 1

        distilled_rel = distilled_wiki_rel(think_rel)
        if cleanup:
            distilled_full = os.path.join(ROOT, distilled_rel)
            if os.path.isfile(distilled_full):
                os.remove(distilled_full)
                print(f"removed {distilled_rel}")
        else:
            summary = read_summary(distilled_rel) or render_summary(plan, "")
            _write_distilled(think_rel, plan, summary, applied=True)

        close_apply(think_rel, success=True)
        _append_log(think_rel, len(to_apply), cleanup=cleanup)
        print(f"applied {len(to_apply)} proposal(s) for {think_rel}")
        try:
            from kb.search.semfind import bundle_from_distill
            bundle_from_distill(think_rel, sub_plan)
        except Exception as e:
            print(f"semfind bundle skipped: {e}", file=sys.stderr)
        return 0
    except Exception as e:
        rollback(think_rel, "rolled_back")
        print(f"error: {e} — rolled back")
        return 1


def _append_log(think_rel, n, cleanup=False):
    from kb.core import log as kblog
    tag = " (cleanup)" if cleanup else ""
    kblog.append(ROOT, "distill", f"{think_rel}{tag} — {n} proposal(s) applied", when=_now())


def cmd_status(_args):
    from .paths import DISTILL_ROOT
    if not os.path.isdir(DISTILL_ROOT):
        print("no distill sessions")
        return 0
    for sid in sorted(os.listdir(DISTILL_ROOT)):
        sp = os.path.join(DISTILL_ROOT, sid, "session.json")
        if os.path.isfile(sp):
            with open(sp, encoding="utf-8") as f:
                s = json.load(f)
            print(
                f"{sid}: {s.get('think_path', s.get('think_slug'))} "
                f"status={s.get('status')} mode={s.get('mode', 'propose')}"
            )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.distill")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("propose")
    sp.add_argument("think", help="think/my-file or my-file")
    sp.add_argument("--from", dest="from_path", help="bootstrap body from another file")

    sr = sub.add_parser("revise")
    sr.add_argument("think")

    sa = sub.add_parser("apply")
    sa.add_argument("think")
    sa.add_argument("--only", help="comma-separated proposal indices")
    sa.add_argument(
        "--cleanup",
        action="store_true",
        help="delete distilled-think page after successful apply",
    )

    sb = sub.add_parser("abort")
    sb.add_argument("think")

    sub.add_parser("status")

    args = p.parse_args(argv)
    if args.cmd == "propose":
        return cmd_propose(args.think, getattr(args, "from_path", None))
    if args.cmd == "revise":
        return cmd_revise(args.think)
    if args.cmd == "apply":
        return cmd_apply(args.think, getattr(args, "only", None), getattr(args, "cleanup", False))
    if args.cmd == "abort":
        return abort(resolve_think_path(args.think))
    if args.cmd == "status":
        return cmd_status(args)
    return 1

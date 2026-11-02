"""`distill send <note> --to a,b` (was `kbd distill`): send a think note into the chosen knowledge bases (docs: think.md).

Each kb gets `wiki/distilled-think-<note>.md` citing `think:<note>.md`, committed there as `kb(distill)`; the
note's provenance sidecar in the think space lists where it went (kb_distillery.distill.fanout). No LLM call unless
`--summarize` is given; then it goes through `kb_distillery.llm` on `--backend subscription|api|batch`
(default `$KB_LLM_BACKEND`, then subscription).

This is separate from `python -m kb_distillery.distill` (propose / revise / apply), which proposes edits inside one kb.
"""
from __future__ import annotations

import argparse
import sys

from kb_distillery.distill import fanout


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="distill send", description="Send a think note into one or more knowledge bases.")
    p.add_argument("note", help="think note: name, name.md, sub/name.md or think:name.md")
    p.add_argument("--to", required=True, help="comma-separated kb ids or paths, e.g. thesis,demo")
    p.add_argument("--summarize", action="store_true", help="write the page summary with an LLM (default: first paragraph)")
    p.add_argument("--backend", choices=("subscription", "api", "batch"),
                   help="LLM backend for --summarize (default: $KB_LLM_BACKEND, then subscription)")
    p.add_argument("--think", help="think folder (default: <kbs dir>/think)")
    p.add_argument("--no-commit", action="store_true", help="write the pages but do not commit them in the kbs")
    p.add_argument("--no-push", action="store_true", help="commit but do not push")
    return p


def main(argv=None, summarize=None) -> int:
    """`summarize` lets tests inject a fake; the CLI builds one over kb_distillery.llm only for --summarize."""
    args = build_parser().parse_args(argv)
    if args.backend and not args.summarize:
        print("kbd distill: --backend only matters with --summarize", file=sys.stderr)
        return 2
    if args.summarize and summarize is None:
        summarize = fanout.llm_summarizer(args.backend)
    refs = [r.strip() for r in args.to.split(",") if r.strip()]
    try:
        outcomes = fanout.distill_note(args.note, refs, think_root=args.think, summarize=summarize)
    except fanout.DistillError as e:
        print(f"kbd distill: {e}", file=sys.stderr)
        return 1
    rc = 0
    for o in outcomes:
        print(f"{o.kb}: {o.page} ({'written' if o.written else 'already there'})")
        if args.no_commit:
            continue
        try:
            from kb_distillery.ops import core            # lazy: importing ops needs the process's kb settings
            core.commit_op("distill", o.page.rsplit("/", 1)[-1][:-3], f"{o.page.rsplit('/', 1)[-1][:-3]} from think",
                           paths=[o.page], root=o.root, push=not args.no_push)
        except Exception as e:                                   # the page stays; the nightly sync commits it
            print(f"{o.kb}: not committed — {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

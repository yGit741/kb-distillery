#!/usr/bin/env python3
"""Nightly sync of the knowledge lane — delegates to src/kb_distillery/ops (ops.core.sync).

Each knowledge operation already commits itself (kb(...) on main). The nightly run
commits human think/ edits as kb(think), commits any labelled leftovers when no
session is open, then pushes main with its snapshot tags. Tooling ships via src/kb_distillery/git/ship.py.
Shared git helpers (run_git, changed_paths, has_open_sessions) live here.

    python3 -m kb_distillery.ops.daily_sync
    python3 -m kb_distillery.ops.daily_sync --dry-run
    python3 -m kb_distillery.ops.daily_sync --no-push
"""
import argparse
import datetime
import os
import subprocess
import sys

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.git.guard import _open_distill_sessions, _open_ingest_sessions
from kb_distillery.vault.schema import KNOWLEDGE_PATHS, lane_of

STAGE_PATHS = KNOWLEDGE_PATHS


def has_open_sessions(root=ROOT):
    """Return (open_ingest_sessions, open_distill_sessions)."""
    return _open_ingest_sessions(root), _open_distill_sessions(root)


def commit_message_from_log(log_path=None):
    """The newest untargeted entry of wiki/log.md as `<op> | <title> (date)`, or a dated fallback."""
    from kb_distillery.vault import log as kblog
    path = log_path or os.path.join(ROOT, kblog.LOG_REL)
    if not os.path.isfile(path):
        return f"chore: daily sync {datetime.date.today().isoformat()}"
    with open(path, encoding="utf-8") as f:
        last = kblog.latest(f.read(), skip_targeted=True)
    if last:
        date, title = last
        return f"{title} ({date})"
    return f"chore: daily sync {datetime.date.today().isoformat()}"


def existing_stage_paths(root=ROOT):
    return [p for p in STAGE_PATHS if os.path.exists(os.path.join(root, p))]


def changed_paths(root=ROOT):
    """Repo-relative paths with uncommitted changes (incl. untracked), by lane."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=root, capture_output=True, text=True, check=False,
    ).stdout
    lanes = {"knowledge": [], "tooling": [], "other": []}
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            i += 1  # rename/copy: next entry is the old path
        path = entry[3:]
        lanes[lane_of(path)].append(path)
    return lanes


def run_git(args, cwd=ROOT):
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def inbox_pickup(run=subprocess.run):
    """Flag `inbox-pickup` (off by default): import what the site's upload inbox holds, as new kbs on this Mac
    (`distill kb inbox pull`, a separate process: the entry-point layer is not ours to import). Never fails the sync."""
    from kb_distillery.config.flags import runtime
    if not runtime.effective("inbox-pickup"):
        return None
    try:
        proc = run([sys.executable, "-m", "kb_distillery.inbox", "pull"], cwd=ROOT, check=False, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"note: inbox pickup skipped — {e}")
        return None
    if proc.returncode:
        print(f"note: inbox pickup finished with exit {proc.returncode} (see the lines above)")
    return proc.returncode


def main(argv=None):
    p = argparse.ArgumentParser(description="Daily vault git sync")
    p.add_argument("--dry-run", action="store_true", help="print actions, no git write")
    p.add_argument("--no-push", action="store_true", help="commit but do not push")
    args = p.parse_args(argv)

    from kb_distillery.config.kb import KbConfigError, require_kb_root
    try:
        require_kb_root(ROOT, "the nightly sync")
    except KbConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Knowledge is committed one operation at a time by meta/ops; the nightly run
    # only commits human think/ edits and labelled leftovers, then pushes main + tags.
    from kb_distillery.ops import core as ops_core
    rc = ops_core.sync(push=not args.no_push, dry_run=args.dry_run)
    if not args.dry_run:
        inbox_pickup()
    return rc


if __name__ == "__main__":
    sys.exit(main())

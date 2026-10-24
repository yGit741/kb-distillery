#!/usr/bin/env python3
"""Nightly sync of the knowledge lane — delegates to backend/src/kb/ops (ops.core.sync).

Each knowledge operation already commits itself (kb(...) on main). The nightly run
commits human think/ edits as kb(think), commits any labelled leftovers when no
session is open, then pushes main with its snapshot tags. Tooling ships via backend/src/kb/git/ship.py.
Shared git helpers (run_git, changed_paths, has_open_sessions) live here.

    python3 -m kb.maintenance.daily_sync
    python3 -m kb.maintenance.daily_sync --dry-run
    python3 -m kb.maintenance.daily_sync --no-push
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb.git.guard import _open_distill_sessions, _open_ingest_sessions
from kb.core.schema import KNOWLEDGE_PATHS, lane_of

LOG_HEADING = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (.+)$")

STAGE_PATHS = KNOWLEDGE_PATHS


def has_open_sessions(root=ROOT):
    """Return (open_ingest_sessions, open_distill_sessions)."""
    return _open_ingest_sessions(root), _open_distill_sessions(root)


def commit_message_from_log(log_path=None):
    """Last ## [date] action | title line in meta/log.md, or dated fallback."""
    path = log_path or os.path.join(ROOT, "meta", "log.md")
    if not os.path.isfile(path):
        return f"chore: daily sync {datetime.date.today().isoformat()}"
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            m = LOG_HEADING.match(stripped)
            if m and "←" not in stripped:
                last = (m.group(1), m.group(2).strip())
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


def main(argv=None):
    p = argparse.ArgumentParser(description="Daily vault git sync")
    p.add_argument("--dry-run", action="store_true", help="print actions, no git write")
    p.add_argument("--no-push", action="store_true", help="commit but do not push")
    args = p.parse_args(argv)

    # Knowledge is committed one operation at a time by meta/ops; the nightly run
    # only commits human think/ edits and labelled leftovers, then pushes main + tags.
    from kb.ops import core as ops_core
    return ops_core.sync(push=not args.no_push, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

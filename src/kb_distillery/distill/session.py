"""Distill session lifecycle: propose, apply, abort, rollback."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .paths import (
    ROOT,
    distilled_wiki_rel,
    load_session_by_think,
    save_session_by_think,
    session_dir_for_think,
    think_basename,
)
from .plan import validate_plan


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _backup_path(think_rel, wiki_rel):
    return os.path.join(session_dir_for_think(think_rel), "backup", os.path.basename(wiki_rel))


def begin_apply(think_rel, plan):
    try:
        session = load_session_by_think(think_rel)
    except FileNotFoundError:
        session = None
    if session and session.get("status") == "open" and session.get("mode") == "apply":
        print(f"distill apply session already open for {think_rel}")
        return think_rel

    sdir = session_dir_for_think(think_rel)
    os.makedirs(os.path.join(sdir, "backup"), exist_ok=True)

    backup_files = []
    targets = {p["target"] for p in plan.get("proposals", [])}
    distilled = distilled_wiki_rel(think_rel)
    targets.add(distilled)

    for wiki_rel in sorted(targets):
        full = os.path.join(ROOT, wiki_rel)
        if os.path.isfile(full):
            dst = _backup_path(think_rel, wiki_rel)
            shutil.copy2(full, dst)
            backup_files.append(wiki_rel)

    session = {
        "think_path": think_rel,
        "think_slug": think_basename(think_rel),
        "distilled_path": distilled,
        "status": "open",
        "mode": "apply",
        "opened_at": _now(),
        "backup_files": backup_files,
        "modified_files": list(backup_files),
    }
    save_session_by_think(think_rel, session)
    print(f"distill apply session opened for {think_rel}")
    return think_rel


def rollback(think_rel, reason="aborted"):
    session = load_session_by_think(think_rel)
    for wiki_rel in session.get("backup_files", []):
        bak = _backup_path(think_rel, wiki_rel)
        dst = os.path.join(ROOT, wiki_rel)
        if os.path.isfile(bak):
            shutil.copy2(bak, dst)
        elif os.path.isfile(dst) and wiki_rel == session.get("distilled_path"):
            os.remove(dst)
    session["status"] = reason
    session["closed_at"] = _now()
    save_session_by_think(think_rel, session)
    print(f"distill session {think_rel} {reason}")


def abort(think_rel):
    try:
        session = load_session_by_think(think_rel)
    except FileNotFoundError:
        print(f"no session for {think_rel}")
        return 1
    if session.get("status") != "open":
        print(f"no open session for {think_rel}")
        return 1
    rollback(think_rel, "aborted")
    return 0


def close_apply(think_rel, success=True):
    session = load_session_by_think(think_rel)
    session["status"] = "applied" if success else "failed"
    session["closed_at"] = _now()
    session["mode"] = "apply"
    save_session_by_think(think_rel, session)


def run_lint():
    r = subprocess.run(
        [sys.executable, "-m", "kb_distillery.lint.lint"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
    return r.returncode

"""Build the Lifecycle tab snapshot: versions, history, snapshots, branches, guardrails (0 LLM).

Read-only: runs only read-only git commands and never touches the network.
"""
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb.git import commit_policy as cp
from kb.maintenance.daily_sync import changed_paths, has_open_sessions
from kb.ops import core as ops_core
from kb.ops.history import timeline
from kb.ops.migrate import _applied, pending_migrations
from kb.core.schema import GIT_POLICY_MODE, OPS_STRICT, SCHEMA_VERSION

ROOT = vault_root()
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.thesis-kb.daily-sync.plist")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout.strip()


def _github_url(root):
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(\.git)?$", url)
    return f"https://github.com/{m.group(1)}" if m else None


def _infra_branches(root):
    out = _git(root, "for-each-ref", "refs/heads/infra/", "refs/remotes/origin/infra/",
               "--format=%(refname:short)\x1f%(committerdate:iso-strict)\x1f%(contents:subject)")
    rows = []
    for line in out.splitlines():
        name, date, subject = (line.split("\x1f") + ["", ""])[:3]
        counts = _git(root, "rev-list", "--left-right", "--count", f"main...{name}").split()
        behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
        rows.append({"name": name, "date": date, "last": subject, "ahead": ahead, "behind": behind})
    return rows


def build_lifecycle_snapshot(root=ROOT, limit=150):
    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    version = cp.last_version(root, "main")
    rows = timeline(root, "main", limit=limit)
    lanes = changed_paths(root)
    ingest, distill = has_open_sessions(root)
    current = ops_core.current_session(root)
    unpushed = _git(root, "rev-list", "--count", "origin/main..main")

    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [r for r in rows if r["kind"] == "kb"
              and datetime.fromisoformat(r["date"]).astimezone(timezone.utc) >= since]
    ops_30d = Counter(r["op"] or r["scope"] for r in recent)

    return {
        "generated_at": _now(),
        "branch": branch,
        "head": _git(root, "rev-parse", "--short", "HEAD"),
        "version": cp.fmt_version(version) if version else None,
        "next_version": cp.fmt_version(cp.next_version(root, "main")),
        "github": _github_url(root),
        "schema": {
            "version": f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}",
            "applied": [r[0] for r in _applied(root).values()],
            "pending": pending_migrations(root),
        },
        "policy": {
            "hooks_installed": _git(root, "config", "core.hooksPath") == "tools/githooks",
            "mode": os.environ.get("KB_POLICY", GIT_POLICY_MODE),
            "strict": OPS_STRICT,
        },
        "working": {
            "lanes": {k: len(v) for k, v in lanes.items()},
            "knowledge": lanes["knowledge"][:40],
            "tooling": lanes["tooling"][:40],
            "think_dirty": sum(1 for p in lanes["knowledge"] if p.startswith("think/")),
            "sessions": {
                "ingest": [{"sha1": s.get("sha1"), "raw": s.get("raw")} for s in ingest],
                "distill": [{"think": s.get("think_path"), "mode": s.get("mode")} for s in distill],
                "researcher": ops_core.open_researcher_sessions(root),
                "ops": {k: current[k] for k in ("op", "target", "summary", "started")} if current else None,
            },
            "unpushed": int(unpushed) if unpushed.isdigit() else None,
        },
        "timeline": rows,
        "snapshots": ops_core.snapshots(root),
        "infra_branches": _infra_branches(root),
        "stats": {
            "kb_steps": sum(1 for r in rows if r["kind"] == "kb"),
            "pr_merges": sum(1 for r in rows if r["kind"] == "pr-merge"),
            "ops_30d": dict(ops_30d),
            "undone": sum(1 for r in rows if r["reverted_by"]),
        },
        "nightly": {"plist_installed": os.path.isfile(PLIST),
                    "log": "~/Library/Logs/thesis-kb-daily-sync.log",
                    **ops_core.nightly_status(root)},
        "stale_worktrees": [{"branch": r["branch"], "path": r["path"], "merged": r["merged"],
                             "ahead": r["ahead"], "dirty": len(r["dirty"])}
                            for r in _stale_worktrees(root) if not r["current"]],
    }


def _stale_worktrees(root):
    from kb.git.ship import stale_worktrees  # noqa: E402 — lazy, ship imports ops
    try:
        return stale_worktrees(root)
    except Exception:  # a broken worktree list must never break the tab
        return []

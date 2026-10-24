"""Git / ops hygiene checks — run by the nightly sync, emailed only when something is wrong.

    python3 -m kb.ops.hygiene            # pretty report (exit 1 when an error-level finding exists)
    python3 -m kb.ops.hygiene --json

Every check is isolated: one that raises or hangs becomes a finding instead of aborting
the run, and the whole run stops asking new checks once the time budget (~60 s) is spent.
`run()` returns a Report; `backend/src/kb/maintenance/notify.py` turns it into the email.
"""
import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import sys
import threading
import time

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb.maintenance.daily_sync import changed_paths, run_git
from kb.report import sanitize

BUDGET_SECONDS = 60.0
CHECK_CAP_SECONDS = 25.0          # no single check may eat the whole budget
SESSION_MAX_HOURS = 24
PR_MAX_DAYS = 7
SITE_MAX_HOURS = 24
PRUNE_FIX = "pixi run ship -- prune --apply"
SYNC_FIX = "pixi run daily-sync"
DEPLOY_FIX = "pixi run share -- deploy-main"


@dataclasses.dataclass
class Finding:
    severity: str            # "warn" | "error"
    kind: str                # short slug, e.g. stale-worktree
    detail: str
    fix: str = ""            # the exact command to run
    more: str = ""           # long tool output behind a one-line detail (not part of the fingerprint)

    def as_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Report:
    findings: list = dataclasses.field(default_factory=list)
    started: str = ""
    elapsed: float = 0.0
    checks: list = dataclasses.field(default_factory=list)   # names that ran to completion

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "warn"]

    def kinds(self):
        """Distinct kinds, worst first, in first-seen order — for the email subject."""
        seen = []
        for f in sorted(self.findings, key=lambda f: 0 if f.severity == "error" else 1):
            if f.kind not in seen:
                seen.append(f.kind)
        return seen

    def fingerprint(self):
        """Stable id of *what* is wrong (not when): same problems → same fingerprint."""
        body = "\n".join(sorted(f"{f.severity}|{f.kind}|{f.detail}" for f in self.findings))
        return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]

    def text(self):
        if not self.findings:
            return f"hygiene: clean ({len(self.checks)} checks, {self.elapsed:.1f}s)"
        lines = [f"hygiene: {len(self.errors)} error(s), {len(self.warnings)} warning(s) "
                 f"({len(self.checks)} checks, {self.elapsed:.1f}s)"]
        for f in sorted(self.findings, key=lambda f: (0 if f.severity == "error" else 1, f.kind)):
            lines.append(f"  [{f.severity.upper():5}] {f.kind}: {f.detail}")
            if f.fix:
                lines.append(f"          fix: {f.fix}")
        return "\n".join(lines)

    def as_dict(self):
        return {"started": self.started, "elapsed": round(self.elapsed, 2), "checks": list(self.checks),
                "errors": len(self.errors), "warnings": len(self.warnings),
                "fingerprint": self.fingerprint(), "findings": [f.as_dict() for f in self.findings]}


# ---------- helpers ----------

def _has_origin_main(root):
    return run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0


def _parse_when(value):
    """ISO timestamp (naive = local) → aware UTC datetime, or None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(datetime.timezone.utc)


def _hours_since(when, now):
    return (now - when).total_seconds() / 3600


# ---------- checks (each: (root, now) -> [Finding]) ----------

def check_worktrees(root, now):
    """(a) stale (merged / branch gone) and dirty worktrees under .claude/worktrees."""
    from kb.git.ship import _worktrees, stale_worktrees, worktree_dirty

    from .threads import fresh_branch
    out = []
    stale = {r["branch"]: r for r in stale_worktrees(root) if not r["current"]}
    for wt in _worktrees(root):
        path, branch = wt["path"], wt["branch"]
        if not os.path.isdir(path):
            out.append(Finding("warn", "missing-worktree", f"{path} is registered but gone from disk",
                               "git worktree prune"))
            continue
        if not branch:
            out.append(Finding("warn", "detached-worktree", f"{path} is on no branch (detached HEAD)",
                               f"pixi run ship -- start <feature> inside {path}, or remove it"))
            continue
        row = stale.get(branch)
        if row and row["merged"] and fresh_branch(root, branch) is not None:
            continue                      # just started: 0 ahead of main is not "merged", it is live work
        dirty = row["dirty"] if row else worktree_dirty(path)
        if row and row["merged"]:
            out.append(Finding("warn", "stale-worktree",
                               f"{branch} at {path} is merged into main"
                               + (f" but has {len(dirty)} uncommitted files" if dirty else ""),
                               PRUNE_FIX if not dirty else f"cd {path} && pixi run lanes   # then commit or discard, then {PRUNE_FIX}"))
        elif row:
            out.append(Finding("warn", "session-worktree",
                               f"{branch} at {path}: {row['ahead']} commits not on main"
                               + (f", {len(dirty)} uncommitted files" if dirty else ""),
                               f"cd {path} && pixi run ship -- start <feature>   # or: pixi run ship -- prune --drop {branch}"))
        elif dirty:
            out.append(Finding("warn", "dirty-worktree",
                               f"{branch} at {path}: {len(dirty)} uncommitted files ({', '.join(dirty[:3])}"
                               + (", …" if len(dirty) > 3 else "") + ")",
                               f'cd {path} && pixi run ship -- commit "fix(<component>): …"'))
    return out


def check_branches(root, now):
    """(b) merged infra/* and worktree-* branches (local or on origin) that prune would delete."""
    from kb.git.ship import prune_plan
    gone, _kept = prune_plan(root, fetch=_has_origin_main(root))
    return [Finding("warn", "unpruned-branch", f"{where} branch {b} is already in main", PRUNE_FIX)
            for where, b in gone if where != "worktree"]       # worktree-held ones are reported by (a)


def check_main_sync(root, now):
    """(c) local main ahead of (unpushed knowledge steps) or behind origin/main."""
    if not _has_origin_main(root):
        return []
    counts = run_git(["rev-list", "--left-right", "--count", "origin/main...main"], cwd=root).stdout.split()
    if len(counts) != 2:
        return []
    behind, ahead = int(counts[0]), int(counts[1])
    out = []
    if ahead:
        out.append(Finding("error", "unpushed-steps", f"main is {ahead} commit(s) ahead of origin/main", SYNC_FIX))
    if behind:
        out.append(Finding("warn", "behind-origin", f"main is {behind} commit(s) behind origin/main", SYNC_FIX))
    return out


def check_sessions(root, now, max_hours=SESSION_MAX_HOURS):
    """(d) ingest / distill / ops / researcher sessions open for more than a day."""
    from .threads import open_sessions
    return [Finding("warn", "stale-session", f"{x.get('detail') or x['label']} open for {x['age_hours'] / 24:.1f} days", x["fix"])
            for x in open_sessions(root, now) if (x["age_hours"] or 0) > max_hours]


def check_prs(root, now, max_days=PR_MAX_DAYS):
    """(e) open PRs older than a week (silently empty without gh / offline)."""
    from kb.git.ship import open_prs
    return [Finding("warn", "old-pr", f"PR #{p['number']} {p['branch']} open for {p['age']}: {p['title']}",
                    f"pixi run ship -- merge   # in its worktree; or: pixi run ship -- prune --drop {p['branch']}")
            for p in open_prs(root) if p.get("hours") is not None and p["hours"] >= max_days * 24]


def check_site(root, now, status_path=None, max_hours=SITE_MAX_HOURS):
    """(f) the private site: last deploy failed, or it serves a main older than a day."""
    from kb.share.contracts import StatusFile
    status = StatusFile(status_path or os.path.join(root, ".cache", "share", "status.json")).read()
    if not status:
        return []
    state = status.get("state")
    if state in ("failed", "refused-no-access"):
        error = status.get("error") or "?"
        return [Finding("error", "deploy-failed", f"last deploy {state} ({status.get('at')}): {sanitize.summarize_error(error)}",
                        DEPLOY_FIX, more=sanitize.clean_block(error, root))]
    if state != "deployed" or not status.get("sha"):
        return []
    sha, head = status["sha"], run_git(["rev-parse", "main"], cwd=root).stdout.strip()
    if sha == head:
        return []
    when = _parse_when(status.get("at"))
    if run_git(["merge-base", "--is-ancestor", sha, "main"], cwd=root).returncode != 0:
        return [Finding("warn", "site-stale", f"site serves {sha[:9]}, which is not on main", DEPLOY_FIX)]
    if when and _hours_since(when, now) < max_hours:
        return []
    behind = run_git(["rev-list", "--count", f"{sha}..main"], cwd=root).stdout.strip() or "?"
    return [Finding("warn", "site-stale", f"site serves {sha[:9]}, {behind} commit(s) behind main (deployed {status.get('at')})",
                    DEPLOY_FIX)]


def check_snapshots(root, now):
    """(g) public snapshot Workers without a reachable manifest (skipped offline / without credentials)."""
    from kb.share import cf_api, snapshots
    try:
        plan = snapshots.prune_plan()
    except (cf_api.CloudflareError, OSError):
        return []
    return [Finding("warn", "orphan-snapshot", f"{name} has no reachable manifest", "pixi run share -- prune --apply")
            for name in plan.get("orphans", [])]


def check_other_lane(root, now, limit=8):
    """(h) files that belong to no lane — never committed, never cleaned up."""
    other = changed_paths(root)["other"]
    if not other:
        return []
    shown = ", ".join(other[:limit]) + (f", … ({len(other)} total)" if len(other) > limit else "")
    return [Finding("warn", "other-lane", f"{len(other)} file(s) outside every lane: {shown}",
                    "pixi run lanes   # then gitignore, move or delete them")]


def check_nightly(root, now):
    """(i) the launchd job itself."""
    from . import core
    st = core.nightly_status(root)
    if st["installed"] and st["loaded"]:
        return []
    return [Finding("warn", "nightly-not-installed", f"nightly sync {st['summary']}", st["hint"] or "pixi run install-sync")]


CHECKS = [
    ("worktrees", check_worktrees),
    ("branches", check_branches),
    ("main-sync", check_main_sync),
    ("sessions", check_sessions),
    ("prs", check_prs),
    ("site", check_site),
    ("snapshots", check_snapshots),
    ("other-lane", check_other_lane),
    ("nightly", check_nightly),
]


# ---------- runner ----------

def tidy(finding, root):
    """One readable line per finding: no ANSI, vault-relative paths, multi-line output moved to `more`."""
    detail = sanitize.short_path(sanitize.strip_ansi(finding.detail), root)
    if "\n" in detail.strip():
        finding.more = finding.more or sanitize.clean_block(detail, root)
        detail = sanitize.summarize_error(detail)
    finding.detail = detail.strip()
    finding.fix = sanitize.short_path(finding.fix, root)
    return finding


def _run_isolated(name, fn, root, now, timeout):
    """Run one check in a daemon thread; (findings, status) with status ok | timeout | error."""
    box = {}

    def target():
        try:
            box["result"] = list(fn(root, now))
        except Exception as e:  # noqa: BLE001 — one broken check must not hide the others
            box["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=target, name=f"hygiene-{name}", daemon=True)
    t.start()
    t.join(max(timeout, 0.0))
    if t.is_alive():
        return [Finding("warn", "check-timeout", f"check {name} timed out after {timeout:.0f}s")], "timeout"
    if "error" in box:
        return [Finding("warn", "check-error", f"check {name} failed: {box['error']}")], "error"
    return box.get("result", []), "ok"


def run(root=ROOT, budget=BUDGET_SECONDS, checks=None, now=None, check_cap=CHECK_CAP_SECONDS):
    """Run every check within `budget` seconds; never raises."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = Report(started=now.isoformat(timespec="seconds"))
    t0 = time.monotonic()
    for name, fn in (checks if checks is not None else CHECKS):
        remaining = budget - (time.monotonic() - t0)
        if remaining <= 0:
            report.findings.append(Finding("warn", "check-skipped", f"check {name} skipped: time budget of {budget:.0f}s spent"))
            continue
        findings, status = _run_isolated(name, fn, root, now, min(remaining, check_cap))
        report.findings.extend(tidy(f, root) for f in findings)
        if status == "ok":
            report.checks.append(name)
    report.elapsed = time.monotonic() - t0
    return report


def main(argv=None):
    p = argparse.ArgumentParser(prog="hygiene", description="git / ops hygiene report")
    p.add_argument("--json", action="store_true")
    p.add_argument("--budget", type=float, default=BUDGET_SECONDS, help="seconds (default 60)")
    args = p.parse_args(argv)
    report = run(ROOT, budget=args.budget)
    print(json.dumps(report.as_dict(), indent=2) if args.json else report.text())
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

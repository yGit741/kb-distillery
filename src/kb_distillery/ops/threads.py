"""Open work threads — every unfinished line of work, one entry each (0 LLM, read-only).

A thread joins what belongs together: an open PR, its infra/* branch (local and on origin) and the
worktree that holds it; an open ingest / distill / ops / researcher session; unpushed knowledge
steps on main; uncommitted files in the primary checkout. Each thread carries its age, its last
activity and the one command that moves it forward. Used by the nightly report and the Ops tab.

    python3 -m kb_distillery.ops.threads          # one line per thread
    python3 -m kb_distillery.ops.threads --json
"""
import argparse
import dataclasses
import datetime
import json
import os
import re
import subprocess
import sys

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.ops.daily_sync import changed_paths, has_open_sessions, run_git

STALE_BRANCH_DAYS = 3        # an infra branch with no PR and no commit for this long is stale
STALE_PR_DAYS = 7
SESSION_MAX_HOURS = 24
PRUNE_FIX = "pixi run ship -- prune --apply"
STATE_RANK = {"blocked": 0, "stale": 1, "active": 2}


@dataclasses.dataclass
class Thread:
    id: str
    kind: str                 # pr | branch | worktree | merged | session | unpushed | behind | uncommitted | stray
    title: str
    state: str                # active | stale | blocked
    status: str               # ok | warn | error  (report colour)
    next: str = ""            # one command
    age_hours: float = None
    last_activity: str = ""   # ISO timestamp
    pieces: dict = dataclasses.field(default_factory=dict)
    notes: list = dataclasses.field(default_factory=list)
    link: str = ""
    branch: str = ""
    path: str = ""            # vault-relative worktree / session path

    def as_dict(self):
        return dataclasses.asdict(self)


# ---------- helpers ----------

def _git(root, *args):
    return run_git(list(args), cwd=root).stdout.strip()


def _parse(value):
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.astimezone()).astimezone(datetime.timezone.utc)


def _hours(when, now):
    return round((now - when).total_seconds() / 3600, 1) if when else None


def age_label(hours):
    if hours is None:
        return "?"
    if hours < 1:
        return f"{max(int(hours * 60), 1)}m"
    if hours < 48:
        return f"{int(hours)}h"
    return f"{int(hours // 24)}d"


def rel(path, root):
    try:
        r = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    except ValueError:
        return path
    return path if r.startswith("..") else r


def github_url(root):
    m = re.search(r"github\.com[:/](.+?)(\.git)?$", _git(root, "remote", "get-url", "origin"))
    return f"https://github.com/{m.group(1)}" if m else ""


def _base(root):
    return "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"


def infra_branches(root):
    """{name: {local, remote, ahead, last}} for infra/* and worktree-* branches, local or on origin."""
    out = _git(root, "for-each-ref", "refs/heads/infra/", "refs/heads/worktree-", "refs/remotes/origin/infra/",
               "--format=%(refname)\x1f%(committerdate:iso-strict)")
    base, rows = _base(root), {}
    for line in out.splitlines():
        ref, date = (line.split("\x1f") + [""])[:2]
        remote = ref.startswith("refs/remotes/origin/")
        name = ref[len("refs/remotes/origin/"):] if remote else ref[len("refs/heads/"):]
        row = rows.setdefault(name, {"local": False, "remote": False, "ahead": 0, "last": ""})
        row["remote" if remote else "local"] = True
        short = f"origin/{name}" if remote else name
        ahead = _git(root, "rev-list", "--count", f"{base}..{short}")
        row["ahead"] = max(row["ahead"], int(ahead) if ahead.isdigit() else 0)
        row["last"] = max(row["last"], date)
    return rows


def fresh_branch(root, name):
    """Creation time (ISO) of a local branch that has never had a commit of its own, else None —
    a just-started branch looks "merged" (0 ahead of main) but is live work."""
    out = _git(root, "log", "-g", "--date=iso-strict", "--format=%gs\x1f%gd", "-n", "2", f"refs/heads/{name}")
    lines = out.splitlines()
    if len(lines) != 1 or not lines[0].startswith("branch: Created"):
        return None
    m = re.search(r"@\{(.+)\}$", lines[0].split("\x1f", 1)[-1])
    return m.group(1) if m else ""


def _session_age(session, path, now):
    for key in ("opened_at", "started", "started_at", "created_at", "at"):
        when = _parse(session.get(key)) if isinstance(session, dict) else None
        if when:
            return _hours(when, now), when
    try:
        when = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
    except OSError:
        return 0.0, None
    return _hours(when, now), when


def open_sessions(root, now):
    """Every open ingest / distill / ops / researcher session as
    [{kind, id, label, detail?, age_hours, started, path, fix}] — shared with hygiene.check_sessions."""
    from kb_distillery.vault.schema import OPS_DIR

    from . import core
    out = []
    ingest, distill = has_open_sessions(root)
    for s in ingest:
        sid = s.get("sha1", "?")
        path = os.path.join(root, "meta", ".ingest", sid, "session.json")
        age, when = _session_age(s, path, now)
        out.append({"kind": "ingest", "id": sid, "label": f"ingest {s.get('raw', sid)}",
                    "detail": f"ingest {sid} ({s.get('raw', '?')})", "age_hours": age,
                    "started": when.isoformat() if when else "", "path": rel(path, root),
                    "fix": f"python3 -m kb_distillery.ingest finalize {sid}   # or: python3 -m kb_distillery.ingest abort {sid}"})
    for s in distill:
        sid = s.get("think_slug") or os.path.basename(s.get("think_path", "?"))
        path = os.path.join(root, "meta", ".distill", str(sid), "session.json")
        age, when = _session_age(s, path, now)
        out.append({"kind": "distill", "id": str(sid), "label": f"distill {s.get('think_path', sid)}", "age_hours": age,
                    "started": when.isoformat() if when else "", "path": rel(path, root),
                    "fix": f"python3 -m kb_distillery.distill apply {s.get('think_path', '<think-file>')}   # or: abort"})
    s = core.current_session(root)
    if s:
        path = os.path.join(root, OPS_DIR, "current.json")
        age, when = _session_age(s, path, now)
        out.append({"kind": "ops", "id": f"{s.get('op')}-{s.get('target')}", "label": f"ops {s.get('op')} {s.get('target')}",
                    "age_hours": age, "started": when.isoformat() if when else "", "path": rel(path, root),
                    "fix": "pixi run ops -- commit   # or: pixi run ops -- abort"})
    for slug in core.open_researcher_sessions(root):
        path = os.path.join(root, "meta", ".researcher", slug, "session.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        age, when = _session_age(data, path, now)
        out.append({"kind": "researcher", "id": slug, "label": f"researcher {slug}", "age_hours": age,
                    "started": when.isoformat() if when else "", "path": rel(path, root),
                    "fix": f"python3 -m kb_distillery.ingest index-researcher finalize {slug}   # or: index-researcher abort {slug}"})
    return out


# ---------- collectors ----------

def _branch_threads(root, now, prs=None):
    from kb_distillery.git import ship
    gh = github_url(root)
    prs = {p["branch"]: p for p in (ship.open_prs(root) if prs is None else prs)}
    branches = infra_branches(root)
    worktrees = {wt["branch"]: wt for wt in ship._worktrees(root) if wt.get("branch")}
    here = os.path.realpath(root)
    out = []
    for wt in ship._worktrees(root):
        if not wt.get("branch"):
            path = rel(wt["path"], root)
            out.append(Thread(f"wt:{path}", "worktree", f"detached worktree {path}", "blocked", "warn",
                              f"cd {path} && pixi run ship -- start <feature>   # or remove it", path=path,
                              notes=[] if os.path.isdir(wt["path"]) else ["registered but gone from disk — git worktree prune"]))
    for name in sorted(set(branches) | set(prs) | set(worktrees)):
        if name == "main":
            continue
        b = branches.get(name, {"local": False, "remote": False, "ahead": 0, "last": ""})
        pr, wt = prs.get(name), worktrees.get(name)
        path = rel(wt["path"], root) if wt else ""
        dirty = ship.worktree_dirty(wt["path"]) if wt else []
        last = _parse(b["last"])
        pieces = {"branch": name}
        if pr:
            pieces["pr"] = f"#{pr['number']}"
        if path:
            pieces["worktree"] = path
        if dirty:
            pieces["dirty"] = len(dirty)
        if b["ahead"]:
            pieces["ahead"] = b["ahead"]
        where = [w for w, on in (("local", b["local"]), ("origin", b["remote"])) if on]
        if where:
            pieces["on"] = "+".join(where)
        cd = f"cd {path} && " if path else ""
        notes = []
        if dirty:
            notes.append(f"{len(dirty)} uncommitted file(s): {', '.join(dirty[:3])}" + (", …" if len(dirty) > 3 else ""))
        if pr:
            hours = pr.get("hours")
            stale = hours is not None and hours >= STALE_PR_DAYS * 24
            t = Thread(f"pr:{pr['number']}", "pr", f"PR #{pr['number']} {pr.get('title') or name}",
                       "stale" if stale else "active", "warn" if stale else "ok",
                       f'{cd}pixi run ship -- merge   # held? the user runs: ship approve N — or: pixi run ship -- prune --drop {name}',
                       age_hours=hours, link=f"{gh}/pull/{pr['number']}" if gh else "")
        elif b["ahead"] == 0 and b["local"] and fresh_branch(root, name) is not None:
            created = _parse(fresh_branch(root, name))
            last = created or last
            t = Thread(f"branch:{name}", "branch", f"{name} — started, nothing committed yet", "active", "ok",
                       f'{cd}pixi run ship -- commit "feat(<component>): …"   # or: pixi run ship -- prune --drop {name}')
            b = dict(b, last=created.isoformat() if created else b["last"])
        elif b["ahead"] == 0 and (b["local"] or b["remote"] or wt):
            t = Thread(f"merged:{name}", "merged", f"{name} is merged — leftover " + ("worktree" if wt else "branch"),
                       "stale", "warn",
                       f"{cd}pixi run lanes   # commit or discard, then {PRUNE_FIX}" if dirty else PRUNE_FIX)
        elif name.startswith("worktree-"):
            t = Thread(f"session:{name}", "worktree", f"session branch {name} never became a PR", "stale", "warn",
                       f"{cd}pixi run ship -- start <feature>   # or: pixi run ship -- prune --drop {name}")
        else:
            hours = _hours(last, now)
            stale = hours is not None and hours >= STALE_BRANCH_DAYS * 24
            t = Thread(f"branch:{name}", "branch", f"{name} — {b['ahead']} commit(s), no PR yet",
                       "stale" if stale else "active", "warn" if stale else "ok",
                       f"{cd}pixi run ship -- pr   # or: pixi run ship -- prune --drop {name}")
        if t.age_hours is None:
            t.age_hours = _hours(last, now)
        if wt and os.path.realpath(wt["path"]) == here:
            notes.append("this checkout")
        t.last_activity, t.pieces, t.notes, t.branch, t.path = b["last"], pieces, notes, name, path
        out.append(t)
    return out


def _session_threads(root, now):
    out = []
    for s in open_sessions(root, now):
        stale = (s["age_hours"] or 0) > SESSION_MAX_HOURS
        out.append(Thread(f"{s['kind']}:{s['id']}", "session", s["label"], "stale" if stale else "active",
                          "warn" if stale else "ok", s["fix"], age_hours=s["age_hours"], last_activity=s["started"],
                          pieces={"session": s["kind"]}, path=s["path"]))
    return out


def _main_threads(root, now):
    out = []
    if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode != 0:
        return out
    counts = _git(root, "rev-list", "--left-right", "--count", "origin/main...main").split()
    behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    if ahead:
        last = _parse(_git(root, "log", "-1", "--format=%cI", "origin/main..main"))
        first = _parse(_git(root, "log", "--reverse", "--format=%cI", "origin/main..main").splitlines()[0]) if ahead else None
        out.append(Thread("main:unpushed", "unpushed", f"main has {ahead} unpushed step(s)", "blocked", "error",
                          "pixi run daily-sync", age_hours=_hours(first, now),
                          last_activity=last.isoformat() if last else "", pieces={"ahead": ahead}, branch="main"))
    if behind:
        oldest = (_git(root, "log", "--reverse", "--format=%cI", "main..origin/main").splitlines() or [""])[0]
        out.append(Thread("main:behind", "behind", f"main is {behind} commit(s) behind origin", "stale", "warn",
                          "pixi run daily-sync", age_hours=_hours(_parse(oldest), now),
                          pieces={"behind": behind}, branch="main"))
    return out


def _dirty_threads(root, now):
    lanes = changed_paths(root)
    out = []
    knowledge = [p for p in lanes["knowledge"] if not p.startswith("think/")]
    think = [p for p in lanes["knowledge"] if p.startswith("think/")]

    def mtime(paths):
        times = [os.path.getmtime(os.path.join(root, p)) for p in paths if os.path.exists(os.path.join(root, p))]
        return datetime.datetime.fromtimestamp(min(times), datetime.timezone.utc) if times else None

    def sample(paths):
        return paths[:3] + ([f"… {len(paths) - 3} more"] if len(paths) > 3 else [])

    if knowledge:
        when = mtime(knowledge)
        out.append(Thread("dirty:knowledge", "uncommitted", f"{len(knowledge)} uncommitted knowledge file(s)", "stale",
                          "warn", 'pixi run ops -- record refine <target> "summary" <paths…>   # or wait for the nightly sync',
                          age_hours=_hours(when, now), pieces={"files": len(knowledge)}, notes=sample(knowledge)))
    if think:
        out.append(Thread("dirty:think", "uncommitted", f"{len(think)} think/ edit(s) — committed by the nightly sync",
                          "active", "ok", "", age_hours=_hours(mtime(think), now), pieces={"files": len(think)}))
    if lanes["tooling"] and _git(root, "symbolic-ref", "--short", "-q", "HEAD") == "main":
        out.append(Thread("dirty:tooling", "uncommitted", f"{len(lanes['tooling'])} tooling edit(s) on main", "stale", "warn",
                          "pixi run ship -- start <feature> --worktree   # tooling never commits on main",
                          age_hours=_hours(mtime(lanes["tooling"]), now), pieces={"files": len(lanes["tooling"])},
                          notes=sample(lanes["tooling"])))
    if lanes["other"]:
        out.append(Thread("dirty:other", "stray", f"{len(lanes['other'])} file(s) outside every lane", "stale", "warn",
                          "pixi run lanes   # then gitignore, move or delete them",
                          age_hours=_hours(mtime(lanes["other"]), now), pieces={"files": len(lanes["other"])},
                          notes=sample(lanes["other"])))
    return out


COLLECTORS = [("branches", _branch_threads), ("sessions", _session_threads), ("main", _main_threads),
              ("dirty", _dirty_threads)]


def sort_key(t):
    return (STATE_RANK.get(t.state, 9), -(t.age_hours or 0))


def collect(root=ROOT, now=None, collectors=None):
    """All open threads, blocked → stale → active, oldest first; a failing collector is skipped
    with a blocked "collector failed" thread instead of hiding the rest."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    out = []
    for name, fn in collectors if collectors is not None else COLLECTORS:
        try:
            out.extend(fn(root, now))
        except Exception as e:  # noqa: BLE001 — one broken source must not hide the others
            out.append(Thread(f"error:{name}", "error", f"could not list {name}: {type(e).__name__}: {e}",
                              "blocked", "warn"))
    return sorted(out, key=sort_key)


def main(argv=None):
    p = argparse.ArgumentParser(prog="threads", description="open work threads")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    threads = collect(ROOT)
    if args.json:
        print(json.dumps([t.as_dict() for t in threads], indent=2))
        return 0
    for t in threads:
        print(f"[{t.state:7}] {t.title}  ({age_label(t.age_hours)})" + (f"\n          → {t.next}" if t.next else ""))
    if not threads:
        print("no open threads")
    return 0


if __name__ == "__main__":
    sys.exit(main())

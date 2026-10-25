"""Path claims: say which paths an infra branch will touch, and warn when lanes overlap.

`ship start <f> --paths a/b,c/d` stores the claim in git config (`branch.infra/<f>.kbPaths`, shared by
all worktrees, like rounds' `kbRound`); `ship pr` writes `Claims: a/b, c/d` into the PR body and
`paths=` into the `claimed` event. At `start` and `pr` the claim is compared with every other lane:
open `infra/*` PRs (their `Claims:` line, else their changed files) and local worktrees (their diff vs
origin/main). Overlaps are printed as an OVERLAP block — a warning only, never a block: the user decides.
"""
import json
import os
import re
import subprocess

CLAIMS_RE = re.compile(r"^Claims:\s*(.+)$", re.M)


def _git(args, cwd):
    from kb.maintenance.daily_sync import run_git
    return run_git(args, cwd=cwd)


def norm(p):
    p = p.strip().strip("`").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def parse_paths(text):
    """'a/b, c/d' or 'a/b,c/d' → ['a/b', 'c/d'] (deduped, order kept)."""
    out = []
    for p in re.split(r"[,\s]+", text or ""):
        p = norm(p)
        if p and p not in out:
            out.append(p)
    return out


def _key(branch):
    return f"branch.{branch}.kbPaths"


def set_branch_claims(branch, paths, root):
    return _git(["config", _key(branch), ",".join(paths)], root).returncode == 0


def branch_claims(branch, root):
    return parse_paths(_git(["config", "--get", _key(branch)], root).stdout)


def claims_line(paths):
    return f"Claims: {', '.join(paths)}" if paths else ""


def claims_from_body(body):
    m = CLAIMS_RE.search(body or "")
    return parse_paths(m.group(1)) if m else []


def touched_dirs(files):
    """Parent directories of changed files (top-level files stay as they are)."""
    return sorted({os.path.dirname(f) or f for f in files})


def _covers(a, b):
    return a == b or b.startswith(a + "/")


def overlap(mine, theirs):
    """Overlapping paths (the more specific side of each pair): equal, or one is a dir prefix of the other."""
    hits = set()
    for a in map(norm, mine):
        for b in map(norm, theirs):
            if not a or not b:
                continue
            if _covers(a, b):
                hits.add(b)
            elif _covers(b, a):
                hits.add(a)
    return sorted(hits)


def _gh(args, root):
    exe = os.environ.get("GH_BIN", "gh")
    try:
        return subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess([exe, *args], 1, "", str(e))


def pr_lanes(root, notes):
    """Open infra/* PRs as [{branch, pr, title, paths, source}] — [] (and a note) when gh fails."""
    cp = _gh(["pr", "list", "--state", "open", "--json", "number,headRefName,title,body"], root)
    try:
        rows = json.loads(cp.stdout) if cp.returncode == 0 and cp.stdout.strip() else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        notes.append("open PRs not checked (gh unavailable)")
        return []
    out = []
    for r in (x for x in rows if isinstance(x, dict)):
        branch = r.get("headRefName", "")
        if not branch.startswith("infra/"):
            continue
        paths, source = claims_from_body(r.get("body", "")), "claims"
        if not paths:
            v = _gh(["pr", "view", str(r.get("number")), "--json", "files"], root)
            try:
                paths = [f["path"] for f in json.loads(v.stdout).get("files", [])] if v.returncode == 0 else []
            except (ValueError, AttributeError, KeyError, TypeError):
                paths = []
            source = "files"
        out.append({"branch": branch, "pr": r.get("number"), "title": r.get("title", ""),
                    "paths": paths, "source": source})
    return out


def worktree_lanes(root):
    """Local worktrees as [{branch, path, paths, claims}]: their diff vs origin/main plus any stored claim."""
    from kb.git import ship
    out = []
    for wt in ship._worktrees(root):
        b = wt.get("branch")
        if not b or not os.path.isdir(wt["path"]):
            continue
        try:
            files = ship.branch_files(wt["path"])
        except Exception:
            files = []
        out.append({"branch": b, "path": wt["path"], "paths": files, "claims": branch_claims(b, root)})
    return out


def find_overlaps(mine, branch, root):
    """[(lane, overlapping paths)] for every other lane, plus notes about what could not be checked."""
    notes, hits = [], []
    if not mine:
        return hits, notes
    for lane in pr_lanes(root, notes):
        if lane["branch"] == branch:
            continue
        ov = overlap(mine, lane["paths"])
        if ov:
            hits.append((lane, ov))
    seen = {lane["branch"] for lane, _ in hits}
    for lane in worktree_lanes(root):
        if lane["branch"] == branch or lane["branch"] in seen:
            continue
        ov = overlap(mine, lane["paths"] + lane["claims"])
        if ov:
            hits.append((lane, ov))
    return hits, notes


def warn(mine, branch, root):
    """Print an OVERLAP block when another lane touches the same paths. Never raises, never blocks."""
    try:
        hits, notes = find_overlaps(mine, branch, root)
    except Exception as e:
        print(f"note: overlap check skipped — {e}")
        return []
    for n in notes:
        print(f"note: {n}")
    if hits:
        print("OVERLAP — other lanes touch the same paths (warning only; the user decides):")
        for lane, ov in hits:
            who = f"PR #{lane['pr']} {lane['title']}" if lane.get("pr") else f"worktree {lane['path']}"
            shown = ", ".join(ov[:6]) + (f" (+{len(ov) - 6} more)" if len(ov) > 6 else "")
            print(f"  {lane['branch']}  {who}\n    {shown}")
    return hits


def cmd_claims(root):
    """One line per lane: branch, PR, where the paths come from, the paths."""
    notes = []
    rows = {}
    for lane in pr_lanes(root, notes):
        rows[lane["branch"]] = (f"#{lane['pr']}", lane["source"], lane["paths"])
    for lane in worktree_lanes(root):
        b = lane["branch"]
        if lane["claims"] and (b not in rows or rows[b][1] == "files"):
            rows[b] = (rows.get(b, ("-",))[0], "claims", lane["claims"])
        elif b not in rows and lane["paths"]:
            rows[b] = ("-", "diff", touched_dirs(lane["paths"]))
    for n in notes:
        print(f"note: {n}")
    if not rows:
        print("no claims")
        return 0
    for b, (pr, src, paths) in sorted(rows.items()):
        shown = ", ".join(paths[:5]) + (f" (+{len(paths) - 5})" if len(paths) > 5 else "")
        print(f"{b:<32} {pr:<5} {src:<6} {shown or '-'}")
    return 0

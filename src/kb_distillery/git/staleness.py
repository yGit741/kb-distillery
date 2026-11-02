"""Stale work: the one set of rules `ship status`, `ship prune --stale`, the nightly hygiene report
and the System tab's "stale work" tile all read.

    python3 -m kb_distillery.git.ship prune --stale            # dry run: what is stale and what --apply would do
    python3 -m kb_distillery.git.ship prune --stale --apply    # quarantine + remove the idle unmerged work

Rules (warn, never block — the user decides what goes):
  idle-branch        a local infra/* or worktree-* branch with no open PR and either commits main lacks
                     but none for BRANCH_IDLE_HOURS (48 h), or no commit of its own since it was
                     created more than 48 h ago (started, never used).
  missing-worktree   a registered worktree whose directory is gone from disk.
  detached-worktree  a worktree on no branch (detached HEAD) whose tip and directory are both 48 h old.
  idle-pr            an open PR with no activity for PR_IDLE_DAYS (3 d); activity = the newer of the PR's
                     `updatedAt` (every kb-event comment bumps it, so it stands in for `ship events N`
                     without one gh call per PR) and its branch tip commit. Listed only — never closed.

`--apply` saves each unmerged branch as a patch + bundle in `_quarantine/` before removing its worktree
(plain `git worktree remove`, which refuses untracked/modified files) and LOCAL branch; it never touches a
dirty worktree, the one it runs in, origin branches or PRs.
"""
import datetime
import os

from kb_distillery.ops.daily_sync import run_git

BRANCH_IDLE_HOURS = 48
PR_IDLE_DAYS = 3
STALE_PREFIXES = ("infra/", "worktree-")
KINDS = ("idle-branch", "missing-worktree", "detached-worktree", "idle-pr")
PRUNE_STALE_FIX = "pixi run ship -- prune --stale   # dry run; --apply quarantines + removes"


def _now(now):
    return now or datetime.datetime.now(datetime.timezone.utc)


def _base(root):
    return "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"


def tip_hours(root, ref, now=None):
    """Hours since `ref`'s tip commit (committer date), or None when the ref does not exist."""
    out = run_git(["log", "-1", "--format=%ct", ref, "--"], cwd=root).stdout.strip()
    if not out.isdigit():
        return None
    when = datetime.datetime.fromtimestamp(int(out), datetime.timezone.utc)
    return (_now(now) - when).total_seconds() / 3600


def created_hours(root, branch, now=None):
    """Hours since a never-committed branch was created (its only reflog entry), else None — a merged
    branch is 0 ahead too, but it has more history and is left to plain `ship prune`."""
    from kb_distillery.ops.threads import fresh_branch
    created = fresh_branch(root, branch)
    if not created:
        return None
    try:
        when = datetime.datetime.fromisoformat(created)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.astimezone()
    return (_now(now) - when).total_seconds() / 3600


def _ahead(root, base, ref):
    n = run_git(["rev-list", "--count", f"{base}..{ref}"], cwd=root).stdout.strip()
    return int(n) if n.isdigit() else 0


def _detached_head(path):
    return run_git(["rev-parse", "HEAD"], cwd=path).stdout.strip()


def scan(root, now=None, prs=None):
    """Every stale item as {kind, branch, path, hours, ahead, dirty, current, pr, detail} (read-only).

    `prs` is `ship.open_prs()` output (fetched when None; empty offline, so nothing is idle-pr then and
    every unmerged branch counts as PR-less — the dry run shows it before anything is removed)."""
    from kb_distillery.git import ship
    now = _now(now)
    prs = ship.open_prs(root) if prs is None else prs
    pr_by_branch = {p.get("branch"): p for p in prs}
    base = _base(root)
    here = os.path.realpath(root)
    items = []
    attached = {}
    for wt in ship._worktrees(root):
        path, branch = wt["path"], wt["branch"]
        current = os.path.realpath(path) == here
        if not os.path.isdir(path):
            items.append({"kind": "missing-worktree", "branch": branch, "path": path, "hours": None, "ahead": 0,
                          "dirty": [], "current": False, "pr": None,
                          "detail": f"{path} is registered but gone from disk"})
            continue
        if not branch:
            head = _detached_head(path)
            ahead = _ahead(root, base, head) if head else 0
            try:      # a just-created / mid-rebase worktree is not stale: age = newer of tip and dir mtime
                dir_hours = (now - datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
                             ).total_seconds() / 3600
            except OSError:
                dir_hours = 0.0
            tip = tip_hours(root, head, now) if head else None
            if min(h for h in (tip, dir_hours) if h is not None) < BRANCH_IDLE_HOURS:
                continue
            items.append({"kind": "detached-worktree", "branch": None, "path": path,
                          "hours": tip, "ahead": ahead,
                          "dirty": ship.worktree_dirty(path), "current": current, "pr": None,
                          "detail": f"{path} is on no branch (detached HEAD, {ahead} commits not on main)"})
            continue
        attached[branch] = {**wt, "current": current}
    local = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=root).stdout.split()
    for b in local:
        if not b.startswith(STALE_PREFIXES) or b in pr_by_branch:
            continue
        ahead = _ahead(root, base, b)
        if ahead:
            hours, what = tip_hours(root, b, now), f"{ahead} commits not on main, last commit"
        else:
            hours, what = created_hours(root, b, now), "started but never committed, created"
        if hours is None or hours < BRANCH_IDLE_HOURS:
            continue
        wt = attached.get(b)
        items.append({"kind": "idle-branch", "branch": b, "path": wt["path"] if wt else None, "hours": hours,
                      "ahead": ahead, "dirty": ship.worktree_dirty(wt["path"]) if wt else [],
                      "current": bool(wt and wt["current"]), "pr": None,
                      "detail": f"{b}: {what} {hours / 24:.1f} days ago, no open PR"
                                + (f" (worktree {wt['path']})" if wt else "")})
    for p in prs:
        b = p.get("branch") or ""
        candidates = [h for h in (p.get("updated_hours"),
                                  tip_hours(root, b, now) if b in local else tip_hours(root, f"origin/{b}", now))
                      if h is not None]
        if not candidates:
            continue
        hours = min(candidates)
        if hours < PR_IDLE_DAYS * 24:
            continue
        items.append({"kind": "idle-pr", "branch": b, "path": attached.get(b, {}).get("path"), "hours": hours,
                      "ahead": 0, "dirty": [], "current": False, "pr": p.get("number"),
                      "detail": f"PR #{p.get('number')} {p.get('title', '')} ({b}): no activity for {hours / 24:.1f} days"})
    return items


def label(item):
    """Short one-line name for a tile hint / status line."""
    if item["kind"] == "idle-pr":
        return f"#{item['pr']} {item['branch']}"
    return item["branch"] or os.path.basename(item["path"] or "") or "?"


def summary(items):
    """One status line, or '' when nothing is stale."""
    if not items:
        return ""
    shown = ", ".join(f"{label(i)} ({i['kind']})" for i in items[:3])
    more = f", … ({len(items)} total)" if len(items) > 3 else ""
    return f"stale work: {shown}{more} — {PRUNE_STALE_FIX}"


def plan(items):
    """[(item, action, reason)] with action in remove | keep | list."""
    out = []
    for i in items:
        if i["kind"] == "idle-pr":
            out.append((i, "list", "PRs are never closed automatically — merge it, or close it on GitHub"))
        elif i["current"]:
            out.append((i, "keep", "this is the worktree you are in"))
        elif i["dirty"]:
            out.append((i, "keep", f"{len(i['dirty'])} uncommitted files — commit or discard them first"))
        elif i["kind"] == "missing-worktree":
            out.append((i, "remove", "git worktree prune (the directory is already gone)"))
        else:
            out.append((i, "remove", f"save {i['ahead']} commit(s) to _quarantine/, then remove"
                                     + (" the worktree" if i["path"] else "") + (" and the branch" if i["branch"] else "")))
    return out


def quarantine(primary, ref, name, ahead):
    """Save `ref`'s commits main lacks as a patch (readable) plus a bundle (keeps merge commits) in
    _quarantine/, named with the sha so a second run never overwrites. Returns the saved paths, [] when
    there is nothing to save, or None when the save failed (then nothing may be removed)."""
    if not ahead:
        return []
    sha = run_git(["rev-parse", ref], cwd=primary).stdout.strip()
    qdir = os.path.join(primary, "_quarantine")
    os.makedirs(qdir, exist_ok=True)
    stem = os.path.join(qdir, f"stale-{name.replace('/', '-')}-{sha[:9]}")
    rng = f"{_base(primary)}..{sha}"
    patch = run_git(["format-patch", "--stdout", rng], cwd=primary).stdout
    with open(stem + ".patch", "w") as f:
        f.write(patch)
    tmp_ref = f"refs/quarantine/{os.path.basename(stem)}"          # a bundle needs a named ref, not a bare sha
    run_git(["update-ref", tmp_ref, sha], cwd=primary)
    cp = run_git(["bundle", "create", stem + ".bundle", f"{_base(primary)}..{tmp_ref}"], cwd=primary)
    run_git(["update-ref", "-d", tmp_ref], cwd=primary)
    if cp.returncode != 0 or not os.path.exists(stem + ".bundle") or not patch.strip():
        print(f"  quarantine failed for {name}: {(cp.stderr or cp.stdout).strip()}")
        return None
    return [stem + ".patch", stem + ".bundle"]


def apply_item(item, root):
    """Quarantine, then remove one stale item (never called for idle-pr, current or dirty). True on success.

    Order: save first, then `git worktree remove` without --force (git itself refuses a worktree with
    modified or untracked files), then delete the LOCAL branch only — the origin branch is kept, so a PR
    that gh failed to report can never be closed by this."""
    from kb_distillery.git import ship
    primary = ship.primary_checkout(root)
    if item["kind"] == "missing-worktree":
        return run_git(["worktree", "prune"], cwd=primary).returncode == 0
    ref = _detached_head(item["path"]) if item["kind"] == "detached-worktree" else item["branch"]
    name = item["branch"] or f"detached-{os.path.basename(item['path'])}"
    saved = quarantine(primary, ref, name, item["ahead"])
    if saved is None:
        return False
    for path in saved:
        print(f"  saved {os.path.relpath(path, primary)}")
    if item["path"]:
        cp = run_git(["worktree", "remove", item["path"]], cwd=primary)
        if cp.returncode != 0:
            print(f"  worktree not removed: {(cp.stderr or cp.stdout).strip()}")
            return False
    if item["branch"]:
        cp = run_git(["branch", "-D", item["branch"]], cwd=primary)
        if cp.returncode != 0:
            print(f"  branch not deleted: {(cp.stderr or cp.stdout).strip()}")
            return False
        print(f"  deleted local branch {item['branch']} (origin/{item['branch']}, if any, is kept)")
    return True


def cmd_prune_stale(apply=False, root=None, now=None, prs=None):
    from kb_distillery.git import ship
    root = root or ship.ROOT
    items = scan(root, now=now, prs=prs)
    if not items:
        print("no stale work")
        return 0
    removable = 0
    for item, action, reason in plan(items):
        verb = {"remove": "remove" if apply else "would remove", "keep": "keep", "list": "list"}[action]
        print(f"{verb} [{item['kind']}] {item['detail']} — {reason}")
        if action == "remove":
            removable += 1
            if apply and not apply_item(item, root):
                print("  failed")
    if not apply and removable:
        print("dry run — re-run with --apply to quarantine and remove")
    return 0

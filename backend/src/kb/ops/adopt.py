"""Adopt a curated history bundle into a checkout without losing local work.

    pixi run ops -- adopt-history <bundle> [--checkout <path>] [--dry-run] [--no-push]

Refuses unless:
  - the bundle's history/curated tip has exactly the same tree as origin/main
    (it was built from the current main);
  - origin/main and the local main are both ancestors of it (pure fast-forward);
  - every uncommitted local change to a file the fast-forward touches is already
    contained in the incoming version (3-way check with `git merge-file`).
Such "superseded" files are backed up to meta/.ops/adopt-backup/<stamp>/, reset,
and come back with the incoming content. Unrelated local edits are left alone.
Then: `git merge --ff-only` and a normal (fast-forward) push with tags.
"""
import datetime
import os
import shutil
import subprocess
import tempfile

from .core import OpsError, _git, ops_lock, _require_main
from kb.core.schema import OPS_DIR


def _blob_text(root, rev, path):
    proc = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=root, capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def _status(root):
    """{path: 'untracked' | 'tracked'} for every uncommitted path."""
    out = _git(root, "status", "--porcelain", "-z", "--untracked-files=all").stdout.split("\0")
    entries, i = {}, 0
    while i < len(out):
        rec = out[i]
        i += 1
        if len(rec) < 4:
            continue
        if rec[0] in "RC":
            i += 1
        entries[rec[3:]] = "untracked" if rec[:2] == "??" else "tracked"
    return entries


def _contained(root, path, head, target):
    """True when the local version of `path` adds nothing beyond `target`'s version."""
    full = os.path.join(root, path)
    local = open(full, "rb").read() if os.path.exists(full) else None
    theirs = _blob_text(root, target, path)
    base = _blob_text(root, head, path)
    if local == theirs:
        return True
    if local is None or theirs is None:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for name, data in (("local", local), ("base", base or b""), ("theirs", theirs)):
            files[name] = os.path.join(tmp, name)
            with open(files[name], "wb") as f:
                f.write(data)
        # A clean merge of the local edits into the incoming file that changes nothing proves
        # containment. Myers can report false conflicts when identical edits sit next to other
        # changes, so histogram and patience get a say too (any clean no-op merge is proof).
        for algo in (None, "histogram", "patience"):
            args = ["git", "merge-file", "-p"] + ([f"--diff-algorithm={algo}"] if algo else [])
            merged = subprocess.run(args + [files["local"], files["base"], files["theirs"]], capture_output=True)
            if merged.returncode == 0 and merged.stdout == theirs:
                return True
    return False


def plan(root, bundle):
    """Fetch the bundle and work out what adopting it would do. Raises OpsError if unsafe."""
    _require_main(root)
    fetch = _git(root, "fetch", "-q", bundle, "+refs/heads/history/curated:refs/heads/history/curated",
                 "+refs/tags/*:refs/tags/*")
    if fetch.returncode != 0:
        raise OpsError(f"could not read bundle: {fetch.stderr.strip()}")
    _git(root, "fetch", "-q", "origin", "main")
    target = _git(root, "rev-parse", "history/curated").stdout.strip()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    remote = _git(root, "rev-parse", "-q", "--verify", "origin/main").stdout.strip() or head
    tree = lambda rev: _git(root, "rev-parse", f"{rev}^{{tree}}").stdout.strip()
    if tree(target) != tree(remote):
        raise OpsError("the bundle was not built from the current origin/main (trees differ) — rebuild it")
    for name, rev in (("origin/main", remote), ("local main", head)):
        if _git(root, "merge-base", "--is-ancestor", rev, target).returncode != 0:
            raise OpsError(f"{name} is not an ancestor of the curated tip — not a fast-forward")
    touched = set(filter(None, _git(root, "diff", "--name-only", "-z", "--no-renames", head, target)
                         .stdout.split("\0")))
    superseded, conflicts = [], []
    for path, kind in _status(root).items():
        if path not in touched:
            continue
        (superseded if _contained(root, path, head, target) else conflicts).append((path, kind))
    if conflicts:
        raise OpsError("local edits not contained in the curated history — commit or move them first:\n  "
                       + "\n  ".join(p for p, _ in conflicts))
    return {"target": target, "head": head, "remote": remote, "superseded": superseded,
            "untouched": sorted(p for p in _status(root) if p not in touched)}


def adopt(bundle, root, push=True, dry_run=False):
    bundle = os.path.abspath(bundle)
    with ops_lock(root):
        p = plan(root, bundle)
        print(f"curated tip {p['target'][:9]} · local main {p['head'][:9]} · origin/main {p['remote'][:9]}")
        print(f"{len(p['superseded'])} local edits already contained upstream · {len(p['untouched'])} unrelated edits kept")
        for path, _ in p["superseded"]:
            print(f"  superseded: {path}")
        if dry_run:
            print("dry-run: nothing changed")
            return p
        if p["superseded"]:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = os.path.join(root, OPS_DIR, "adopt-backup", stamp)
            for path, kind in p["superseded"]:
                src = os.path.join(root, path)
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(os.path.join(backup, path)), exist_ok=True)
                    shutil.copy2(src, os.path.join(backup, path))
                if kind == "untracked":
                    os.remove(src)
                else:
                    _git(root, "checkout", p["head"], "--", path)
            print(f"backed up superseded files to {os.path.relpath(backup, root)}")
        ff = _git(root, "merge", "--ff-only", p["target"])
        if ff.returncode != 0:
            raise OpsError(f"fast-forward failed: {ff.stderr.strip()}")
        print(f"main → {p['target'][:9]} (curated history adopted)")
        # the fetched scratch branch is now identical to main — no reason to keep it around
        if _git(root, "branch", "-D", "history/curated").returncode == 0:
            print("removed scratch branch history/curated")
        if push and p["remote"] != p["target"]:
            proc = _git(root, "push", "origin", "main", "--follow-tags")
            print((proc.stdout + proc.stderr).strip() or "pushed")
            if proc.returncode != 0:
                raise OpsError("push failed — main is updated locally; push again with `pixi run daily-sync`")
        return p

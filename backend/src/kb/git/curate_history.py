#!/usr/bin/env python3
"""Rebuild git history at finer granularity in a sandbox clone — never touches the source repo.

    python3 -m kb.git.curate_history --plan final.json --src <repo> --out <dir> [--dry-run]

The plan (built from the reviewed history proposal) lists every step of the new
first-parent history in order. Each step takes file contents from an original
commit, so the rebuilt history ends in exactly the same tree as the source:

  {"steps": [{"id": "n07", "orig": "<sha>", "mode": "split"|"keep"|"keep-merge",
              "paths": ["meta/a.py", "-wiki/old.md", ...],   # split only; "-" = deletion
              "message": "<full message incl. trailers>", "author_date": "<iso>",
              "chapter": "knowledge/..." | "infra/...", "verdict": "ok",
              "second_parent": "<sha>"}],                    # keep-merge only
   "chapters": {"infra/x": {"message": "<merge message> (retro)"}},
   "replay_messages": {"<sha prefix>": "<corrected message>"}}   # optional, for replayed commits

Steps in an infra/* chapter become commits on a branch forked from main at the
chapter's first step and are merged back (--no-ff shape) right after its last step.
Steps in knowledge/* chapters land on main directly. Commits on the source main newer
than the plan are replayed tree-for-tree.

By default the old history is kept: the result ends in one merge commit
"chore(git): adopt curated history (retro)" whose first parent is the curated line
and whose second parent is the source main. Old main is then an ancestor of the new
tip, so adopting is a plain fast-forward push (no force-push, old shas stay valid).
--replace builds the curated line alone (adopting it then needs a force-push).

Built entirely with plumbing (read-tree / update-index / write-tree / commit-tree)
in a `git clone --no-local` under --out, hooks disabled, push disabled. Outputs:
report.json, sha-map.tsv, built.json, history-curated.bundle. Adopting the result
into the real repo is a manual step for the user (see report.json "adopt").
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
from kb.git import commit_policy

ZERO = "0" * 40
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BRANCH = "history/curated"


class Git:
    def __init__(self, path, env=None):
        self.path = path
        self.env = dict(os.environ, **(env or {}))

    def run(self, *args, input=None, env=None, check=True):
        e = dict(self.env, **(env or {}))
        cp = subprocess.run(["git", *args], cwd=self.path, input=input, capture_output=True,
                            text=True, env=e, check=False)
        if check and cp.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:3])}… failed: {cp.stderr.strip()}")
        return cp.stdout

    def full(self, rev):
        return self.run("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def tree_of(self, rev):
        return self.run("rev-parse", f"{rev}^{{tree}}").strip()


# ---------- change sets ----------

def entries(git, rev, paths):
    """{path: (mode, sha)} for the given paths present in rev's tree."""
    out = {}
    for i in range(0, len(paths), 200):
        chunk = paths[i:i + 200]
        for rec in git.run("ls-tree", "-r", "-z", rev, "--", *chunk).split("\0"):
            if not rec:
                continue
            meta, path = rec.split("\t", 1)
            mode, _type, sha = meta.split()
            out[path] = (mode, sha)
    return out


def diff_raw(git, a, b):
    """[(path, mode|None, sha|None)] changes from a to b (no rename detection)."""
    args = ["diff-tree", "-r", "-z", "--no-renames", "--raw"]
    args += ["--root", b] if a is None else [a, b]
    out = git.run(*args).split("\0")
    changes, i = [], 0
    if a is None and out and out[0] and not out[0].startswith(":"):
        i = 1  # --root prints the commit id first
    while i < len(out) - 1:
        meta, path = out[i], out[i + 1]
        i += 2
        if not meta.startswith(":"):
            continue
        _om, nm, _os, ns, status = meta[1:].split()
        changes.append((path, None, None) if status.startswith("D") else (path, nm, ns))
    return changes


def orig_paths(git, orig):
    parents = git.run("rev-list", "--parents", "-n1", orig).split()[1:]
    return {p for p, _m, _s in diff_raw(git, parents[0] if parents else None, orig)}


def step_changes(git, step):
    orig = step["orig_full"]
    if step["mode"] == "split":
        want = [p.lstrip("-") for p in step["paths"]]
        present = entries(git, orig, want)
        changes = []
        for raw in step["paths"]:
            path = raw.lstrip("-")
            if raw.startswith("-"):
                if path in present:
                    raise ValueError(f"{step['id']}: {path} marked deleted but exists in {orig[:9]}")
                changes.append((path, None, None))
            else:
                if path not in present:
                    raise ValueError(f"{step['id']}: {path} not in {orig[:9]} (mark it '-' if deleted)")
                changes.append((path, *present[path]))
        return changes
    parents = git.run("rev-list", "--parents", "-n1", orig).split()[1:]
    return diff_raw(git, parents[0] if parents else None, orig)


def apply(git, tree, changes, index_file):
    env = {"GIT_INDEX_FILE": index_file}
    git.run("read-tree", tree or EMPTY_TREE, env=env)
    lines = []
    for path, mode, sha in changes:
        lines.append(f"0 {ZERO}\t{path}" if mode is None else f"{mode} {sha}\t{path}")
    if lines:
        git.run("update-index", "-z", "--index-info", input="\0".join(lines) + "\0", env=env)
    return git.run("write-tree", env=env).strip()


# ---------- validation ----------

def validate(git, plan, allow_unreviewed=False):
    errors, warnings = [], []
    steps = plan["steps"]
    for s in steps:
        try:
            s["orig_full"] = git.full(s["orig"])
        except RuntimeError:
            errors.append(f"{s['id']}: unknown commit {s['orig']}")
            continue
        if not allow_unreviewed and s.get("verdict") not in ("ok", "edited"):
            errors.append(f"{s['id']}: not approved in review (verdict={s.get('verdict')})")
        if commit_policy.parse_message(s["message"]).kind == "unknown":
            errors.append(f"{s['id']}: message does not follow the convention: {s['message'].splitlines()[0]!r}")
    if errors:
        return errors, warnings
    # split coverage: every path of each split original assigned exactly once
    by_orig = {}
    for s in steps:
        if s["mode"] == "split":
            by_orig.setdefault(s["orig_full"], []).append(s)
    for orig, group in by_orig.items():
        seen = {}
        for s in group:
            for p in s["paths"]:
                path = p.lstrip("-")
                if path in seen:
                    errors.append(f"{orig[:9]}: {path} assigned to both {seen[path]} and {s['id']}")
                seen[path] = s["id"]
        expected = orig_paths(git, orig)
        missing, extra = expected - set(seen), set(seen) - expected
        if missing:
            errors.append(f"{orig[:9]}: {len(missing)} paths not assigned, e.g. {sorted(missing)[:3]}")
        if extra:
            errors.append(f"{orig[:9]}: {len(extra)} paths not changed by it, e.g. {sorted(extra)[:3]}")
    for name in {s["chapter"] for s in steps if s["chapter"].startswith("infra/")}:
        msg = plan.get("chapters", {}).get(name, {}).get("message", "")
        if commit_policy.parse_message(msg).kind != "pr-merge":
            errors.append(f"{name}: merge message must end with '(retro)' or '(#N)': {msg.splitlines()[0] if msg else ''!r}")
    return errors, warnings


def chapter_overlaps(steps, changes):
    """infra chapters whose files are also touched by main steps inside their span."""
    problems = []
    spans = {}
    for i, s in enumerate(steps):
        if s["chapter"].startswith("infra/"):
            spans.setdefault(s["chapter"], [i, i])[1] = i
    for name, (a, b) in spans.items():
        mine = {p for i in range(a, b + 1) if steps[i]["chapter"] == name for p, _m, _s in changes[i]}
        for i in range(a, b + 1):
            if steps[i]["chapter"] != name:
                clash = mine & {p for p, _m, _s in changes[i]}
                if clash:
                    problems.append(f"{name} vs {steps[i]['id']} ({steps[i]['chapter']}): {sorted(clash)[:3]}")
    return problems


# ---------- build ----------

def _plus_minute(iso):
    """Merge timestamp: one second after the branch's last commit (stays before the next step)."""
    return (datetime.datetime.fromisoformat(iso) + datetime.timedelta(seconds=1)).isoformat()


ADOPT_SUBJECT = "chore(git): adopt curated history (retro)"


def build(src, plan, out, allow_unreviewed=False, dry_run=False, keep_old=True):
    os.makedirs(out, exist_ok=True)
    report = {"src": src, "started": datetime.datetime.now().isoformat(timespec="seconds"),
              "errors": [], "warnings": [], "checks": {}}
    srcgit = Git(src)
    errors, warnings = validate(srcgit, plan, allow_unreviewed)
    report["errors"] += errors
    report["warnings"] += warnings
    steps = plan["steps"]
    if not errors:
        changes = [step_changes(srcgit, s) for s in steps]
        report["errors"] += chapter_overlaps(steps, changes)
    if report["errors"] or dry_run:
        report["result"] = "invalid" if report["errors"] else "valid (dry run)"
        _write_json(os.path.join(out, "report.json"), report)
        return report

    repo = os.path.join(out, "repo")
    if os.path.exists(repo):
        raise SystemExit(f"{repo} exists — use a fresh --out directory")
    subprocess.run(["git", "clone", "-q", "--no-local", "--no-checkout", src, repo], check=True)
    git = Git(repo)
    for key, val in (("core.hooksPath", "/dev/null"), ("gc.auto", "0"), ("remote.origin.pushurl", "DISABLED")):
        git.run("config", key, val)
    name = srcgit.run("config", "user.name", check=False).strip() or "curator"
    email = srcgit.run("config", "user.email", check=False).strip() or "curator@localhost"
    committer = {"GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}

    index_file = os.path.join(tempfile.mkdtemp(prefix="curate-idx-"), "index")
    src_main = git.full("origin/main")

    def author_of(sha):
        n, e = git.run("log", "-1", "--format=%an%x1f%ae", sha).strip().split("\x1f")
        return {"GIT_AUTHOR_NAME": n, "GIT_AUTHOR_EMAIL": e}

    def commit(tree, parents, message, author, date, orig_label):
        if orig_label and "Reconstructed-from:" not in message:
            message = message.rstrip("\n") + ("\n" if commit_policy.parse_trailers(message) else "\n\n") \
                + f"Reconstructed-from: {orig_label}\n"
        args = ["commit-tree", tree]
        for p in parents:
            args += ["-p", p]
        env = dict(committer, **author, GIT_AUTHOR_DATE=date)
        return git.run(*args, input=message, env=env).strip()

    main_tip, main_tree, linear_tree = None, None, None
    open_branches = {}  # chapter -> {"tip", "tree", "last_date", "author", "remaining"}
    remaining = {}
    for s in steps:
        remaining[s["chapter"]] = remaining.get(s["chapter"], 0) + 1
    built, sha_map = [], []
    boundaries = {}
    last_index_of = {}
    for i, s in enumerate(steps):
        last_index_of[s["orig_full"]] = i
    # source commit order, so a checkpoint compares against the newest finished original
    order = {sha: n for n, sha in enumerate(git.run("rev-list", "--reverse", "--all").split())}
    seen = set()

    for i, s in enumerate(steps):
        ch = changes[i]
        author = author_of(s["orig_full"])
        linear_tree = apply(git, linear_tree, ch, index_file)
        label = s["orig_full"][:12]
        if s["chapter"].startswith("infra/") and s["mode"] != "keep-merge":
            br = open_branches.get(s["chapter"])
            if br is None:
                br = open_branches[s["chapter"]] = {"tip": main_tip, "tree": main_tree, "changes": []}
            br["tree"] = apply(git, br["tree"], ch, index_file)
            br["tip"] = commit(br["tree"], [br["tip"]] if br["tip"] else [], s["message"], author,
                               s["author_date"], label)
            br["changes"] += ch
            br["last_date"], br["author"] = s["author_date"], author
            built.append(_rec(git, br["tip"], s, "branch"))
            remaining[s["chapter"]] -= 1
            if remaining[s["chapter"]] == 0:
                main_tree = apply(git, main_tree, br["changes"], index_file)
                msg = plan["chapters"][s["chapter"]]["message"]
                parents = [main_tip, br["tip"]] if main_tip else [br["tip"]]
                main_tip = commit(main_tree, parents, msg, br["author"], _plus_minute(br["last_date"]),
                                  s["chapter"])
                built.append(_rec(git, main_tip, {"id": s["chapter"], "chapter": s["chapter"],
                                                  "author_date": _plus_minute(br["last_date"])}, "merge"))
                del open_branches[s["chapter"]]
        else:
            main_tree = apply(git, main_tree, ch, index_file)
            parents = [main_tip] if main_tip else []
            if s["mode"] == "keep-merge":
                parents.append(git.full(s["second_parent"]))
            main_tip = commit(main_tree, parents, s["message"], author, s["author_date"], label)
            built.append(_rec(git, main_tip, s, "main"))
        if s["mode"] != "split":
            sha_map.append((s["orig_full"], built[-1]["sha"]))
        # checkpoint: every original seen so far is complete → linear tree == newest of them
        seen.add(s["orig_full"])
        if all(last_index_of[o] <= i for o in seen):
            newest = max(seen, key=lambda o: order.get(o, -1))
            ok_tree = git.tree_of(newest) == linear_tree
            if s["mode"] == "split" or not ok_tree:
                boundaries[f"{s['id']}={newest[:9]}"] = ok_tree

    if open_branches:
        report["errors"].append(f"chapters never closed: {sorted(open_branches)}")

    planned_tip = main_tip
    # replay commits on the source main newer than the plan's horizon, tree-for-tree
    horizon = git.full(plan["horizon"]) if plan.get("horizon") else None
    if horizon and horizon != src_main:
        mapped = dict(sha_map)
        mapped[horizon] = main_tip
        for rec in git.run("rev-list", "--reverse", "--first-parent", "--parents", f"{horizon}..{src_main}").splitlines():
            sha, *parents = rec.split()
            new_parents = [mapped.get(p, p) for p in parents]
            msg = git.run("log", "-1", "--format=%B", sha)
            fix = next((m for k, m in plan.get("replay_messages", {}).items() if sha.startswith(k)), None)
            if fix:  # corrected message for a replayed commit (e.g. a wrong KB-Version trailer)
                sep = "\n" if commit_policy.parse_trailers(fix) else "\n\n"  # stay in the trailer block
                msg = fix.rstrip("\n") + f"{sep}Corrected-from: {sha[:12]}\n"
            date = git.run("log", "-1", "--format=%aI", sha).strip()
            main_tip = commit(git.tree_of(sha), new_parents, msg, author_of(sha), date, None)
            mapped[sha] = main_tip
            sha_map.append((sha, main_tip))
            built.append(_rec(git, main_tip, {"id": sha[:9], "chapter": "replay", "author_date": date}, "replay"))

    curated_tip = main_tip
    if keep_old:
        # one merge joins the curated line (first parent) to the untouched old main (second parent)
        msg = (f"{ADOPT_SUBJECT}\n\nThe curated first-parent history replaces the original for reading;\n"
               f"the original commits stay reachable as this merge's second parent.\n\n"
               f"Original-main: {src_main}\n")
        now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        main_tip = commit(git.tree_of(curated_tip), [curated_tip, src_main], msg,
                          {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email}, now, None)
        built.append(_rec(git, main_tip, {"id": "adopt", "chapter": "adopt", "author_date": now}, "merge"))

    git.run("update-ref", f"refs/heads/{BRANCH}", main_tip)
    last = commit_policy.last_version(repo, main_tip)
    tag = None
    if last:
        tag = "kb-" + commit_policy.fmt_version(last)
        target = commit_policy.version_commit(repo, last, main_tip)
        git.run("tag", "-a", tag, target, "-m", "curated start", env=dict(committer))

    # ---------- verification ----------
    checks = report["checks"]
    checks["tip_tree_equals_source_main"] = git.tree_of(main_tip) == git.tree_of(src_main)
    if keep_old:
        checks["fast_forward_from_source_main"] = \
            subprocess.run(["git", "merge-base", "--is-ancestor", src_main, main_tip], cwd=repo).returncode == 0
    checks["split_boundaries"] = boundaries
    v = commit_policy.check_push_range(repo, ZERO, planned_tip)
    lane = [x for x in v if "non-knowledge paths" in x]
    checks["policy_violations"] = [x for x in v if x not in lane]
    report["warnings"] += [f"pre-lifecycle lane mix: {x}" for x in lane]
    if planned_tip != main_tip:
        report["warnings"] += [f"replayed (not curated): {x}"
                               for x in commit_policy.check_push_range(repo, planned_tip, main_tip)]
    fsck = subprocess.run(["git", "fsck", "--strict", "--no-dangling"], cwd=repo, capture_output=True, text=True)
    checks["fsck"] = fsck.returncode == 0
    fp = [b for b in built if b["role"] in ("main", "merge", "replay")]
    for prev, cur in zip(fp, fp[1:]):
        if datetime.datetime.fromisoformat(cur["author_date"]) < datetime.datetime.fromisoformat(prev["author_date"]):
            report["warnings"].append(f"author date goes back: {prev['id']} ({prev['author_date'][:16]}) "
                                      f"→ {cur['id']} ({cur['author_date'][:16]})")
    ok = (checks["tip_tree_equals_source_main"] and all(boundaries.values())
          and not checks["policy_violations"] and checks["fsck"] and not report["errors"]
          and checks.get("fast_forward_from_source_main", True))

    bundle = os.path.join(out, "history-curated.bundle")
    refs = [f"refs/heads/{BRANCH}"] + ([f"refs/tags/{tag}"] if tag else [])
    git.run("bundle", "create", bundle, *refs)
    report.update({
        "result": "verified" if ok else "FAILED",
        "branch": BRANCH, "tip": main_tip, "tag": tag,
        "first_parent_commits": int(git.run("rev-list", "--count", "--first-parent", main_tip).strip()),
        "all_commits": int(git.run("rev-list", "--count", main_tip).strip()),
        "bundle": bundle,
        "keep_old": keep_old,
        "adopt": [
            "launchctl bootout gui/$(id -u)/com.thesis-kb.daily-sync   # pause nightly sync",
            f"git fetch {bundle} {BRANCH}:{BRANCH} --tags",
            f"git diff main {BRANCH} --stat   # must print nothing",
            f"git merge --ff-only {BRANCH}   # on main — old history stays as the adopt merge's 2nd parent",
            "git push origin main --follow-tags   # plain fast-forward; pre-push validates it",
            "pixi run install-sync   # resume nightly sync",
        ] if keep_old else [
            "launchctl bootout gui/$(id -u)/com.thesis-kb.daily-sync   # pause nightly sync",
            "git tag backup/pre-curation-<date> main && git push origin backup/pre-curation-<date>",
            f"git fetch {bundle} {BRANCH}:{BRANCH} --tags",
            f"git diff main {BRANCH} --stat   # must print nothing",
            f"git checkout main && git reset --hard {BRANCH}",
            "KB_ALLOW_REWRITE=1 git push --force-with-lease=main:<old-main-sha> origin main --follow-tags",
            "rebase or delete worktree-* branches (sha-map.tsv), delete origin/worktree-raw-naming-convention",
            "pixi run install-sync   # resume nightly sync",
        ],
    })
    _write_json(os.path.join(out, "report.json"), report)
    _write_json(os.path.join(out, "built.json"), built)
    with open(os.path.join(out, "sha-map.tsv"), "w") as f:
        f.write("orig\tnew\n")
        for a, b in sha_map:
            f.write(f"{a}\t{b}\n")
    return report


def _rec(git, sha, step, role):
    subject = git.run("log", "-1", "--format=%s", sha).strip()
    parents = git.run("log", "-1", "--format=%P", sha).split()
    return {"sha": sha, "id": step.get("id"), "role": role, "chapter": step.get("chapter"),
            "subject": subject, "parents": parents, "author_date": step.get("author_date")}


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--plan", required=True)
    p.add_argument("--src", required=True, help="source repo (read only)")
    p.add_argument("--out", required=True, help="sandbox directory (outside OneDrive)")
    p.add_argument("--dry-run", action="store_true", help="validate the plan only")
    p.add_argument("--allow-unreviewed", action="store_true")
    p.add_argument("--replace", action="store_true",
                   help="drop the old history instead of keeping it as the adopt merge's second parent")
    args = p.parse_args(argv)
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    report = build(os.path.abspath(args.src), plan, os.path.abspath(args.out),
                   args.allow_unreviewed, args.dry_run, keep_old=not args.replace)
    print(f"result: {report['result']}")
    for e in report["errors"]:
        print(f"  error: {e}")
    for w in report["warnings"][:20]:
        print(f"  warning: {w}")
    if report.get("checks"):
        print("  checks:", json.dumps(report["checks"]))
    return 0 if report["result"] in ("verified", "valid (dry run)") else 1


if __name__ == "__main__":
    sys.exit(main())

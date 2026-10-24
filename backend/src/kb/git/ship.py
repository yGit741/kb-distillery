#!/usr/bin/env python3
"""Ship the tooling lane through infra/<feature> branches and PRs. Run on demand only.

    python3 -m kb.git.ship start <feature> [--worktree]   # name the branch infra/<feature>
    python3 -m kb.git.ship commit "feat(scope): msg"      # policy → gates → commit tooling paths
    python3 -m kb.git.ship pr [--title "..."] [--hold]    # gates → push → gh pr create (idempotent)
    python3 -m kb.git.ship merge                          # sync main → gates → merge commit "<title> (#N)"
    python3 -m kb.git.ship approve N                      # USER ONLY: lift the hold on PR #N
    python3 -m kb.git.ship merge --local --pr N           # offline: git merge --no-ff into main
    python3 -m kb.git.ship status                         # pending changes grouped by lane
    python3 -m kb.git.ship prune [--apply]                # delete merged infra/* / worktree-* branches + their clean worktrees
    python3 -m kb.git.ship prune --drop <branch>          # delete one unmerged branch, patch saved to _quarantine/

Hygiene is built into the commands that already run: `merge` removes its own worktree and
local branch (and tags a post-migration snapshot after a schema PR), `status` reports stale
worktrees, open PRs and the nightly sync, `prune` only ever deletes what is merged and clean.

Legacy (bootstrap only; refused once GIT_POLICY_MODE=enforce):
    python3 -m kb.git.ship "feat(dashboard): launch command" [--dry-run] [--no-push] [--skip-tests]

Merging is the agent's default: `merge` runs as soon as the gates pass. A PR carrying the
`hold` label waits for the user — `pr` puts it on every schema/paradigm PR and on any PR
opened with `--hold` (the user asked to review it); `merge` refuses while it is there, and only
`approve N` lifts it. `kb.git.git_guard` blocks agents from running `approve` or editing labels.

PRs are always merged with a real merge commit — never squash or rebase — so the
branch's commits stay visible. Schema/paradigm PRs snapshot the current knowledge
version first and carry the bumped KB-Version on their merge commit.
Knowledge-lane paths are never staged here (except migrated files in a schema PR).
"""
import argparse
import json
import os
import re
import subprocess
import sys

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb.maintenance.daily_sync import changed_paths, has_open_sessions, run_git
from kb.git import commit_policy
from kb.core.schema import GIT_POLICY_MODE, SCHEMA_VERSION

GATES = [
    ("tests", [sys.executable, "-m", "pytest", "-q", "backend/tests"]),
    ("lint-skills", [sys.executable, "-m", "kb.lint.lint_skills"]),
    ("lint", [sys.executable, "-m", "kb.lint.lint"]),
]
SUBCOMMANDS = {"start", "commit", "pr", "merge", "sync", "status", "prune", "protect", "approve"}
GENERATED_FILES = {"index.md", "meta/corpus.tsv", "meta/coherence-warnings.tsv"}
MIGRATED_GENERATED = {"meta/corpus.tsv"}   # a migration's output: committed by schema/paradigm commits
FEATURE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FORBIDDEN_MERGE_FLAGS = {"--squash", "--rebase", "-s", "-r"}


PRUNABLE_PREFIXES = ("infra/", "worktree-", "history/")


def print_status(lanes, root=ROOT):
    for lane, hint in (
        ("knowledge", "pixi run ops (one commit per operation) / nightly daily-sync"),
        ("tooling", "pixi run ship -- start/commit/pr/merge"),
        ("other", "never committed — gitignore, move, or delete"),
    ):
        paths = lanes[lane]
        print(f"{lane} ({len(paths)} files → {hint})")
        for p in paths:
            print(f"  {p}")
    # hygiene lines — informational, never blocking
    from kb.ops import core as ops_core
    nightly = ops_core.nightly_status(root)
    print(f"nightly sync: {nightly['summary']}" + (f" — {nightly['hint']}" if nightly["hint"] else ""))
    ops_core.print_worktree_report(root)
    prs = open_prs(root)
    if prs:
        print("open infra PRs: " + ", ".join(f"#{p['number']} {p['branch']} ({p['age']})" for p in prs)
              + " — pixi run ship -- merge (in its worktree) or prune --drop")


def open_prs(root=ROOT):
    """Open PRs on origin as [{number, branch, title, age, hours}] — empty when gh/network is unavailable
    (`hours` is None when createdAt could not be parsed)."""
    import datetime
    try:
        cp = subprocess.run([os.environ.get("GH_BIN", "gh"), "pr", "list", "--state", "open",
                             "--json", "number,headRefName,title,createdAt"],
                            cwd=root, capture_output=True, text=True, check=False, timeout=8)
        rows = json.loads(cp.stdout) if cp.returncode == 0 and cp.stdout.strip() else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    out = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in rows if isinstance(rows, list) else []:
        try:
            created = datetime.datetime.fromisoformat(r.get("createdAt", "").replace("Z", "+00:00"))
            hours = int((now - created).total_seconds() // 3600)
            age = f"{hours // 24}d" if hours >= 48 else f"{hours}h"
        except ValueError:
            age, hours = "?", None
        out.append({"number": r.get("number"), "branch": r.get("headRefName", ""), "title": r.get("title", ""),
                    "age": age, "hours": hours})
    return out


# ---------- worktree hygiene ----------

def _worktrees(root):
    """[{path, branch}] for every linked worktree of this repository (the primary excluded)."""
    primary = os.path.realpath(primary_checkout(root))
    rows, path, branch = [], None, None
    for line in run_git(["worktree", "list", "--porcelain"], cwd=root).stdout.splitlines() + [""]:
        if line.startswith("worktree "):
            path, branch = line[len("worktree "):], None
        elif line.startswith("branch refs/heads/"):
            branch = line[len("branch refs/heads/"):]
        elif line == "" and path:
            if os.path.realpath(path) != primary:
                rows.append({"path": path, "branch": branch})
            path, branch = None, None
    return rows


def worktree_dirty(path):
    """Uncommitted paths in a worktree, ignoring files lint regenerates (and gitignored ones)."""
    if not os.path.isdir(path):
        return []
    out = run_git(["status", "--porcelain", "-z", "--untracked-files=all"], cwd=path).stdout
    entries, dirty, i = out.split("\0"), [], 0
    while i < len(entries):
        rec = entries[i]
        i += 1
        if len(rec) < 4:
            continue
        if rec[0] in "RC":
            i += 1
        if rec[3:] not in GENERATED_FILES:
            dirty.append(rec[3:])
    return dirty


def stale_worktrees(root=ROOT):
    """Worktrees that should not be there any more: on a branch main already contains (merged),
    or on a Claude session's worktree-* branch that never became an infra/<feature> PR."""
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
    here = os.path.realpath(root)
    rows = []
    for wt in _worktrees(root):
        b = wt["branch"]
        if not b:
            continue
        ahead = run_git(["rev-list", "--count", f"{base}..{b}"], cwd=root).stdout.strip()
        ahead = int(ahead) if ahead.isdigit() else 0
        merged = ahead == 0
        if not merged and not b.startswith("worktree-"):
            continue                                        # live infra work: not stale
        rows.append({**wt, "ahead": ahead, "merged": merged, "dirty": worktree_dirty(wt["path"]),
                     "current": os.path.realpath(wt["path"]) == here})
    return rows


def remove_worktree(branch, root, force=False):
    """Remove the worktree holding `branch` (when clean, or `force`) and delete the local branch.

    Only ever called for a branch main already contains; returns True when both are gone.
    """
    primary = primary_checkout(root)
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=primary).returncode == 0 else "main"
    if run_git(["merge-base", "--is-ancestor", branch, base], cwd=primary).returncode != 0 and \
            run_git(["merge-base", "--is-ancestor", branch, "main"], cwd=primary).returncode != 0:
        print(f"note: {branch} is not contained in main — worktree kept")
        return False
    for wt in _worktrees(primary):
        if wt["branch"] != branch:
            continue
        dirty = worktree_dirty(wt["path"])
        if dirty and not force:
            print(f"note: worktree kept, {len(dirty)} uncommitted files: {wt['path']}")
            return False
        cp = run_git(["worktree", "remove", "--force", wt["path"]], cwd=primary)
        if cp.returncode != 0:
            print(f"note: worktree not removed — {_out(cp)}")
            return False
        print(f"worktree removed: {wt['path']}")
    cp = run_git(["branch", "-D", branch], cwd=primary)
    if cp.returncode == 0:
        print(f"deleted local branch {branch}")
    return cp.returncode == 0


def _migration_raw_moves(root):
    """old raw path → new path (None for a collapsed duplicate) from migration finish files
    (meta/migration/*-finish.json), so worktree links follow a raw-moving migration."""
    moves = {}
    d = os.path.join(root, "meta", "migration")
    if not os.path.isdir(d):
        return moves
    for name in sorted(os.listdir(d)):
        if name.endswith("-finish.json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                data = json.load(f)
            moves.update(data.get("raw", {}))
            moves.update({p: None for p in data.get("raw_dupes", {})})
    return moves


def link_untracked_raw(root=ROOT):
    """In a linked worktree, symlink the primary checkout's gitignored raw/ files (PDFs…).

    They are not in git, so a fresh worktree lacks them and lint would fail on every
    `raw:` reference. Symlinks stay gitignored and hash identically.
    """
    if not is_linked_worktree(root):
        return 0
    primary = primary_checkout(root)
    out = subprocess.run(["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", "raw/"],
                         cwd=primary, capture_output=True, text=True, check=False).stdout or ""
    moves = _migration_raw_moves(root)
    made = 0
    for rel in filter(None, out.split("\0")):
        # a schema PR that moves raw files sees the primary's untracked file at its new path;
        # the primary itself catches up after the merge (the migration's finish step)
        if moves.get(rel) is None and rel in moves:
            continue                                    # collapsed duplicate: not linked at all
        dst = os.path.join(root, moves.get(rel, rel))
        if os.path.lexists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.symlink(os.path.join(primary, rel), dst)
        made += 1
    if made:
        print(f"linked {made} untracked raw files from the primary checkout")
    return made


def run_gates(root=ROOT, skip_tests=False):
    link_untracked_raw(root)
    for name, cmd in GATES:
        if name == "tests" and skip_tests:
            continue
        print(f"gate: {name}")
        if subprocess.run(cmd, cwd=root).returncode != 0:
            print(f"error: {name} failed")
            return False
    return True


def _out(cp):
    return ((cp.stdout or "") + (cp.stderr or "")).strip()


def current_branch(root=ROOT):
    cp = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=root,
                        capture_output=True, text=True, check=False)
    return (cp.stdout or "").strip()


def _rev_parse(root, flag):
    cp = subprocess.run(["git", "rev-parse", "--path-format=absolute", flag], cwd=root,
                        capture_output=True, text=True, check=False)
    return (cp.stdout or "").strip()


def primary_checkout(root=ROOT):
    """Path of the main working tree (the one the nightly sync runs in)."""
    common = _rev_parse(root, "--git-common-dir")
    return os.path.dirname(common) if common else root


def is_linked_worktree(root=ROOT):
    git_dir = _rev_parse(root, "--git-dir")
    return bool(git_dir) and git_dir != _rev_parse(root, "--git-common-dir")


def gh(args, root=ROOT):
    exe = os.environ.get("GH_BIN", "gh")
    return subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False)


def _policy_warn(message, branch, paths):
    for v in commit_policy.check_message(message, branch, paths):
        print(f"policy warning: {v}")


# ---------- legacy bootstrap flow ----------

def legacy(argv):
    p = argparse.ArgumentParser(description="Commit + push tooling-lane changes (legacy)")
    p.add_argument("message", nargs="?", help="commit message, e.g. 'feat(ship): launch command'")
    p.add_argument("--status", action="store_true", help="show pending changes per lane")
    p.add_argument("--dry-run", action="store_true", help="print actions, no git write")
    p.add_argument("--no-push", action="store_true", help="commit but do not push")
    p.add_argument("--skip-tests", action="store_true", help="skip the unittest gate")
    args = p.parse_args(argv)

    lanes = changed_paths()
    if args.status:
        print_status(lanes, ROOT)
        return 0
    if not args.message:
        p.error("commit message required (or --status)")

    tooling = lanes["tooling"]
    if not tooling:
        print("nothing to ship")
        return 0

    branch = current_branch()
    if GIT_POLICY_MODE == "enforce" and branch == "main":
        print("error: tooling no longer commits to main — use ship start/commit/pr/merge")
        return 1

    ingest_open, distill_open = has_open_sessions()
    if ingest_open or distill_open:
        print("skipped: open ingest/distill sessions — finish or abort them first")
        return 0

    if not run_gates(skip_tests=args.skip_tests):
        print("nothing committed")
        return 1

    # lint may regenerate knowledge files; re-read so only tooling is staged
    tooling = changed_paths()["tooling"]
    _policy_warn(args.message, branch, tooling)

    if args.dry_run:
        print(f"dry-run: would commit {len(tooling)} files: {args.message}")
        for path in tooling:
            print(f"  {path}")
        if not args.no_push:
            print("dry-run: would git push origin HEAD")
        return 0

    add = run_git(["add", "-A", "--"] + tooling)
    if add.returncode != 0:
        print(add.stderr.strip())
        return 1

    commit = run_git(["commit", "-m", args.message, "--"] + tooling)
    print(_out(commit))
    if commit.returncode != 0:
        return 1

    if args.no_push:
        print("committed (no push)")
        return 0

    push = run_git(["push", "origin", "HEAD"])
    print(_out(push))
    return push.returncode


# ---------- PR flow ----------

def link_pixi_env(root, worktree_path):
    """Symlink the primary's `.pixi` into a fresh worktree so `pixi run` reuses its env (no ~1 GB install).
    pixi.toml's [activation.env] PYTHONPATH makes `import kb` resolve to the worktree's own source."""
    src = os.path.join(primary_checkout(root), ".pixi")
    dst = os.path.join(worktree_path, ".pixi")
    if os.path.isdir(src) and not os.path.lexists(dst):
        os.symlink(src, dst)
        print(f"linked {dst} -> {src} (pixi run reuses the primary's env, no install)")
    print(f"import kb here: `pixi run python …` or `PYTHONPATH={worktree_path}/backend/src python3 …`")


def cmd_start(feature, worktree=False, root=ROOT):
    if not FEATURE_RE.match(feature):
        print("error: feature must be kebab-case, e.g. kb-ops")
        return 1
    branch = f"infra/{feature}"
    if worktree:
        run_git(["fetch", "-q", "origin", "main"], cwd=root)
        base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
        path = os.path.join(primary_checkout(root), ".claude", "worktrees", feature)
        cp = run_git(["worktree", "add", path, "-b", branch, base], cwd=root)
        print(_out(cp))
        if cp.returncode == 0:
            print(f"worktree ready: {path} on {branch}")
            link_pixi_env(root, path)
            stale = [r for r in stale_worktrees(root) if r["merged"] and not r["dirty"] and not r["current"]]
            if stale:
                print(f"note: {len(stale)} merged worktree(s) can go — pixi run ship -- prune --apply")
        return cp.returncode
    if not is_linked_worktree(root):
        print("error: start infra work in a worktree, not the primary checkout "
              "(the nightly sync needs it on main) — use --worktree")
        return 1
    current = current_branch(root)
    if current == branch:
        print(f"already on {branch}")
        return 0
    cp = run_git(["branch", "-m", branch], cwd=root)
    print(_out(cp) or f"renamed {current} → {branch}")
    return cp.returncode


def cmd_commit(message, skip_tests=False, root=ROOT, gates=True):
    branch = current_branch(root)
    if not branch.startswith("infra/"):
        print(f"error: ship commit runs on an infra/<feature> branch (current: {branch or 'detached'})")
        return 1
    parsed = commit_policy.parse_message(message)
    lanes = changed_paths(root)
    paths = list(lanes["tooling"])
    if parsed.type in ("schema", "paradigm"):
        paths += lanes["knowledge"]
    if not paths:
        print("nothing to commit")
        return 0
    violations = commit_policy.check_message(message, branch, paths)
    if violations:
        print("error: commit policy:")
        for v in violations:
            print(f"  - {v}")
        return 1
    if gates and not run_gates(root, skip_tests):
        print("nothing committed")
        return 1
    lanes = changed_paths(root)
    paths = list(lanes["tooling"]) + (lanes["knowledge"] if parsed.type in ("schema", "paradigm") else [])
    # generated files are rebuilt by lint on main — never part of a tooling commit. A schema/paradigm
    # commit keeps meta/corpus.tsv: its hand-owned columns (disposition, collection, scopes) are what a
    # migration rewrites, and lint keeps them as committed instead of re-deriving them.
    keep = MIGRATED_GENERATED if parsed.type in ("schema", "paradigm") else set()
    paths = [p for p in paths if p not in GENERATED_FILES or p in keep]
    tracked = set(filter(None, run_git(["ls-files", "-z"], cwd=root).stdout.split("\0")))
    # a `git rm --cached` (untrack, keep on disk) is already staged; re-adding would re-track it
    staged_del = set(filter(None, run_git(["diff", "--cached", "--name-only", "--diff-filter=D", "-z"],
                                          cwd=root).stdout.split("\0")))
    addable = [p for p in paths if (os.path.lexists(os.path.join(root, p)) or p in tracked) and p not in staged_del]
    if addable:
        add = run_git(["add", "-A", "--"] + addable, cwd=root)
        if add.returncode != 0:
            print(_out(add))
            return 1
    staged = set(filter(None, run_git(["diff", "--cached", "--name-only", "-z"], cwd=root).stdout.split("\0")))
    extra = sorted(staged - set(paths))
    if extra:
        print(f"error: unrelated changes are staged — unstage them first: {extra[:5]}")
        return 1
    if not staged:
        print("nothing to commit")
        return 0
    commit = run_git(["commit", "-m", message], cwd=root)
    print(_out(commit))
    return commit.returncode


def _branch_commits(root):
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
    out = run_git(["log", "--reverse", "--no-merges", "--format=%s", f"{base}..HEAD"], cwd=root).stdout
    return [s for s in out.splitlines() if s.strip()]


def _kb_steps_only(root, base):
    """True when every first-parent commit main gained since the branch point is a kb(...) step."""
    fork = run_git(["merge-base", base, "HEAD"], cwd=root).stdout.strip()
    if not fork:
        return False
    out = run_git(["log", "--first-parent", "--format=%s", f"{fork}..{base}"], cwd=root).stdout
    subjects = [s for s in out.splitlines() if s.strip()]
    return bool(subjects) and all(commit_policy.parse_message(s).kind == "kb" for s in subjects)


def _schema_kind(subjects):
    types = {commit_policy.parse_message(s).type for s in subjects}
    return "paradigm" if "paradigm" in types else ("schema" if "schema" in types else None)


def pr_body(subjects, notes=""):
    lines = ["## Summary", ""] + [f"- {s}" for s in subjects] + [
        "", "## Gates", "", "- unit tests · lint-skills · lint (run by `pixi run ship -- pr`)"]
    kind = _schema_kind(subjects)
    if kind:
        lines += ["", "## Schema", "",
                  f"This is a **{kind}** PR: merging snapshots the current knowledge version "
                  f"and bumps it ({'y+1' if kind == 'schema' else 'x+1'}). The migration run is included."]
    if notes.strip():
        lines += ["", "## Notes", "", notes.strip()]
    return "\n".join(lines) + "\n"


HOLD_LABEL = "hold"


def _hold_reason(subjects, hold=False):
    """Why a new PR must wait for the user, or None when the agent may merge it itself."""
    kind = _schema_kind(subjects)
    if kind:
        return f"{kind} PR (migration + version bump)"
    return "opened with --hold" if hold else None


def _read_notes(path):
    """`ship pr --notes FILE`: findings, proofs and caveats appended to the PR body as ## Notes."""
    if not path:
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def cmd_pr(title=None, skip_tests=False, root=ROOT, gates=True, notes_file=None, hold=False):
    branch = current_branch(root)
    if not branch.startswith("infra/"):
        print(f"error: ship pr runs on an infra/<feature> branch (current: {branch or 'detached'})")
        return 1
    subjects = _branch_commits(root)
    if not subjects:
        print("error: no commits on this branch yet — ship commit first")
        return 1
    title = title or (subjects[0] if len(subjects) == 1 else None)
    if not title:
        top = commit_policy.highest_type(subjects)
        print(f"error: several commits — pass --title '{top or 'type'}(scope): summary'")
        return 1
    problems = commit_policy.check_pr_title(title, subjects)
    if problems:
        print("error: " + "\n       ".join(problems))
        return 1
    if gates and not run_gates(root, skip_tests):
        return 1
    push = run_git(["push", "-u", "origin", branch], cwd=root)
    print(_out(push))
    if push.returncode != 0:
        return 1
    why = _hold_reason(subjects + [title], hold)
    existing = gh(["pr", "view", branch, "--json", "number,url"], root)
    if existing.returncode == 0 and existing.stdout.strip():
        info = json.loads(existing.stdout)
        print(f"PR #{info['number']} already open: {info['url']} (pushed new commits)")
        if why:
            gh(["pr", "edit", branch, "--add-label", HOLD_LABEL], root)
            print(f"held for the user: {why}")
        return 0
    args = ["pr", "create", "--base", "main", "--head", branch,
            "--title", title, "--body", pr_body(subjects, _read_notes(notes_file))]
    if why:
        gh(["label", "create", HOLD_LABEL, "--force", "--color", "B60205",
            "--description", "waits for the user's approval (pixi run ship -- approve N)"], root)
        args += ["--label", HOLD_LABEL]
    created = gh(args, root)
    print(_out(created))
    if created.returncode == 0:
        print(f"held for the user: {why} — they lift it with: pixi run ship -- approve N" if why
              else "not held: run `pixi run ship -- merge` yourself once you are done")
    return created.returncode


def cmd_approve(number, root=ROOT):
    """The user's word, as a command: lift the hold so an agent's `ship merge` may proceed."""
    cp = gh(["pr", "edit", str(number), "--remove-label", HOLD_LABEL], root)
    print(_out(cp))
    if cp.returncode == 0:
        print(f"PR #{number} approved — `pixi run ship -- merge` on its branch will now merge it")
    return cp.returncode


def cmd_sync(cont=False, abort=False, root=ROOT, gates=True):
    """Bring origin/main into this infra branch as a merge commit (the first step of `merge`, on its
    own, for a PR whose base moved). Conflicts are left in the tree to resolve by hand: edit, `git add`,
    then `ship sync --continue` (gates, then the merge commit); `--abort` drops the merge."""
    branch = current_branch(root)
    if not branch.startswith("infra/"):
        print(f"error: ship sync runs on an infra/<feature> branch (current: {branch or 'detached'})")
        return 1
    merging = run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root).returncode == 0
    if abort:
        if not merging:
            print("no merge in progress")
            return 0
        cp = run_git(["merge", "--abort"], cwd=root)
        print(_out(cp) or "merge aborted")
        return cp.returncode
    if cont:
        if not merging:
            print("error: no merge in progress — run ship sync first")
            return 1
        unmerged = [p for p in run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root).stdout.split("\n") if p]
        if unmerged:
            print("error: unresolved conflicts — fix and `git add` them first:")
            for p in unmerged:
                print(f"  {p}")
            return 1
        if gates and not run_gates(root):
            print("nothing committed — the merge stays in progress")
            return 1
        cp = run_git(["commit", "--no-edit"], cwd=root)
        print(_out(cp))
        return cp.returncode
    if merging:
        print("error: a merge is already in progress — ship sync --continue or --abort")
        return 1
    run_git(["fetch", "-q", "origin"], cwd=root)
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
    if run_git(["merge-base", "--is-ancestor", base, "HEAD"], cwd=root).returncode == 0:
        print(f"{branch} already contains {base}")
        return 0
    regenerated = [p for p in GENERATED_FILES if p in changed_paths(root)["knowledge"]]
    if regenerated:                                  # lint rebuilds them; never block a sync on them
        run_git(["checkout", "HEAD", "--", *regenerated], cwd=root)
    dirty = [p for lane in changed_paths(root).values() for p in lane]
    if dirty:
        print(f"error: uncommitted changes — ship commit them first: {dirty[:5]}")
        return 1
    cp = run_git(["merge", "--no-ff", "--no-edit", "-m", f"Merge branch 'main' into {branch}", base], cwd=root)
    print(_out(cp))
    if cp.returncode != 0:
        unmerged = [p for p in run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root).stdout.split("\n") if p]
        print(f"conflicts in {len(unmerged)} file(s) — resolve, `git add`, then: pixi run ship -- sync --continue")
        for p in unmerged:
            print(f"  {p}")
        return 1
    print(f"merged {base} into {branch}")
    return 0


def _knowledge_clashes(root, primary, base):
    """Primary-checkout knowledge edits that touch a file this PR changes, with different content."""
    changed = set(filter(None, run_git(["diff", "--name-only", "-z", "--no-renames", base, "HEAD"], cwd=root)
                         .stdout.split("\0")))
    clashes = []
    for p in changed_paths(primary)["knowledge"]:
        if p not in changed or p in GENERATED_FILES:
            continue
        local = os.path.join(primary, p)
        mine = open(local, "rb").read() if os.path.exists(local) else None
        show = subprocess.run(["git", "show", f"HEAD:{p}"], cwd=root, capture_output=True)
        theirs = show.stdout if show.returncode == 0 else None
        if mine != theirs:
            clashes.append(p)
    return clashes


def _snapshot_before_schema(primary, feature):
    """Tag the current knowledge version (annotated) before a schema/paradigm merge."""
    current = commit_policy.last_version(primary, "origin/main") or commit_policy.last_version(primary, "main")
    if not current:
        print("note: no knowledge version yet — skipping pre-merge snapshot")
        return None, True
    tag = "kb-" + commit_policy.fmt_version(current)
    if run_git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=primary).returncode == 0:
        print(f"snapshot {tag} already exists")
        return current, True
    sha = commit_policy.version_commit(primary, current, "origin/main") or commit_policy.version_commit(primary, current, "main")
    cp = run_git(["tag", "-a", tag, sha, "-m", f"pre-{feature}"], cwd=primary)
    print(_out(cp) or f"snapshot {tag} (pre-{feature})")
    if cp.returncode != 0:
        return current, False
    run_git(["push", "origin", tag], cwd=primary)
    return current, True


def cmd_merge(local=False, pr_number=None, title=None, skip_tests=False, no_push=False, root=ROOT, gates=True):
    branch = current_branch(root)
    if not branch.startswith("infra/"):
        print(f"error: ship merge runs on an infra/<feature> branch (current: {branch or 'detached'})")
        return 1
    feature = branch[len("infra/"):]
    primary = primary_checkout(root)

    run_git(["fetch", "-q", "origin"], cwd=root)
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
    behind = run_git(["merge-base", "--is-ancestor", base, "HEAD"], cwd=root).returncode != 0
    if behind and not _schema_kind(_branch_commits(root)) and _kb_steps_only(root, base):
        # knowledge and tooling paths are disjoint, so kb steps never conflict with a feature
        # branch: skip the sync merge instead of stacking one per retry
        print("main moved by kb(...) steps only — no sync merge needed")
        behind = False
    if behind:
        # lint gates regenerate these in the worktree; they are rebuilt anyway, so drop them before syncing
        regenerated = [p for p in GENERATED_FILES if p in changed_paths(root)["knowledge"]]
        if regenerated:
            run_git(["checkout", "HEAD", "--", *regenerated], cwd=root)
        sync = run_git(["merge", "--no-edit", "-m", f"Merge branch 'main' into {branch}", base], cwd=root)
        print(_out(sync))
        if sync.returncode != 0:
            run_git(["merge", "--abort"], cwd=root)
            print("error: main does not merge cleanly into the branch — resolve by hand")
            return 1
    if gates and not run_gates(root, skip_tests):
        return 1

    if local:
        if pr_number is None or not title:
            print("error: --local needs --pr N and --title (subject is '<title> (#N)')")
            return 1
    else:
        if not no_push:
            run_git(["push", "-u", "origin", branch], cwd=root)
        view = gh(["pr", "view", branch, "--json", "number,title,state,labels"], root)
        if view.returncode != 0:
            print("error: no PR for this branch — run ship pr first")
            print(_out(view))
            return 1
        info = json.loads(view.stdout)
        if info.get("state") not in (None, "OPEN"):
            print(f"error: PR #{info['number']} is {info['state']}")
            return 1
        if HOLD_LABEL in {l.get("name") for l in info.get("labels") or []}:
            print(f"error: PR #{info['number']} is held for the user's approval — ask them to run: "
                  f"pixi run ship -- approve {info['number']}")
            return 1
        pr_number, title = info["number"], title or info["title"]

    subjects = _branch_commits(root)
    problems = commit_policy.check_pr_title(title, subjects)
    if problems:
        print("error: " + "\n       ".join(problems) + "\n       (retitle the PR on GitHub or pass --title)")
        return 1
    subject = f"{title} (#{pr_number})"
    # the commit list makes `git log --first-parent` readable without GitHub; trailers stay last
    body_lines = [f"- {s}" for s in subjects]
    kind = _schema_kind(subjects + [title])
    if kind:
        clashes = _knowledge_clashes(root, primary, base)
        if clashes:
            print("error: uncommitted knowledge in the primary checkout differs from this PR's migrated notes:")
            for p in clashes[:10]:
                print(f"  {p}")
            print("commit them (pixi run ops -- record …) or align them first")
            return 1
        current, ok = _snapshot_before_schema(primary, feature)
        if not ok:
            return 1
        try:
            # this checkout is the PR branch, so schema.SCHEMA_VERSION is the PR's declared schema
            version = commit_policy.merge_version(SCHEMA_VERSION, current, kind)
        except ValueError as e:
            print(f"error: {e}")
            return 1
        body_lines += ["", "KB-Version: " + commit_policy.fmt_version(version)]
    if commit_policy.parse_message(subject).kind != "pr-merge":
        print(f"error: merge subject does not follow the convention: {subject!r}")
        return 1
    body = "\n".join(body_lines)

    if local:
        if current_branch(primary) != "main":
            print("error: primary checkout is not on main")
            return 1
        msg = subject + ("\n\n" + body if body else "")
        cp = run_git(["merge", "--no-ff", "-m", msg, branch], cwd=primary)
        print(_out(cp))
        if cp.returncode != 0:
            run_git(["merge", "--abort"], cwd=primary)
            return 1
        rc = 0
        if not no_push:
            push = run_git(["push", "origin", "main"], cwd=primary)
            print(_out(push))
            rc = push.returncode
            if rc == 0:
                from kb.ops import core as ops_core
                ops_core.share_autodeploy(f"merge {branch} (local)", primary)
        _finish_merge(branch, feature, kind, primary, root, push=not no_push)
        return rc

    args = ["pr", "merge", str(pr_number), "--merge", "--subject", subject, "--body", body]
    assert not FORBIDDEN_MERGE_FLAGS & set(args), "ship never squashes or rebases"
    merged = gh(args, root)
    print(_out(merged))
    if merged.returncode != 0:
        return 1
    run_git(["push", "origin", "--delete", branch], cwd=root)
    from kb.ops import core as ops_core
    try:
        print(f"primary checkout: {ops_core.update_main(primary)}")
        ops_core.share_autodeploy(f"merge {branch}", primary)
    except ops_core.OpsError as e:
        print(f"note: primary checkout not updated — {e}")
    _finish_merge(branch, feature, kind, primary, root, push=not no_push)
    return 0


def _finish_merge(branch, feature, kind, primary, root, push=True):
    """After the merge landed on main: post-migration snapshot, then remove the PR's worktree."""
    if kind:
        _snapshot_after_schema(primary, feature, push)
    was_here = is_linked_worktree(root) and os.path.isdir(root)
    if remove_worktree(branch, primary) and was_here and not os.path.isdir(root):
        print(f"this worktree is gone — continue in the primary checkout: {primary}")


def _snapshot_after_schema(primary, feature, push=True):
    """Tag the new baseline (the schema merge's KB-Version) so pre/post snapshots bracket a migration."""
    from kb.ops import core as ops_core
    try:
        tag = ops_core.snapshot(f"post-{feature}", root=primary)
    except ops_core.OpsError as e:
        print(f"note: no post-merge snapshot — {e}")
        return None
    if push and run_git(["remote"], cwd=primary).stdout.strip():
        run_git(["push", "-q", "origin", tag], cwd=primary)
    return tag


def cmd_protect(root=ROOT):
    """Repository settings that keep PR history intact: merge commits only (no squash, no rebase)."""
    cp = gh(["repo", "edit", "--enable-merge-commit=true", "--enable-squash-merge=false",
             "--enable-rebase-merge=false", "--delete-branch-on-merge=true"], root)
    print(_out(cp) or "GitHub: merge commits only; squash and rebase merges disabled")
    return cp.returncode


def cmd_drop(branch, root=ROOT):
    """Delete an unmerged branch (local + origin) after saving its commits as a patch in _quarantine/."""
    if branch in ("main", "HEAD") or not branch:
        print("error: refusing to drop main")
        return 1
    ref = branch if run_git(["rev-parse", "-q", "--verify", branch], cwd=root).returncode == 0 else f"origin/{branch}"
    if run_git(["rev-parse", "-q", "--verify", ref], cwd=root).returncode != 0:
        print(f"error: no branch {branch}")
        return 1
    attached = run_git(["worktree", "list", "--porcelain"], cwd=root).stdout
    if f"branch refs/heads/{branch}\n" in attached + "\n":
        print(f"error: {branch} is checked out in a worktree — remove the worktree first")
        return 1
    quarantine = os.path.join(primary_checkout(root), "_quarantine")
    os.makedirs(quarantine, exist_ok=True)
    patch = os.path.join(quarantine, f"dropped-{branch.replace('/', '-')}.patch")
    with open(patch, "w") as f:
        f.write(run_git(["format-patch", "--stdout", f"origin/main..{ref}"], cwd=root).stdout)
    print(f"saved {os.path.relpath(patch, primary_checkout(root))}")
    if run_git(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], cwd=root).returncode == 0:
        print(_out(run_git(["branch", "-D", branch], cwd=root)))
    if run_git(["rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}"], cwd=root).returncode == 0:
        print(_out(run_git(["push", "origin", "--delete", branch], cwd=root)) or f"deleted origin/{branch}")
    return 0


def prune_plan(root=ROOT, fetch=True):
    """What `prune` would delete: (gone, kept) — gone = [(where, branch)] with where in
    worktree | local | remote; kept = human-readable reasons. Read-only (apart from the fetch)."""
    if fetch:
        run_git(["fetch", "-q", "--prune", "origin"], cwd=root)
    base = "origin/main" if run_git(["rev-parse", "-q", "--verify", "origin/main"], cwd=root).returncode == 0 else "main"
    here = os.path.realpath(root)
    attached = {wt["branch"]: wt for wt in _worktrees(root) if wt["branch"]}
    local = [b for b in run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=root).stdout.split()
             if b.startswith(PRUNABLE_PREFIXES)]
    remote = [b for b in run_git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], cwd=root).stdout.split()
              if b not in ("origin/main", "origin/HEAD", "origin")]
    gone, kept = [], []
    for b in local:
        unique = run_git(["rev-list", "--count", f"{base}..{b}"], cwd=root).stdout.strip()
        wt = attached.get(b)
        if wt and os.path.realpath(wt["path"]) == here:
            kept.append(f"{b} (this worktree)")
        elif unique != "0":
            hint = " — `pixi run ship -- start <feature>` inside it, or prune --drop" if b.startswith("worktree-") else ""
            kept.append(f"{b} ({unique} commits not on main{', session worktree' if wt and b.startswith('worktree-') else ''}){hint}")
        elif wt and worktree_dirty(wt["path"]):
            kept.append(f"{b} (merged, but {len(worktree_dirty(wt['path']))} uncommitted files in {wt['path']})")
        else:
            gone.append(("worktree" if wt else "local", b))
    for r in remote:
        unique = run_git(["rev-list", "--count", f"{base}..{r}"], cwd=root).stdout.strip()
        (gone.append(("remote", r[len("origin/"):])) if unique == "0"
         else kept.append(f"{r} ({unique} commits not on main)"))
    return gone, kept


def cmd_prune(apply=False, root=ROOT):
    """Delete infra/*, worktree-* and history/* branches (local + origin) already contained in origin/main,
    together with the worktree that holds them when it has no uncommitted work.

    Branches with commits main lacks, dirty worktrees and the current worktree are kept and listed.
    Dry run unless apply=True.
    """
    gone, kept = prune_plan(root)
    for where, b in gone:
        print(f"{'delete' if apply else 'would delete'} {where + (' + branch' if where == 'worktree' else '')} {b}")
        if apply:
            if where == "worktree":
                if not remove_worktree(b, root):
                    print("  failed")
                continue
            cp = run_git(["branch", "-D", b], cwd=root) if where == "local" else \
                run_git(["push", "origin", "--delete", b], cwd=root)
            if cp.returncode != 0:
                print(f"  failed: {_out(cp)}")
    for k in kept:
        print(f"keep {k}")
    if not apply and gone:
        print("dry run — re-run with --apply to delete")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] not in SUBCOMMANDS:
        return legacy(argv)
    p = argparse.ArgumentParser(prog="ship", description="Ship tooling through infra/* PRs")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("feature")
    s.add_argument("--worktree", action="store_true", help="create .claude/worktrees/<feature> from origin/main")
    c = sub.add_parser("commit")
    c.add_argument("message")
    c.add_argument("--skip-tests", action="store_true")
    r = sub.add_parser("pr")
    r.add_argument("--title")
    r.add_argument("--skip-tests", action="store_true")
    r.add_argument("--notes", metavar="FILE", help="markdown appended to the PR body as ## Notes")
    r.add_argument("--hold", action="store_true", help="the user wants to review it: merge waits for `approve`")
    ap = sub.add_parser("approve", help="USER ONLY: lift the hold on PR N (agents are blocked by git_guard)")
    ap.add_argument("number", type=int)
    m = sub.add_parser("merge")
    m.add_argument("--local", action="store_true", help="merge --no-ff into main without GitHub")
    m.add_argument("--pr", type=int, help="PR number (required with --local)")
    m.add_argument("--title", help="PR title (required with --local)")
    m.add_argument("--skip-tests", action="store_true")
    m.add_argument("--no-push", action="store_true")
    sy = sub.add_parser("sync", help="merge origin/main into this infra branch (conflicts left to resolve)")
    sy.add_argument("--continue", dest="cont", action="store_true", help="gates, then commit the resolved merge")
    sy.add_argument("--abort", action="store_true")
    sub.add_parser("status")
    pr_ = sub.add_parser("prune")
    pr_.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    pr_.add_argument("--drop", metavar="BRANCH", help="delete one UNMERGED branch after saving it to _quarantine/")
    sub.add_parser("protect", help="GitHub settings: merge commits only, no squash/rebase")
    args = p.parse_args(argv)

    if args.cmd == "prune":
        return cmd_drop(args.drop) if args.drop else cmd_prune(args.apply)
    if args.cmd == "protect":
        return cmd_protect()
    if args.cmd == "sync":
        return cmd_sync(cont=args.cont, abort=args.abort)
    if args.cmd == "status":
        print_status(changed_paths(), ROOT)
        return 0
    if args.cmd == "start":
        return cmd_start(args.feature, args.worktree)
    if args.cmd == "commit":
        return cmd_commit(args.message, args.skip_tests)
    if args.cmd == "pr":
        return cmd_pr(args.title, args.skip_tests, notes_file=args.notes, hold=args.hold)
    if args.cmd == "approve":
        return cmd_approve(args.number)
    return cmd_merge(args.local, args.pr, args.title, args.skip_tests, args.no_push)


if __name__ == "__main__":
    sys.exit(main())

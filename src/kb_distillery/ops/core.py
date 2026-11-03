"""One knowledge operation = one versioned commit on main.

Every writer (ingest, catalog, distill, researcher, free-form wiki edits) ends in
`commit_op`, which commits exactly the knowledge files that operation changed as
`kb(<op>): <summary> (kb-x.y.z)` with KB-Version / KB-Op / KB-Target trailers.
Human edits under think/ are committed first, on their own, as `kb(think)`.

Undo and restore only ever rewrite the restorable set (schema.RESTORABLE_PATHS):
never raw/ (immutable), think/ (human-owned), wiki/log.md (append-only) or the
generated files (lint regenerates them).
"""
import contextlib
import datetime
import fcntl
import json
import os
import re
import secrets
import subprocess
import sys

from kb_distillery.config.paths import THINK_PATH, vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.git import commit_policy as cp
from kb_distillery.ops.daily_sync import changed_paths, has_open_sessions, run_git
from kb_distillery.vault import log as kblog
from kb_distillery.vault.schema import (INDEX_REL, LOG_REL, OPS_DIR, RESTORABLE_PATHS, RESTORE_EXCLUDED, RESTORE_EXCLUDED_GLOBS, is_index_path, is_page_file,
                                       lane_of, strip_prefix)

GENERATED_KNOWLEDGE = (INDEX_REL, "meta/corpus.tsv", "meta/coherence-warnings.tsv")
LOG_PATH = LOG_REL
MAX_SUMMARY = cp.MAX_SUMMARY
# Human-owned paths committed on their own as kb(think) before any agent op (and nightly).
HUMAN_PREFIXES = ("think/",)
NIGHTLY_LABEL = "com.kb-distillery.daily-sync"
NIGHTLY_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{NIGHTLY_LABEL}.plist")
NIGHTLY_LOG = os.path.expanduser("~/Library/Logs/kb-distillery-daily-sync.log")


class OpsError(RuntimeError):
    pass


# ---------- small helpers ----------

def _git(root, *args, check=False, env=None):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), check=False)
    if check and proc.returncode != 0:
        raise OpsError(f"git {args[0]} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def identity_env(root):
    """Env that gives a kb commit an author where git has none (a fresh HOME). Per field: a configured user.name /
    user.email (or GIT_* variable) always wins, the fallback fills only what is missing. `distill doctor` still warns."""
    out = {}
    for field, key, default in (("NAME", "user.name", "kb-distillery"), ("EMAIL", "user.email", "kb@localhost")):
        have = os.environ.get(f"GIT_AUTHOR_{field}") or _git(root, "config", "--get", key).stdout.strip()
        if not have:
            out.update({f"GIT_AUTHOR_{field}": default, f"GIT_COMMITTER_{field}": default})
    return out


def _ops_dir(root):
    path = os.path.join(root, OPS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def current_branch(root=ROOT):
    return _git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def in_progress(root=ROOT):
    """'merge' / 'rebase' / 'revert' / 'cherry-pick' when git is mid-operation, else None."""
    for ref, name in (("MERGE_HEAD", "merge"), ("REVERT_HEAD", "revert"),
                      ("CHERRY_PICK_HEAD", "cherry-pick"), ("REBASE_HEAD", "rebase")):
        if _git(root, "rev-parse", "-q", "--verify", ref).returncode == 0:
            return name
    git_dir = _git(root, "rev-parse", "--git-dir").stdout.strip()
    for d in ("rebase-merge", "rebase-apply"):
        if git_dir and os.path.isdir(os.path.join(root, git_dir, d)):
            return "rebase"
    return None


def _require_main(root):
    branch = current_branch(root)
    if branch != "main":
        raise OpsError(f"knowledge commits go on main (current: {branch or 'detached'}) — files left uncommitted")
    state = in_progress(root)
    if state:
        raise OpsError(f"git is in the middle of a {state} — finish it first")


@contextlib.contextmanager
def ops_lock(root=ROOT, blocking=True):
    """Exclusive lock shared by ops commands and the nightly sync."""
    fh = open(os.path.join(_ops_dir(root), "lock"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        fh.close()
        raise OpsError("another ops command or the nightly sync holds the lock")
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _shorten(text, limit=MAX_SUMMARY):
    """Fit `text` in `limit` chars, cutting at a word boundary rather than mid-word."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


HASH_LIKE = re.compile(r"^[0-9a-f]{7,40}$")


def short_title(slug):
    """Words for a subject line: `paper-2023-are-emergent-abilities…` → `2023 are emergent abilities…`.

    The full slug stays in the KB-Target trailer; the subject is for reading.
    """
    return strip_prefix(slug).replace("-", " ") if "-" in slug else slug


def _is_wiki_page(path):
    """A changed path that is a wiki page (not wiki/index.md or wiki/log.md, the reserved files)."""
    return path.startswith("wiki/") and "/" not in path[5:] and is_page_file(path[5:])


def _target_of(target, paths):
    """A readable KB-Target: never a session id or sha (fall back to the first wiki page touched)."""
    if target and not HASH_LIKE.match(target):
        return target
    for p in paths:
        if _is_wiki_page(p):
            return os.path.basename(p)[:-3]
    return target or "kb"


def _pages(paths):
    return sorted(os.path.basename(p)[:-3] for p in paths if _is_wiki_page(p))


def _tier(root, op, target, pages=()):
    """easy | full | deep for a digest step, read from the digested page's `depth`
    (the target page, or the touched page named after the target's raw stem)."""
    if op != "digest":
        return None
    for slug in [target] + [p for p in pages if p != target and p.endswith(target)]:
        try:
            with open(os.path.join(root, "wiki", f"{slug}.md"), encoding="utf-8") as f:
                head = f.read(4000)
        except OSError:
            continue
        m = re.search(r"^depth:\s*(easy|full|deep)\s*$", head, re.M)
        if m:
            return m.group(1)
    return None


def run_lint(root=ROOT, okf_pages=None):
    """Lint, then okf-check on `okf_pages` only (relative paths of the pages this commit changes). None = no OKF check:
    undo and restore return to an earlier state and must work from a bad one."""
    proc = subprocess.run([sys.executable, "-m", "kb_distillery.lint.lint"], cwd=root, env=dict(os.environ, KB_ROOT=str(root)),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-8:])
        raise OpsError(f"lint failed — nothing committed\n{tail}")
    if okf_pages is not None:
        okf_gate(root, okf_pages)


def okf_gate(root, okf_pages):
    """okf-check the pages a commit changes (relative paths; non-pages ignored). Raises OpsError naming file and rule."""
    pages = sorted(p for p in okf_pages if p.startswith("wiki/") and p.endswith(".md")
                   and not is_index_path(p) and p != LOG_REL and os.path.isfile(os.path.join(root, p)))
    if not pages:
        return
    # the OKF gate: no bypass. A finding names the file and the rule; fix that page, then commit again
    okf = subprocess.run([sys.executable, "-m", "kb_distillery.lint.okf_check", *(f"--only={p}" for p in pages)], cwd=root,
                         env=dict(os.environ, KB_ROOT=str(root)), capture_output=True, text=True)
    if okf.returncode != 0:
        lines = (okf.stdout or okf.stderr or "").splitlines()
        shown = "\n".join(lines[:25] + ([f"… and {len(lines) - 26} more"] if len(lines) > 26 else []) + lines[-1:])
        raise OpsError(f"okf-check failed — nothing committed (fix the pages named below; there is no bypass)\n{shown}")


# ---------- knowledge state snapshots ----------

def knowledge_state(root=ROOT):
    """{path: (size, mtime_ns) | None} for every uncommitted knowledge path."""
    state = {}
    for rel in changed_paths(root)["knowledge"]:
        full = os.path.join(root, rel)
        try:
            st = os.stat(full)
            state[rel] = (st.st_size, st.st_mtime_ns)
        except FileNotFoundError:
            state[rel] = None
    return state


def changed_since(before, root=ROOT):
    after = knowledge_state(root)
    return sorted(p for p in set(before) | set(after) if before.get(p, "clean") != after.get(p, "clean"))


def _session_owned(root):
    owned = set()
    ingest, distill = has_open_sessions(root)
    for s in ingest:
        owned |= set(s.get("new_files", []) + s.get("modified_files", []))
    for s in distill:
        owned |= set(s.get("modified_files", []))
    return owned


# ---------- commits ----------

MAX_BODY_PAGES = 30


def _message(op, summary, version, target, extra=None, pages=None):
    """Subject says what the step did in words; the body lists the pages, trailers the facts."""
    if not summary or summary == target:
        summary = short_title(target)
    lines = [f"kb({op}): {_shorten(summary)} (kb-{cp.fmt_version(version)})", ""]
    if pages:
        lines += [f"- {p}" for p in pages[:MAX_BODY_PAGES]]
        if len(pages) > MAX_BODY_PAGES:
            lines.append(f"- … and {len(pages) - MAX_BODY_PAGES} more")
        lines.append("")
    lines += [f"KB-Version: {cp.fmt_version(version)}", f"KB-Op: {op}", f"KB-Target: {target}"]
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


def _commit_paths(root, paths, message):
    """Stage and commit exactly `paths` (pathspec commit, other staged work untouched)."""
    add = _git(root, "add", "-A", "--", *paths)
    if add.returncode != 0:
        raise OpsError(f"git add failed: {add.stderr.strip()}")
    pending = [p for p in paths if _git(root, "diff", "--cached", "--quiet", "--", p).returncode == 1]
    if not pending:
        return None
    nonce = secrets.token_hex(8)
    token_file = os.path.join(root, _git(root, "rev-parse", "--git-path", "kb-linted").stdout.strip())
    with open(token_file, "w") as f:
        f.write(nonce)
    try:
        # KB_LINTED + the nonce file let scripts/githooks/pre-commit skip re-linting
        proc = subprocess.run(["git", "commit", "-q", "-F", "-", "--", *pending], cwd=root,
                              input=message, capture_output=True, text=True,
                              env=dict(os.environ, **identity_env(root), KB_LINTED=nonce))
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(token_file)
    if proc.returncode != 0:
        raise OpsError(f"git commit failed: {(proc.stderr or proc.stdout).strip()}")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def chore(scope, summary, paths=None, root=ROOT, push=True):
    """Commit a kb repo's own tooling files (`KB_TOOLING_PATHS`: kb.toml, .claude/, CLAUDE.md, ...) as one
    `chore(<scope>): <summary>` on its main. Unversioned, like any chore there. Only tooling paths are taken
    (`paths` narrows the choice, and must all be tooling); knowledge edits in the same tree are never touched.
    Returns the new sha, or None when no tooling file changed."""
    from kb_distillery.vault.schema import is_kb_tooling
    from kb_distillery.git.commit_policy import _is_kb_repo
    if not _is_kb_repo(root):
        raise OpsError("ops chore is for a knowledge base that is its own git repo (kb.toml at its top)")
    with ops_lock(root):
        _require_main(root)
        out = _git(root, "status", "--porcelain", "-z", "--untracked-files=all").stdout
        dirty = sorted({e[3:] for e in out.split("\0") if len(e) > 3})
        if paths:
            bad = [p for p in paths if not is_kb_tooling(p)]
            if bad:
                raise OpsError(f"not kb tooling paths (use ops commit for knowledge): {', '.join(bad)}")
            chosen = [p for p in paths if p in dirty]
        else:
            chosen = [p for p in dirty if is_kb_tooling(p)]
        if not chosen:
            return None
        if "kb.toml" in chosen:
            run_lint(root)          # a kb.toml the engine cannot read must not reach main (the hook skips lint here)
        sha = _commit_paths(root, chosen, f"chore({scope}): {summary}\n")
        if sha:
            print(f"committed chore({scope}): {summary}")
            if push:
                push_main(root, quiet=True)
        return sha


def is_human_path(path):
    """think/ notes: human-owned, committed on their own as kb(think)."""
    return path.startswith(HUMAN_PREFIXES)


def push_main(root=ROOT, quiet=False):
    """Push main (+ snapshot tags) right after a knowledge step; never fatal.

    Offline or rejected pushes print one note — the nightly sync retries. KB_NO_PUSH=1
    (or `ops commit --no-push`) skips it, e.g. when working offline on purpose.
    """
    if os.environ.get("KB_NO_PUSH") or not _git(root, "remote").stdout.strip():
        return False
    proc = _git(root, "push", "-q", "origin", "main", "--follow-tags")
    if proc.returncode != 0:
        reason = ((proc.stderr or proc.stdout).strip().splitlines() or ["?"])[-1]
        print(f"note: push failed ({reason}) — main stays local, the nightly sync retries")
        return False
    if not quiet:
        print("pushed main")
    return True


def nightly_status(root=ROOT):
    """Is the nightly launchd sync installed, loaded, and when did it last run? (read-only)"""
    installed = os.path.isfile(NIGHTLY_PLIST)
    loaded = False
    if installed:
        try:
            uid = os.getuid()
            loaded = subprocess.run(["launchctl", "print", f"gui/{uid}/{NIGHTLY_LABEL}"],
                                    capture_output=True, check=False).returncode == 0
        except (FileNotFoundError, AttributeError):
            loaded = False
    last_run = None
    if os.path.isfile(NIGHTLY_LOG):
        last_run = datetime.datetime.fromtimestamp(os.path.getmtime(NIGHTLY_LOG)).isoformat(timespec="minutes")
    if not installed:
        summary, hint = "NOT INSTALLED", "pixi run install-sync"
    elif not loaded:
        summary, hint = "installed but not loaded", "pixi run install-sync"
    elif not last_run:
        summary, hint = "installed, never ran", f"launchctl kickstart gui/{os.getuid()}/{NIGHTLY_LABEL}"
    else:
        summary, hint = f"ok (last run {last_run})", None
        stale = datetime.datetime.now() - datetime.datetime.fromisoformat(last_run)
        if stale.days >= 2:
            summary, hint = f"stale (last run {last_run})", f"tail {NIGHTLY_LOG}"
    return {"installed": installed, "loaded": loaded, "last_run": last_run, "summary": summary, "hint": hint}


def nightly_in_use(root=ROOT):
    """Has this kb opted into the nightly sync: a sync config, a recorded run, or the launchd job on this machine?

    A kb that never did (a fresh `distill init`) has no nightly to report on, so the System screen shows nothing about it."""
    from . import runlog
    return (os.path.isfile(os.path.join(root, "meta", "ops", "sync.toml")) or os.path.isfile(NIGHTLY_PLIST)
            or bool(runlog.read(root, 1)))


def think_repo(root=ROOT):
    """Where kb(think) commits go: the shared think repo (`kbs/think/`, its own git history) when
    it is one, else the vault itself (legacy layout, think/ inside the vault)."""
    shared = THINK_PATH if root == ROOT else os.path.join(root, "think")
    return shared if os.path.exists(os.path.join(shared, ".git")) else root


def sync_human(root=ROOT):
    """Commit dirty think files on their own as kb(think) — human edits never mix with agent work. In the
    shared think repo every dirty file is a human edit; in a legacy vault only think/ paths are."""
    repo = think_repo(root)
    if repo == root:
        think = [p for p in changed_paths(root)["knowledge"] if is_human_path(p)]
    else:
        think = [p for lane in changed_paths(repo).values() for p in lane]
    if not think:
        return None
    if repo == root:
        _require_main(root)
    version = cp.next_version(repo)
    summary = f"human edits ({len(think)} file{'s' if len(think) != 1 else ''})"
    msg = _message("think", summary, version, "think", {"KB-Actor": "human"})
    if repo == root:  # the shared think repo has no meta/log.md; the legacy vault logs the step in the same commit
        if LOG_PATH not in set(changed_paths(root)["knowledge"]):  # a dirty log is another writer's pending line
            _log_step(root, "think", "think", summary, set())
            think = think + [LOG_PATH]
    sha = _commit_paths(repo, think, msg)
    if sha:
        print(f"committed human think edits as kb-{cp.fmt_version(version)} in {repo}")
    return sha


def _log_step(root, op, target, summary, dirty):
    """Give the step its meta/log.md line unless the writer already logged it (log.md is dirty)."""
    if LOG_PATH in dirty:
        return
    shown = summary if summary and summary != target else short_title(target)
    kblog.append(root, op, _shorten(shown), (target,))


def commit_op(op, target, summary=None, paths=None, lint=True, trailers=None, root=ROOT, _locked=False,
              push=True):
    """Commit one knowledge operation. Returns the new sha, or None if nothing changed.

    `paths` = files this operation changed (see knowledge_state / changed_since).
    Generated files and meta/log.md are added when dirty; think/ and files owned by
    other open sessions are never included. The step is pushed right away (see push_main)
    so main never sits ahead of origin waiting for the night.
    """
    if op not in cp.KB_OPS:
        raise OpsError(f"unknown op {op!r} (one of {', '.join(cp.KB_OPS)})")
    ctx = contextlib.nullcontext() if _locked else ops_lock(root)
    with ctx:
        _require_main(root)
        sync_human(root)
        owned = _session_owned(root)
        dirty = set(changed_paths(root)["knowledge"])
        chosen = [p for p in (paths if paths is not None else dirty)
                  if lane_of(p) == "knowledge" and not is_human_path(p) and p not in owned]
        if lint:
            run_lint(root, okf_pages=chosen)
            dirty = set(changed_paths(root)["knowledge"])      # lint regenerates files
            chosen = [p for p in (paths if paths is not None else dirty)
                      if lane_of(p) == "knowledge" and not is_human_path(p) and p not in owned]
        elif op not in ("undo", "restore"):
            okf_gate(root, chosen)          # the caller linted already; the OKF check is still ours
        if not chosen:
            return None
        version = cp.next_version(root)
        target = _target_of(target, chosen)
        _log_step(root, op, target, summary, dirty)
        dirty = set(changed_paths(root)["knowledge"])
        chosen += [p for p in (*GENERATED_KNOWLEDGE, *sorted(d for d in dirty if is_index_path(d)), LOG_PATH)
                   if p in dirty and p not in chosen]
        trailers = dict(trailers or {})
        pages = _pages(chosen)
        tier = _tier(root, op, target, pages)
        if tier and "KB-Tier" not in trailers:
            trailers["KB-Tier"] = tier
        message = _message(op, summary, version, target, trailers, pages=pages)
        _write_pending(root, op, target, summary)
        sha = _commit_paths(root, sorted(set(chosen)), message)
        _clear(root, "pending.json")
        if sha:
            print(f"committed {message.splitlines()[0]}")
            if push:
                push_main(root, quiet=True)
            share_autodeploy(f"commit_op {op} {target}", root)
        return sha


def share_autodeploy(reason, root=ROOT, foreground=False):
    """Ask the configured publisher to publish main soon (`Publisher.request_publish`); never raises; no publisher = nothing.

    With the Cloudflare publisher that nudges the deploy owner (touch `.cache/share/wake`); `KB_SHARE_DIRECT=1` (the user
    only) keeps the old path: `share deploy-main` from here, detached by default, in the foreground for the nightly sync."""
    try:
        from kb_distillery import hosting
        hosting.current(root=root).request_publish(reason, root, foreground)
    except Exception as e:  # noqa: BLE001 — a deploy hiccup must never fail a knowledge op
        print(f"note: share autodeploy not triggered — {e}")


def _write_pending(root, op, target, summary):
    with open(os.path.join(_ops_dir(root), "pending.json"), "w") as f:
        json.dump({"op": op, "target": target, "summary": summary,
                   "at": datetime.datetime.now().isoformat(timespec="seconds")}, f)


def _read(root, name):
    path = os.path.join(root, OPS_DIR, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _clear(root, name):
    with contextlib.suppress(FileNotFoundError):
        os.remove(os.path.join(root, OPS_DIR, name))


def current_session(root=ROOT):
    return _read(root, "current.json")


# ---------- free-form edit sessions ----------

def begin(op, target, summary=None, root=ROOT):
    if op not in cp.KB_OPS or op in ("think", "undo", "restore"):
        raise OpsError(f"begin takes a writing op (import, catalog, digest, refine, distill), not {op!r}")
    if current_session(root):
        s = current_session(root)
        raise OpsError(f"an ops session is already open: {s['op']} {s['target']} — commit or abort it")
    _require_main(root)
    sync_human(root)
    session = {"op": op, "target": target, "summary": summary,
               "started": datetime.datetime.now().isoformat(timespec="seconds"),
               "baseline": knowledge_state(root)}
    with open(os.path.join(_ops_dir(root), "current.json"), "w") as f:
        json.dump(session, f)
    print(f"ops session open: {op} {target} — edit, then `pixi run ops -- commit`")
    return session


def commit(summary=None, root=ROOT):
    s = current_session(root)
    if not s:
        raise OpsError("no ops session open — use `pixi run ops -- begin <op> <target> \"why\"`")
    baseline = {k: tuple(v) if v else None for k, v in s["baseline"].items()}
    paths = changed_since(baseline, root)
    sha = commit_op(s["op"], s["target"], summary or s.get("summary"), paths=paths, root=root)
    _clear(root, "current.json")
    if not sha:
        print("nothing changed since begin — session closed")
    return sha


def abort(root=ROOT):
    s = current_session(root)
    if not s:
        print("no ops session open")
        return []
    baseline = {k: tuple(v) if v else None for k, v in s["baseline"].items()}
    paths = changed_since(baseline, root)
    _clear(root, "current.json")
    print(f"ops session closed without commit; {len(paths)} files still modified:")
    for p in paths:
        print(f"  {p}")
    return paths


# ---------- undo / restore ----------

def _restorable(path):
    return path not in RESTORE_EXCLUDED and not is_index_path(path) and any(path == p.rstrip("/") or (p.endswith("/") and path.startswith(p)) for p in RESTORABLE_PATHS)


def _first_parent(root, ref="main"):
    return _git(root, "rev-list", "--first-parent", ref).stdout.split()


def _blob(root, rev, path):
    proc = _git(root, "rev-parse", "-q", "--verify", f"{rev}:{path}")
    return proc.stdout.strip() if proc.returncode == 0 else None


def _append_log(root, line):
    """undo/restore log themselves before commit_op (which then sees a dirty log and adds nothing)."""
    op, _, rest = line.partition(" | ")
    kblog.append(root, op, rest)


def _set_from(root, rev, path):
    """Make the working file equal to rev:path (delete when absent there)."""
    full = os.path.join(root, path)
    if _blob(root, rev, path) is None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(full)
        return
    data = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=root, capture_output=True, check=True).stdout
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)


def undo(rev, root=ROOT):
    """Reverse one agent knowledge step as a new kb(undo) commit (restorable files only)."""
    with ops_lock(root):
        _require_main(root)
        sha = _git(root, "rev-parse", "--verify", f"{rev}^{{commit}}", check=True).stdout.strip()
        if sha not in _first_parent(root):
            raise OpsError("only knowledge steps on main's first-parent history can be undone")
        body = _git(root, "log", "-1", "--format=%B", sha).stdout
        c = cp.parse_message(body)
        if c.kind != "kb":
            raise OpsError(f"{sha[:9]} is not a knowledge step ({c.subject!r}) — infra changes are reverted by a PR")
        if c.scope == "think":
            raise OpsError("kb(think) commits are your own edits in think/ — agents never undo them")
        if c.scope == "import":
            raise OpsError("kb(import) only adds raw/ inbox files — triage the inbox instead (raw/ is immutable)")
        if _git(root, "log", "--first-parent", "--format=%H", f"--grep=^KB-Reverts: {sha}", "main").stdout.strip():
            raise OpsError(f"{sha[:9]} was already undone")
        parent = f"{sha}^"
        files = [l.split("\t", 1)[1] for l in
                 _git(root, "diff-tree", "-r", "--no-renames", "--name-status", parent, sha).stdout.splitlines()
                 if "\t" in l]
        files = [f for f in files if _restorable(f)]
        if not files:
            raise OpsError("that step changed nothing undo may touch (wiki/, meta/aliases.tsv, meta/chats/)")
        dirty = set(changed_paths(root)["knowledge"])
        if dirty & set(files):
            raise OpsError(f"uncommitted edits on files this undo touches: {sorted(dirty & set(files))[:5]}")
        conflicts = [f for f in files if _blob(root, "HEAD", f) != _blob(root, sha, f)]
        if conflicts:
            later = _git(root, "log", "--first-parent", "--format=%h %s", f"{sha}..HEAD", "--", *conflicts).stdout
            raise OpsError("later steps changed the same files — undo those first (newest first):\n" + later.strip())
        for f in files:
            _set_from(root, parent, f)
        run_lint(root)
        target = c.trailers.get("KB-Target", "?")
        _append_log(root, f"undo | {c.subject} ← {sha[:12]}")
        return commit_op("undo", target, f"revert {cp.fmt_version(c.version)} {c.summary}",
                         paths=files, lint=False, trailers={"KB-Reverts": sha}, root=root, _locked=True)


def restore(tag, root=ROOT):
    """Bring the restorable set back to snapshot `tag` as one new kb(restore) commit."""
    with ops_lock(root):
        _require_main(root)
        if not cp.KB_TAG.match(tag):
            raise OpsError("restore takes a snapshot tag kb-x.y.z (see `pixi run ops -- log --snapshots`)")
        if _git(root, "cat-file", "-t", tag).stdout.strip() != "tag":
            raise OpsError(f"{tag} is not an annotated snapshot tag")
        dirty = [p for p in changed_paths(root)["knowledge"] if _restorable(p)]
        if dirty:
            raise OpsError(f"commit or discard edits under wiki/ first: {dirty[:5]}")
        diff = _git(root, "diff", "--name-only", "--no-renames", tag, "HEAD", "--", *RESTORABLE_PATHS,
                 *(f":(exclude){p}" for p in RESTORE_EXCLUDED),
                 *(f":(exclude,glob){p}" for p in RESTORE_EXCLUDED_GLOBS)).stdout.split("\n")
        files = [f for f in diff if f]
        if not files:
            print(f"wiki already matches {tag}")
            return None
        for f in files:
            _set_from(root, tag, f)
        run_lint(root)
        _append_log(root, f"restore | back to {tag} ({len(files)} files)")
        return commit_op("restore", tag, f"back to {tag}", paths=files, lint=False,
                         trailers={"KB-Snapshot": tag}, root=root, _locked=True)


# ---------- snapshots ----------

def snapshot(label=None, root=ROOT):
    """Annotated tag kb-x.y.z on the newest knowledge step of main."""
    version = cp.last_version(root, "main")
    if not version:
        raise OpsError("no knowledge version on main yet — nothing to snapshot")
    sha = cp.version_commit(root, version, "main")
    name = "kb-" + cp.fmt_version(version)
    existing = _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{name}^{{commit}}")
    if existing.returncode == 0:
        print(f"{name} already exists{' (same commit)' if existing.stdout.strip() == sha else ''}")
        return name
    head = _git(root, "rev-parse", "main").stdout.strip()
    if head != sha:
        print(f"note: main's tip is an infra merge — snapshot goes on the last knowledge step {sha[:9]}")
    _git(root, "tag", "-a", name, sha, "-m", label or "snapshot", check=True, env=identity_env(root))
    print(f"snapshot {name}{' — ' + label if label else ''}")
    return name


def snapshots(root=ROOT):
    out = _git(root, "for-each-ref", "--sort=-creatordate", "refs/tags/kb-*",
               "--format=%(refname:short)\x1f%(creatordate:short)\x1f%(contents:subject)").stdout
    return [dict(zip(("tag", "date", "label"), line.split("\x1f"))) for line in out.splitlines() if line]


# ---------- catching up with origin/main ----------

PREFER = {"local": "theirs", "origin": "ours"}   # rebase -X: `theirs` = the step being replayed


def update_main(root=ROOT, prefer=None):
    """Bring local main up to origin/main without losing local knowledge steps.

    behind only → fast-forward. Diverged (a PR merged on GitHub while knowledge steps were
    still local) → replay the unpushed commits on top of origin/main, but only when every one
    of them is a knowledge-only kb(...) step; they were never pushed, and a PR merge carries no
    version, so their kb-x.y.z stay valid. A conflict aborts and leaves main untouched — unless
    the user chose a side: `prefer="local"` keeps the replayed step's text in every conflicting
    hunk (another session pushed the same pages from an older base), `prefer="origin"` keeps
    what is on GitHub. Generated files (index.md, meta/corpus.tsv) are rebuilt by the next lint
    either way. Returns "up-to-date" | "fast-forward" | "replayed N[, kept …]"; raises OpsError.
    """
    if prefer not in (None, *PREFER):
        raise OpsError(f"prefer must be local or origin, not {prefer!r}")
    _require_main(root)
    if _git(root, "fetch", "-q", "origin", "main").returncode != 0:
        raise OpsError("could not fetch origin/main")
    counts = _git(root, "rev-list", "--left-right", "--count", "origin/main...main").stdout.split()
    behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    if not behind:
        return "up-to-date"
    if not ahead:
        ff = _git(root, "merge", "--ff-only", "origin/main")
        if ff.returncode != 0:
            raise OpsError(f"fast-forward failed (local edits in the way?): {ff.stderr.strip()}")
        return "fast-forward"
    local = _git(root, "log", "--format=%H%x1f%B%x1e", "origin/main..main").stdout.split("\x1e")
    for rec in filter(None, (r.strip("\n") for r in local)):
        sha, body = rec.split("\x1f", 1)
        files = [f for f in _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", sha)
                 .stdout.split("\0") if f]
        if cp.parse_message(body).kind != "kb" or any(lane_of(f) != "knowledge" for f in files):
            raise OpsError(f"local main has a non-knowledge commit {sha[:9]} — sort it out by hand")
    # --autostash: unrelated uncommitted edits (e.g. .obsidian settings) are set aside and restored
    strategy = ["-X", PREFER[prefer]] if prefer else []
    replay = _git(root, "rebase", "--autostash", *strategy, "origin/main")
    if replay.returncode != 0:
        _git(root, "rebase", "--abort")
        raise OpsError(f"replaying local knowledge steps on origin/main conflicted — main left as it was"
                       + ("" if prefer else " (`ops sync --prefer local|origin` picks a side)") + ":\n"
                       f"{(replay.stdout + replay.stderr).strip()[-400:]}")
    return f"replayed {ahead}" + (f", kept {prefer} text in conflicts" if prefer else "")


# ---------- nightly sync ----------

def open_researcher_sessions(root):
    """Slugs of researcher-profile sessions whose session.json status is "open" (closed ones are kept on disk)."""
    d = os.path.join(root, "meta", ".researcher")
    if not os.path.isdir(d):
        return []
    open_ = []
    for slug in sorted(os.listdir(d)):
        path = os.path.join(d, slug, "session.json")
        try:
            with open(path, encoding="utf-8") as f:
                if json.load(f).get("status") == "open":
                    open_.append(slug)
        except (OSError, ValueError):
            continue
    return open_


def _researcher_open(root):
    return bool(open_researcher_sessions(root))


def sync(push=True, dry_run=False, root=ROOT, prefer=None):
    """Nightly: commit human think/ edits, then labelled leftovers, then push main + tags —
    then the hygiene checks (src/kb_distillery/ops/hygiene.py) and the nightly report (src/kb_distillery/ops/nightly_report.py),
    mailed per `[notify] mode` and logged to meta/.ops/runs.jsonl (src/kb_distillery/ops/runlog.py).

    Hygiene never changes the outcome: a crash inside it is printed and swallowed, and when
    the sync itself raises the email carries the traceback tail before the error propagates.
    """
    skipped = None
    head = _git(root, "rev-parse", "-q", "--verify", "main").stdout.strip()
    try:
        rc = _sync(push, dry_run, root, prefer)
    except OpsError as e:
        print(f"skipped: {e}")
        skipped, rc = str(e), 0
    except Exception:
        import traceback
        sync_hygiene(root, failed=True, error=traceback.format_exc(), head_before=head)
        raise
    if not dry_run:
        sync_hygiene(root, failed=rc != 0, error=skipped, head_before=head, rc=rc)
    return rc


def _sync_facts(root, head_before, rc, failed, error):
    """What the sync did, read back from the repo: commits made, whether main is on origin."""
    head = _git(root, "rev-parse", "-q", "--verify", "main").stdout.strip()
    made = _git(root, "rev-list", "--count", f"{head_before}..main").stdout.strip() if head_before and head else ""
    pushed = None
    if _git(root, "rev-parse", "-q", "--verify", "origin/main").returncode == 0:
        pushed = _git(root, "rev-list", "--count", "origin/main..main").stdout.strip() == "0"
    return {"rc": rc, "failed": bool(failed), "skipped": bool(error and not failed),
            "error": (error or "")[-4000:], "commits": int(made) if made.isdigit() else None,
            "pushed": pushed, "head": head[:12]}


def _deploy_state(root):
    try:
        with open(os.path.join(root, ".cache", "share", "status.json"), encoding="utf-8") as f:
            st = json.load(f)
        return {k: st.get(k) for k in ("state", "sha", "at", "kb_version")}
    except (OSError, ValueError):
        return None


def _nightly_metrics(root):
    """Session logs → meta/.ops/metrics, then a copy to D1 when it is configured (kb_distillery.metrics).
    Returns (status, fields) for the run log; never raises — Claude Code deletes old logs, so a
    missed night only matters when the logs outlive the retention, and they now keep a year."""
    try:
        from kb_distillery.metrics import d1, sessions, store
        recs = store.merge_sessions(list(sessions.scan()), root)
        pushed = None
        if d1.database_id(root):
            pushed = d1.push(root) == 0
        return ("ok" if pushed is not False else "warn"), {"sessions": len(recs), "d1": pushed}
    except Exception as e:  # noqa: BLE001 — metrics must never fail the sync
        print(f"note: metrics ingest failed — {type(e).__name__}: {e}")
        return "warn", {"error": f"{type(e).__name__}: {e}"}


def sync_hygiene(root=ROOT, failed=False, error=None, head_before=None, rc=None):
    """Run the hygiene checks + work threads after a nightly sync, mail the nightly report (every
    night in digest mode, else only with findings or a failed / skipped sync) and append the run
    to meta/.ops/runs.jsonl. Never raises; KB_NO_HYGIENE=1 disables it (tests)."""
    if os.environ.get("KB_NO_HYGIENE"):
        return None
    run = None
    try:
        from . import hygiene, runlog
        from kb_distillery.ops import notify
        run = runlog.Run(root)
        facts = _sync_facts(root, head_before, rc, failed, error)
        run.set(sync={k: v for k, v in facts.items() if k != "error"})
        if facts["error"]:
            run.step("sync", "error", error=facts["error"].strip().splitlines()[-1][:300])
        report = hygiene.run(root)
        if error and not failed:
            report.findings.append(hygiene.Finding("error", "sync-skipped", error, "pixi run daily-sync   # after fixing"))
        print(report.text())
        run.step("hygiene", "error" if report.errors else "warn" if report.findings else "ok",
                 checks=len(report.checks), elapsed=round(report.elapsed, 2))
        m_status, m_fields = _nightly_metrics(root)
        run.step("metrics", m_status, **m_fields)
        tail = notify.log_tail(NIGHTLY_LOG) if (failed or error) else None
        doc, threads = None, []
        try:
            from . import nightly_report
            from . import threads as threads_mod
            threads = threads_mod.collect(root)
            doc = nightly_report.build(root, report, threads, sync=facts, log_tail=tail)
            run.step("report", doc.status, threads=len(threads))
        except Exception as e:  # noqa: BLE001 — a broken report falls back to the plain hygiene mail
            print(f"note: nightly report failed — {type(e).__name__}: {e}")
            run.step("report", "error", error=f"{type(e).__name__}: {e}")
        outcome = notify.notify_report(report, root, sync_failed=failed or bool(error), error=error, tail=tail, doc=doc)
        run.step("notify", "ok" if outcome in ("sent", "clean", "throttled") else "warn", outcome=outcome)
        run.set(hygiene=report.as_dict(), threads=[t.as_dict() for t in threads], notify=outcome,
                deploy=_deploy_state(root))
        run.finish(status=doc.status if doc else
                   "error" if failed or report.errors else "warn" if report.findings else "ok")
        return outcome
    except Exception as e:  # noqa: BLE001 — hygiene must never fail the sync
        print(f"note: hygiene checks failed — {type(e).__name__}: {e}")
        if run is not None:
            try:
                run.step("hygiene", "error", error=f"{type(e).__name__}: {e}").finish(status="error")
            except Exception:  # noqa: BLE001 — the log is best effort
                pass
        return None


def _sync(push, dry_run, root, prefer=None):
    with ops_lock(root, blocking=False):
        if current_branch(root) != "main" or in_progress(root):
            print("skipped: primary checkout is not on main or git is mid-operation")
            return 0
        if dry_run:
            lanes = changed_paths(root)
            print(f"dry-run: knowledge changes: {len(lanes['knowledge'])}, tooling (not synced): {len(lanes['tooling'])}")
            return 0
        sync_human(root)
        ingest, distill = has_open_sessions(root)
        if ingest or distill or current_session(root) or _researcher_open(root):
            print("open sessions — leftovers wait for the next sync")
        else:
            leftovers = [p for p in changed_paths(root)["knowledge"] if not is_human_path(p)]
            if leftovers:
                pending = _read(root, "pending.json") or {}
                commit_op(pending.get("op", "refine"), pending.get("target", "leftovers"),
                          pending.get("summary") or "unlabeled leftovers", paths=leftovers,
                          root=root, _locked=True, push=False)
        if push and _git(root, "remote").stdout.strip():
            state = update_main(root, prefer=prefer)
            if state != "up-to-date":
                print(f"caught up with origin/main ({state})")
            proc = _git(root, "push", "origin", "main", "--follow-tags")
            print((proc.stdout + proc.stderr).strip() or "pushed")
            share_autodeploy("nightly sync", root, foreground=True)  # backstop; never fails the sync
            return proc.returncode
        return 0


# ---------- reporting ----------

def log(n=20, kind=None, root=ROOT):
    from .history import timeline
    for row in timeline(root, limit=n * 3):
        if kind == "kb" and row["kind"] != "kb":
            continue
        if kind == "infra" and row["kind"] == "kb":
            continue
        label = f"kb-{row['kb_version']}" if row["kb_version"] and row["kind"] == "kb" else \
            (f"#{row['pr']}" if row["pr"] else ("retro" if row["kind"] == "pr-merge" else row["kind"]))
        snap = f"  ⟵ {row['snapshot_tag']}" if row["snapshot_tag"] else ""
        undone = f"  (undone by {row['reverted_by'][:9]})" if row["reverted_by"] else ""
        print(f"{row['short']}  {row['date'][:10]}  {label:<11} {row['subject']}{snap}{undone}")
        n -= 1
        if n <= 0:
            break


def hooks_installed(root):
    """Do the kb's git hooks really run? `core.hooksPath` (absolute, or relative to the work tree top, as git reads it)
    must point at a folder whose pre-commit, commit-msg and pre-push are executable: git skips any other silently.
    No comparison with one fixed path: a kb outside the engine gets an absolute one, a kb inside a relative one."""
    configured = _git(root, "config", "core.hooksPath").stdout.strip()
    if not configured:
        return False
    top = _git(root, "rev-parse", "--show-toplevel").stdout.strip() or root
    folder = os.path.normpath(os.path.join(top, os.path.expanduser(configured)))
    return all(os.path.isfile(os.path.join(folder, n)) and os.access(os.path.join(folder, n), os.X_OK)
               for n in ("pre-commit", "commit-msg", "pre-push"))


def status(root=ROOT):
    from .migrate import pending_migrations
    lanes = changed_paths(root)
    ingest, distill = has_open_sessions(root)
    last = cp.last_version(root, "main")
    hooks = hooks_installed(root)
    unpushed = _git(root, "rev-list", "--count", "origin/main..main").stdout.strip() or "?"
    snaps = snapshots(root)
    from kb_distillery.vault.schema import GIT_POLICY_MODE, OPS_STRICT, SCHEMA_VERSION
    print(f"branch: {current_branch(root) or 'detached'}   knowledge version: "
          f"{'kb-' + cp.fmt_version(last) if last else 'none yet'}   next: kb-{cp.fmt_version(cp.next_version(root, 'main'))}")
    print(f"schema: {SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}   pending migrations: {len(pending_migrations(root))}")
    print(f"last snapshot: {snaps[0]['tag'] + ' (' + snaps[0]['date'] + ')' if snaps else 'none'}   unpushed commits: {unpushed}")
    print(f"uncommitted: knowledge {len(lanes['knowledge'])} · tooling {len(lanes['tooling'])} · other {len(lanes['other'])}")
    sessions = [f"ingest {s.get('sha1')}" for s in ingest] + [f"distill {s.get('think_path')}" for s in distill]
    if current_session(root):
        s = current_session(root)
        sessions.append(f"ops {s['op']} {s['target']}")
    sessions += [f"researcher {slug}" for slug in open_researcher_sessions(root)]
    print(f"open sessions: {', '.join(sessions) or 'none'}")
    print(f"git hooks: {'installed (' + GIT_POLICY_MODE + ')' if hooks else 'not installed — distill hooks install'}"
          f"   guard strict: {OPS_STRICT}")
    nightly = nightly_status(root)
    print(f"nightly sync: {nightly['summary']}" + (f" — {nightly['hint']}" if nightly["hint"] else ""))
    print_worktree_report(root)
    if _read(root, "pending.json"):
        print(f"pending commit label: {_read(root, 'pending.json')}")


def print_worktree_report(root=ROOT):
    """One line per leftover worktree (merged, or a Claude session's worktree-* branch) — warn only."""
    from kb_distillery.git.ship import stale_worktrees  # lazy: ship imports ops
    rows = [r for r in stale_worktrees(root) if not r["current"]]   # the one we stand in is not "left behind"
    if not rows:
        return
    merged = [r for r in rows if r["merged"]]
    session = [r for r in rows if not r["merged"]]
    if merged:
        print(f"stale worktrees: {len(merged)} merged — pixi run ship -- prune --apply"
              + ("".join(f"\n  {r['branch']}" + (f" ({len(r['dirty'])} uncommitted files, kept)" if r['dirty'] else "")
                         for r in merged)))
    if session:
        print(f"session worktrees: {len(session)} on worktree-* branches — "
              f"`pixi run ship -- start <feature>` inside it, or `ship -- prune --drop <branch>`"
              + "".join(f"\n  {r['branch']} ({r['ahead']} commits, {len(r['dirty'])} uncommitted files)" for r in session))

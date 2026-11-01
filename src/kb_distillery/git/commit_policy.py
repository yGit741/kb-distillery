#!/usr/bin/env python3
"""KB Conventional Commits — one validator for githooks, ship, ops and history curation.

Knowledge commits (directly on main, one per operation, versioned):
    kb(<op>): <summary> (kb-x.y.z)
    subject = what the step did, in words; body = the wiki pages it touched
    trailers: KB-Version, KB-Op, KB-Target (a slug, never a hash); KB-Reverts (undo);
              KB-Snapshot (restore); KB-Tier easy|full|deep (digest)

Infra commits (on infra/<feature> branches, unversioned; scope always required):
    <schema|paradigm|feat|fix|chore>(<component>): <imperative summary>
    schema = note rules (+ migration) · feat = new capability · fix = wrong behaviour ·
    chore = no behaviour change (config, ignore files, docs, tests, refactors)
PR merges on main (real merge commits, never squash):
    <infra subject> (#N)          — or "(retro)" in the curated past
    the title's type is the highest of its commits (paradigm › schema › feat › fix › chore);
    the merge body lists the branch's commits so the log reads without GitHub
    schema/paradigm merges also carry KB-Version x.(y+1).0 / (x+1).0.0

Git hooks:
    python3 -m kb_distillery.git.commit_policy msg <commit-msg-file>     # commit-msg
    python3 -m kb_distillery.git.commit_policy push <remote> <url>       # pre-push (ref lines on stdin)
Mode: env KB_POLICY=warn|enforce, default schema.GIT_POLICY_MODE.
"""
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from kb_distillery.paths import THINK_PATH, vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()
from kb_distillery.core.schema import GIT_POLICY_MODE, SCHEMA_VERSION, is_kb_tooling, lane_of

KB_OPS = ("import", "catalog", "digest", "refine", "distill", "think", "undo", "restore")
INFRA_TYPES = ("feat", "fix", "chore", "schema", "paradigm")
TYPE_RANK = {"chore": 0, "fix": 1, "feat": 2, "schema": 3, "paradigm": 4}  # a PR is titled by its highest
KB_TIERS = ("easy", "full", "deep")
MAX_SUMMARY = 72
MAX_SUBJECT = 100          # the whole first line, prefix and (kb-x.y.z) / (#N) suffix included
PR_SUFFIX_ROOM = len(" (#9999)")
HASH_LIKE = re.compile(r"^[0-9a-f]{7,40}$")
ZERO_SHA = "0" * 40

_VERSION = r"(?P<version>\d+\.\d+\.\d+)"
SUBJECT_KB = re.compile(rf"^kb\((?P<scope>{'|'.join(KB_OPS)})\): (?P<summary>\S.*?) \(kb-{_VERSION}\)$")
_INFRA = rf"(?P<type>{'|'.join(INFRA_TYPES)})\((?P<scope>[a-z0-9-]+)\)(?P<breaking>!)?: (?P<summary>\S.*?)"
SUBJECT_INFRA = re.compile(rf"^{_INFRA}$")
SUBJECT_PR_MERGE = re.compile(rf"^{_INFRA} \((#(?P<pr>\d+)|(?P<retro>retro))\)$")
SUBJECT_SYNC_MAIN = re.compile(r"^Merge (remote-tracking )?branch '(origin/)?main' into infra/[a-z0-9-]+$")
TRAILER = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9-]*): (?P<value>.+)$")
KB_TAG = re.compile(r"^kb-\d+\.\d+\.\d+$")


@dataclass
class Commit:
    subject: str
    kind: str  # kb | infra | pr-merge | sync-merge | unknown
    type: str = ""
    scope: str = ""
    summary: str = ""
    version: tuple = None
    pr: int = None
    retro: bool = False
    trailers: dict = field(default_factory=dict)


def parse_version(text):
    m = re.fullmatch(r"(?:kb-)?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def fmt_version(v):
    return f"{v[0]}.{v[1]}.{v[2]}"


def parse_trailers(message):
    """Key: value lines of the last paragraph (git trailer convention)."""
    paras = [p for p in re.split(r"\n\s*\n", message.strip()) if p.strip()]
    if len(paras) < 2:
        return {}
    out = {}
    for line in paras[-1].splitlines():
        m = TRAILER.match(line.strip())
        if not m:
            return {}
        out[m.group("key")] = m.group("value").strip()
    return out


def strip_comments(message):
    return "\n".join(l for l in message.splitlines() if not l.startswith("#")).strip()


def parse_message(message):
    message = strip_comments(message)
    subject = message.splitlines()[0].strip() if message else ""
    trailers = parse_trailers(message)
    m = SUBJECT_KB.match(subject)
    if m:
        return Commit(subject, "kb", "kb", m.group("scope"), m.group("summary"),
                      parse_version(m.group("version")), trailers=trailers)
    m = SUBJECT_PR_MERGE.match(subject)
    if m:
        return Commit(subject, "pr-merge", m.group("type"), m.group("scope") or "", m.group("summary"),
                      parse_version(trailers.get("KB-Version")),
                      int(m.group("pr")) if m.group("pr") else None, bool(m.group("retro")), trailers)
    m = SUBJECT_INFRA.match(subject)
    if m:
        return Commit(subject, "infra", m.group("type"), m.group("scope") or "", m.group("summary"),
                      trailers=trailers)
    if SUBJECT_SYNC_MAIN.match(subject):
        return Commit(subject, "sync-merge", trailers=trailers)
    return Commit(subject, "unknown", trailers=trailers)


def _is_kb_repo(root):
    """A knowledge base's own repo: kb.toml at its top, and not the shared think repo."""
    return os.path.isfile(os.path.join(root, "kb.toml")) and os.path.realpath(root) != os.path.realpath(THINK_PATH)


def _is_kb_chore(c, paths, kb_repo):
    """`chore(<scope>)` on a kb repo's main that touches only kb tooling paths (hooks, CLAUDE.md, kb.toml, …)."""
    return bool(kb_repo and c.kind == "infra" and c.type == "chore" and paths and all(is_kb_tooling(p) for p in paths))


def check_message(message, branch, paths, is_merge=False, think_repo=False, kb_repo=False):
    """Violations for one commit about to be made on `branch` touching `paths`."""
    c = parse_message(message)
    v = []
    lanes = {p: "knowledge" if think_repo else lane_of(p) for p in paths}
    on_main = branch == "main"
    if c.kind == "unknown":
        return [f"subject does not follow KB Conventional Commits: {c.subject!r}"]
    if c.summary and len(c.summary) > MAX_SUMMARY:
        v.append(f"summary longer than {MAX_SUMMARY} chars")
    if len(c.subject) > MAX_SUBJECT:
        v.append(f"subject line longer than {MAX_SUBJECT} chars")
    if is_merge:
        if on_main and c.kind != "pr-merge":
            v.append("merge into main must be titled '<type(scope): summary> (#N)'")
        if not on_main and c.kind not in ("sync-merge", "pr-merge"):
            v.append("only 'Merge branch main into infra/<f>' merges are allowed on branches")
        if c.kind == "pr-merge" and c.type in ("schema", "paradigm") and not c.version:
            v.append(f"{c.type} merge needs a KB-Version trailer (bumped schema version)")
        if c.kind == "pr-merge" and c.type not in ("schema", "paradigm") and c.version:
            v.append("only schema/paradigm merges carry KB-Version")
        return v
    if c.kind in ("pr-merge", "sync-merge"):
        return v + ["merge subject used on a non-merge commit"]
    if c.kind == "kb":
        if not on_main:
            v.append("kb(...) commits go directly on main")
        if c.trailers.get("KB-Op") != c.scope:
            v.append(f"KB-Op trailer must equal the scope ({c.scope})")
        if parse_version(c.trailers.get("KB-Version")) != c.version:
            v.append("KB-Version trailer must equal the (kb-x.y.z) subject suffix")
        if c.scope == "undo" and not c.trailers.get("KB-Reverts"):
            v.append("kb(undo) needs a KB-Reverts trailer")
        if c.scope == "restore" and not c.trailers.get("KB-Snapshot"):
            v.append("kb(restore) needs a KB-Snapshot trailer")
        if HASH_LIKE.match(c.trailers.get("KB-Target", "")):
            v.append("KB-Target must be a slug or name, not a hash or session id")
        tier = c.trailers.get("KB-Tier")
        if tier and (c.scope != "digest" or tier not in KB_TIERS):
            v.append(f"KB-Tier ({' | '.join(KB_TIERS)}) belongs on kb(digest) only")
        bad = [p for p, lane in lanes.items() if lane != "knowledge"]
        if bad:
            v.append(f"kb commits may only touch knowledge paths: {bad[:5]}")
        # In the shared think repo (kbs/think, its own history) every path is a think note.
        think = list(paths) if think_repo else [p for p in paths if p.startswith("think/")]
        if c.scope == "think" and len(think) != len(paths):
            v.append("kb(think) commits only touch think/")
        if c.scope != "think" and think:
            v.append("agent kb commits must not include think/ (human edits get their own kb(think) commit)")
        return v
    # infra
    kb_chore = on_main and _is_kb_chore(c, paths, kb_repo)   # a kb repo's own tooling commits straight onto its main
    if on_main and not kb_chore:
        v.append(f"{c.type} commits go through an infra/<feature> branch + PR, not main")
    if kb_chore:
        pass
    elif c.type not in ("schema", "paradigm"):
        bad = [p for p, lane in lanes.items() if lane != "tooling"]
        if bad:
            v.append(f"{c.type} commits may only touch tooling paths (knowledge/other: {bad[:5]})")
    else:
        bad = [p for p, lane in lanes.items() if lane == "other"]
        if bad:
            v.append(f"paths outside both lanes: {bad[:5]}")
    if c.version:
        v.append("infra commits are not versioned (no KB-Version)")
    return v


def highest_type(subjects):
    """The highest-ranked infra type among `subjects` (merges and non-infra lines ignored)."""
    types = [c.type for c in map(parse_message, subjects) if c.kind == "infra"]
    return max(types, key=TYPE_RANK.get) if types else None


def check_pr_title(title, subjects):
    """Violations for a PR title over the branch's commit `subjects` (it becomes '<title> (#N)')."""
    c = parse_message(title)
    if c.kind != "infra":
        return [f"PR title must be 'type(scope): summary', got {title!r}"]
    v = []
    top = highest_type(subjects)
    if top and TYPE_RANK[c.type] < TYPE_RANK[top]:
        v.append(f"PR title type {c.type!r} is below its highest commit type {top!r} — title it {top}(…)")
    if len(title) + PR_SUFFIX_ROOM > MAX_SUBJECT:
        v.append(f"PR title too long: the merge subject '<title> (#N)' must fit {MAX_SUBJECT} chars")
    return v


# ---------- git-backed checks ----------

def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def last_version(root=ROOT, rev="HEAD", limit=2000):
    """Most recent KB-Version on the first-parent chain of `rev`, or None."""
    out = _git(root, "log", "--first-parent", f"-n{limit}", "--format=%B%x1e", rev, "--")
    if out.returncode != 0:
        return None
    for body in out.stdout.split("\x1e"):
        v = parse_version(parse_trailers(body).get("KB-Version"))
        if v:
            return v
    return None


def version_commit(root, version, rev="HEAD", limit=2000):
    """sha of the first-parent commit on `rev` whose KB-Version equals `version`."""
    out = _git(root, "log", "--first-parent", f"-n{limit}", "--format=%H%x1f%B%x1e", rev, "--")
    for rec in out.stdout.split("\x1e"):
        if "\x1f" not in rec:
            continue
        sha, body = rec.strip("\n").split("\x1f", 1)
        if parse_version(parse_trailers(body).get("KB-Version")) == tuple(version):
            return sha
    return None


def next_version(root=ROOT, rev="HEAD", schema_version=SCHEMA_VERSION):
    """Version for the next kb commit on top of `rev`."""
    last = last_version(root, rev)
    x, y = schema_version
    if last and (last[0], last[1]) == (x, y):
        return (x, y, last[2] + 1)
    if last and (last[0], last[1]) > (x, y):
        return (last[0], last[1], last[2] + 1)
    return (x, y, 1)


def bumped_version(current, kind):
    """KB-Version a schema/paradigm merge sets after `current`; None when there is no version yet."""
    if not current:
        return None
    x, y, _ = current
    return (x, y + 1, 0) if kind == "schema" else (x + 1, 0, 0)


def merge_version(branch_schema, current, kind):
    """KB-Version for a schema/paradigm PR merge: the PR's own SCHEMA_VERSION with step 0.

    Raises ValueError when the PR did not bump SCHEMA_VERSION the right way.
    """
    new = (branch_schema[0], branch_schema[1], 0)
    want = bumped_version(current, kind)
    if want and new != want:
        raise ValueError(f"{kind} PR must set SCHEMA_VERSION to {want[0]}.{want[1]} "
                         f"(current knowledge version {fmt_version(current)}), found {new[0]}.{new[1]}")
    return new


def _is_ancestor(root, old, new):
    return _git(root, "merge-base", "--is-ancestor", old, new).returncode == 0


def check_push_range(root, old, new, ref="refs/heads/main"):
    """Violations for updating `ref` from `old` to `new` (pre-push)."""
    v = []
    if ref.startswith("refs/tags/"):
        return check_tag(root, ref[len("refs/tags/"):], new)
    if new == ZERO_SHA:
        return ["deleting main is not allowed"] if ref == "refs/heads/main" else []
    if ref != "refs/heads/main":
        return v
    if old != ZERO_SHA and not _is_ancestor(root, old, new):
        if os.environ.get("KB_ALLOW_REWRITE") != "1":
            return ["non-fast-forward push to main (history rewrite) — set KB_ALLOW_REWRITE=1 yourself if intended"]
        # allowed rewrite: validate the new commits from the common ancestor
        old = _git(root, "merge-base", old, new).stdout.strip() or ZERO_SHA
    rng = new if old == ZERO_SHA else f"{old}..{new}"
    log = _git(root, "log", "--first-parent", "--reverse", "--format=%H%x1f%P%x1f%B%x1e", rng, "--")
    prev = last_version(root, old) if old != ZERO_SHA else None
    for rec in log.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, parents, body = rec.split("\x1f", 2)
        c = parse_message(body)
        short = sha[:9]
        nparents = len(parents.split())
        if nparents >= 2:
            if c.kind != "pr-merge":
                v.append(f"{short}: merge on main must be a PR merge '<type(scope): summary> (#N)'")
            elif c.type in ("schema", "paradigm"):
                want = bumped_version(prev, c.type)
                if want and c.version != want or not want and (not c.version or c.version[2] != 0):
                    v.append(f"{short}: {c.type} merge must set KB-Version "
                             f"{fmt_version(want) if want else 'x.y.0'}")
                prev = c.version or prev
            elif c.version:
                v.append(f"{short}: only schema/paradigm merges carry KB-Version")
            continue
        if c.kind != "kb":
            files = [f for f in _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", sha).stdout.split("\0") if f]
            if _is_kb_chore(c, files, _is_kb_repo(root)):    # unversioned: the kb-x.y.z sequence skips it
                if c.trailers.get("KB-Version"):
                    v.append(f"{short}: infra commits are not versioned (no KB-Version)")
                continue
            v.append(f"{short}: only kb(...) commits or PR merges may land on main ({c.subject!r})")
            continue
        if prev:
            want = (prev[0], prev[1], prev[2] + 1)
            if c.version != want:
                v.append(f"{short}: version {fmt_version(c.version)} should be {fmt_version(want)}")
        prev = c.version
        files = [f for f in _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", sha).stdout.split("\0") if f]
        bad = [f for f in files if lane_of(f) != "knowledge"]
        if bad:
            v.append(f"{short}: kb commit touches non-knowledge paths {bad[:3]}")
    return v


def check_tag(root, name, sha):
    if not name.startswith("kb-") or sha == ZERO_SHA:
        return []
    if not KB_TAG.match(name):
        return [f"tag {name}: snapshot tags are kb-x.y.z"]
    if _git(root, "cat-file", "-t", sha).stdout.strip() != "tag":
        return [f"tag {name}: snapshot tags must be annotated"]
    body = _git(root, "log", "-1", "--format=%B", f"{sha}^{{commit}}").stdout
    ver = parse_version(parse_trailers(body).get("KB-Version"))
    if ver != parse_version(name):
        return [f"tag {name}: points at a commit whose KB-Version is {fmt_version(ver) if ver else 'missing'}"]
    return []


# ---------- hook entry points ----------

def _mode():
    return os.environ.get("KB_POLICY", GIT_POLICY_MODE)


def _report(violations, what):
    if not violations:
        return 0
    enforce = _mode() == "enforce"
    label = "rejected" if enforce else "warning"
    print(f"commit policy {label} ({what}):", file=sys.stderr)
    for item in violations:
        print(f"  - {item}", file=sys.stderr)
    return 1 if enforce else 0


def hook_msg(msg_file, root=ROOT):
    with open(msg_file, encoding="utf-8") as f:
        message = f.read()
    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    paths = [p for p in _git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    merge_head = _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0
    think_repo = os.path.realpath(root) == os.path.realpath(THINK_PATH)
    return _report(check_message(message, branch, paths, is_merge=merge_head, think_repo=think_repo,
                                 kb_repo=_is_kb_repo(root)), "commit-msg")


def hook_push(stdin, root=ROOT):
    violations = []
    for line in stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, remote_sha = parts
        violations += check_push_range(root, remote_sha, local_sha, remote_ref)
    return _report(violations, "pre-push")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["msg"] and len(argv) == 2:
        return hook_msg(argv[1])
    if argv[:1] == ["push"]:
        return hook_push(sys.stdin)
    if argv[:1] == ["next-version"]:
        print("kb-" + fmt_version(next_version()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

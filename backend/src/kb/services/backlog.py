"""Backlog: one markdown file per item in `.backlog/` (gitignored, in the PRIMARY checkout).

An item is a rough idea, a bug, or a plan that was made but not started. Capturing one never costs a PR:
the folder is local state, shared by every worktree because it resolves to the primary checkout
($KB_BACKLOG_DIR overrides it). No LLM: the agent formats the dump in-session, this module stores it.

A plan item copies the plan's text (the source file is scratch) and records where the repo stood when
the plan was written: `base_sha`, the branch, and the tracked paths the plan names. `drift()` then answers
"is this plan still relevant?" from git alone: commits that touched those paths since `base_sha`, paths that
were deleted or renamed, and later commit subjects that match the plan title (it may already be done).

CLI: `pixi run backlog -- add|list|show|status`.
"""
import argparse
import datetime
import functools
import json
import os
import re
import subprocess
import sys

from kb.paths import CHECKOUT_ROOT

KINDS = ("idea", "plan", "bug")
STATUSES = ("inbox", "next", "doing", "done", "dropped")
SIZES = ("s", "m", "l")
OPEN = ("inbox", "next", "doing")
MAX_PLAN_BYTES = 1024 * 1024
MAX_PATHS = 40
STALE_COMMITS = 10          # this many commits on the plan's paths since base_sha: re-read before starting
_FIELDS = ("title", "kind", "area", "size", "status", "created", "source", "plan_status", "base_sha", "branch", "paths")


class BacklogError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _git(*args, cwd=None):
    """stdout of a git command, or None when it fails (no repo, bad ref)."""
    try:
        r = subprocess.run(["git", *args], cwd=cwd or primary_root(), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


@functools.cache
def primary_root():
    """The primary checkout: a worktree shares its backlog with the checkout it was cut from."""
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=CHECKOUT_ROOT,
                             capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return os.path.dirname(out) if out.endswith(".git") else CHECKOUT_ROOT


def backlog_dir():
    return os.environ.get("KB_BACKLOG_DIR") or os.path.join(primary_root(), ".backlog")


def _main_ref():
    """Where the repo stands for a plan: origin/main (what `ship merge` updates first), else main, else HEAD."""
    for ref in ("origin/main", "main"):
        if _git("rev-parse", "--verify", "-q", ref):
            return ref
    return "HEAD"


def _slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48].strip("-")
    return s or "item"


# ── file format ──────────────────────────────────────────────────────────────────────────────────
# The two text sections are cut at marker lines that no plan contains, never at markdown headings: a plan
# has its own `## Why` / `## Plan`. The plan comes last and runs to the end of the file.
WHY_MARK = "<!-- backlog:why -->"
PLAN_MARK = "<!-- backlog:plan -->"
_DEFAULTS = dict(title="(untitled)", kind="idea", area="", size="m", status="inbox", created="", source="",
                 plan_status="no-plan", base_sha="", branch="")


def _dump(meta, why, plan):
    lines = ["---"]
    for k in _FIELDS:
        v = meta.get(k, "")
        lines.append(f"{k}: {json.dumps(v) if isinstance(v, list) else str(v).replace(chr(10), ' ')}".rstrip())
    lines.append("---")
    body = f"\n{WHY_MARK}\n{why.strip()}\n" if why.strip() else ""
    if plan.strip():
        body += f"\n{PLAN_MARK}\n{plan.strip()}\n"
    return "\n".join(lines) + "\n" + body


def _load(path):
    """One item. A hand-edited file is read leniently: a missing field gets its default, a bad kind, size or
    status falls back to one the screen can show, and bad `paths` JSON means no paths."""
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        raise BacklogError(422, f"{os.path.basename(path)}: no frontmatter")
    raw = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        raw[k.strip()] = v.strip()
    meta = {**_DEFAULTS, **{k: v for k, v in raw.items() if k in _DEFAULTS and v != ""}}
    for key, allowed in (("kind", KINDS), ("size", SIZES), ("status", STATUSES)):
        if meta[key] not in allowed:
            meta[key] = _DEFAULTS[key]
    meta["plan_status"] = meta["plan_status"] if meta["plan_status"] in ("has-plan", "no-plan") else "no-plan"
    try:
        paths = json.loads(raw.get("paths") or "[]")
        meta["paths"] = [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []
    except ValueError:
        meta["paths"] = []
    body = m.group(2)
    head, _, plan = body.partition(PLAN_MARK)
    meta["why"] = head.partition(WHY_MARK)[2].strip() if WHY_MARK in head else ""
    meta["plan"] = plan.strip()
    meta["id"] = os.path.basename(path)[:-3]
    return meta


def _write(path, meta, why, plan):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(_dump(meta, why, plan))
    os.replace(tmp, path)


# ── plan intake ──────────────────────────────────────────────────────────────────────────────────
def tracked_paths(text, sha):
    """Repo files named in `text` that existed at `sha` (exact repo-relative match; no guessing)."""
    tree = _git("ls-tree", "-r", "--name-only", sha) if sha else None
    if not tree:
        return []
    files = set(tree.splitlines())
    found = []
    for tok in re.findall(r"[\w./@+-]+", text):
        tok = tok.rstrip(".,:;").removeprefix("./")       # keep a leading dot: .cursor/…, .gitignore
        if tok in files and tok not in found:
            found.append(tok)
    return found[:MAX_PATHS]


def add_item(title, why="", kind="idea", area="", size="m", plan_file=None, source="", root=None):
    title = " ".join(title.split())
    if not title:
        raise BacklogError(422, "title is required")
    if kind not in KINDS or size not in SIZES:
        raise BacklogError(422, f"kind is one of {KINDS}, size one of {SIZES}")
    plan, sha, branch, paths = "", "", "", []
    if plan_file:
        if not os.path.isfile(plan_file) or os.path.getsize(plan_file) > MAX_PLAN_BYTES:
            raise BacklogError(422, f"plan file missing or over {MAX_PLAN_BYTES} bytes: {plan_file}")
        plan = open(plan_file, encoding="utf-8").read()
        kind = "plan"
        sha = (_git("rev-parse", _main_ref()) or "").strip()
        branch = (_git("rev-parse", "--abbrev-ref", "HEAD", cwd=CHECKOUT_ROOT) or "").strip()
        paths = tracked_paths(plan, sha)
        source = source or os.path.basename(plan_file)
    meta = dict(title=title, kind=kind, area=area, size=size, status="inbox",
                created=datetime.date.today().isoformat(), source=source,
                plan_status="has-plan" if plan.strip() else "no-plan", base_sha=sha, branch=branch, paths=paths)
    d = root or backlog_dir()
    os.makedirs(d, exist_ok=True)
    base = f"{meta['created'].replace('-', '')}-{_slug(title)}"
    iid, n = base, 2
    while os.path.exists(os.path.join(d, iid + ".md")):
        iid, n = f"{base}-{n}", n + 1
    _write(os.path.join(d, iid + ".md"), meta, why, plan)
    return {**meta, "id": iid, "why": why.strip(), "plan": plan.strip()}


# ── drift ────────────────────────────────────────────────────────────────────────────────────────
def _title_in(subject, title):
    s, t = subject.lower(), title.lower()
    words = [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 3]
    return t in s or (len(words) >= 3 and all(w in s for w in words))


def _repo_state():
    """The ref and file set every item is compared with; a listing resolves them once, not per card."""
    ref = _main_ref()
    return ref, set((_git("ls-tree", "-r", "--name-only", ref) or "").splitlines())


def drift(item, state=None):
    """{level, commits, missing, maybe_done}: fresh | drifted | stale | maybe-done | closed | none.
    `none`: the item names no tracked paths to compare (an idea, or a plan that names no files).
    Only files count, not folders: a plan that names `a/b/` records no path for it."""
    if item["status"] not in OPEN:
        return {"level": "closed", "commits": 0, "missing": [], "maybe_done": []}
    sha, paths = item.get("base_sha"), item.get("paths") or []
    if not sha or not paths or _git("cat-file", "-e", sha) is None:
        return {"level": "none", "commits": 0, "missing": [], "maybe_done": []}
    ref, tree = state or _repo_state()
    touched = (_git("log", "--format=%h %s", f"{sha}..{ref}", "--", *paths) or "").splitlines()
    missing = [p for p in paths if p not in tree]
    subjects = (_git("log", "--format=%h %s", f"{sha}..{ref}") or "").splitlines()
    done = [s for s in subjects if _title_in(s.split(" ", 1)[-1], item["title"])][:3]
    level = ("maybe-done" if done else "stale" if missing or len(touched) >= STALE_COMMITS
             else "drifted" if touched else "fresh")
    return {"level": level, "commits": len(touched), "missing": missing, "maybe_done": done}


# ── read / update ────────────────────────────────────────────────────────────────────────────────
def get_item(iid, root=None):
    path = os.path.join(root or backlog_dir(), os.path.basename(iid) + ".md")
    if not os.path.isfile(path):
        raise BacklogError(404, f"no backlog item {iid}")
    item = _load(path)
    return {**item, "drift": drift(item)}


def list_items(status=None, root=None):
    d = root or backlog_dir()
    names = sorted(n for n in os.listdir(d) if n.endswith(".md")) if os.path.isdir(d) else []
    items, state = [], None
    for n in names:
        try:
            item = _load(os.path.join(d, n))
        except (BacklogError, ValueError, OSError):
            continue                                    # a file that is not a card never breaks the list
        if status and item["status"] != status:
            continue
        item["plan"] = ""                               # the list is cards; `show` returns the plan text
        if state is None and item["status"] in OPEN and item["paths"]:
            state = _repo_state()
        items.append({**item, "drift": drift(item, state)})
    order = {s: i for i, s in enumerate(STATUSES)}
    items.sort(key=lambda i: i.get("created", ""), reverse=True)
    items.sort(key=lambda i: order.get(i.get("status"), 99))
    return {"items": items, "dir": d}


def set_status(iid, status, root=None):
    if status not in STATUSES:
        raise BacklogError(422, f"status is one of {STATUSES}")
    path = os.path.join(root or backlog_dir(), os.path.basename(iid) + ".md")
    if not os.path.isfile(path):
        raise BacklogError(404, f"no backlog item {iid}")
    item = _load(path)
    item["status"] = status
    _write(path, item, item["why"], item["plan"])
    return get_item(iid, root)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def _line(i):
    d = i["drift"]["level"]
    return (f"{i['id']:<44} {i['status']:<7} {i['kind']:<5} {i['size']} {i['plan_status']:<8} "
            f"{'' if d in ('none', 'closed') else d}  {i['title']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="backlog", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="capture an item")
    a.add_argument("--title", required=True)
    a.add_argument("--why", default="")
    a.add_argument("--kind", default="idea", choices=KINDS)
    a.add_argument("--area", default="")
    a.add_argument("--size", default="m", choices=SIZES)
    a.add_argument("--plan", help="a plan file to copy in (kind becomes plan; base_sha and paths recorded)")
    a.add_argument("--source", default="")
    ls = sub.add_parser("list", help="items, grouped by status")
    ls.add_argument("--status", choices=STATUSES)
    sh = sub.add_parser("show", help="one item with its plan and drift")
    sh.add_argument("id")
    st = sub.add_parser("status", help="move an item")
    st.add_argument("id")
    st.add_argument("status", choices=STATUSES)
    args = p.parse_args(argv)
    try:
        if args.cmd == "add":
            i = add_item(args.title, args.why, args.kind, args.area, args.size, args.plan, args.source)
            print(f"added {i['id']}  ({i['kind']}, {i['plan_status']}, {len(i['paths'])} paths tracked)")
        elif args.cmd == "list":
            res = list_items(args.status)
            print("\n".join(_line(i) for i in res["items"]) or f"empty ({res['dir']})")
        elif args.cmd == "show":
            i = get_item(args.id)
            print(json.dumps({k: v for k, v in i.items() if k != "plan"}, indent=2))
            print(i["plan"] or "(no plan)")
        else:
            i = set_status(args.id, args.status)
            print(f"{i['id']} -> {i['status']}")
    except BacklogError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

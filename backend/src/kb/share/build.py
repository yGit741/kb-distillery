"""Build one self-contained HTML of the wiki graph + explorer from a git ref (0 LLM).

    pixi run share -- build <ref> [--profile private|public] [--viewer <ref>] [--open] [--viewer-worktree]
    pixi run share -- versions

Two processes:

* **outer** (`build()`): resolves refs, `git archive`s the *content* ref into a temp `content/`
  and the *viewer* ref's `meta/` into a temp `viewer/` (tracked files only — never the working
  tree, never gitignored raw/ binaries), then runs the viewer's own copy of this module
  (`python -m kb.share.build --inner …`, cwd=viewer/, `KB_ROOT=content/`) so old content is
  rendered by whichever viewer code was asked for. Writes `index.html` + `manifest.json` under
  `.exported/share/<ref>/`.
* **inner** (`--inner`): collects graph/explorer data from `KB_ROOT` via the dashboard builders,
  normalises it (commit date instead of wall clock, sorted nodes/links), applies the profile,
  inlines the dashboard pages + vendored libs into `<iframe srcdoc>` documents and writes the
  shell page.

A `<ref>` is `main`, any commit-ish, a `kb-x.y.z` tag, or a bare knowledge version `x.y.z`
(resolved through the `KB-Version` trailers on main). `built_at` is the content commit's date,
so the same content + viewer + profile always yields the same bytes.

**Private profile only** — read-only dashboard tabs on top of Graph/Explore, and a GitHub link:

* **Start** (`/start`): the dashboard's Start page as-is (its "right now" strip reads the Lifecycle
  data below). The Chat link is removed at build time — the chat is never shared.
* **Health** (`/`): `lint.collect_snapshot()` on the content checkout under `KB_CI=1` (the
  committed `meta/corpus.tsv` stands in for the gitignored raw bytes), server-rendered through
  `dashboard.render`. `generated_at` = commit date, lint timings zeroed, guard-hook status
  neutralised (local editor config, not knowledge).
* **Digestion** (`/digestion`): `digestion_data.build_digestion_snapshot()` on the content
  checkout; wiki commit times come from the real repo's history at the content sha
  (`KB_SHARE_GIT_ROOT`, an archive has no history). Dropped: `server`, `failures`, `recent`,
  `active_ingest` (local logs/sessions, absolute paths); file ages and mtime fallbacks
  (extraction time) are blanked; `distill_review` keeps slug + count only (no think/ paths).
* **Lifecycle** (`/lifecycle`): computed here from the real repo's history *at the content sha*
  with `now` = commit date; snapshots = annotated `kb-*` tags on that history. Dropped:
  `working`, `nightly`, `stale_worktrees`, `unpushed`, `infra_branches` (local checkout state
  and mutable refs — not fixed by the content commit).

* **GitHub ↗** in the top bar: the repo URL, normalised from `git remote get-url origin` of the
  real repo at build time (`github_url`); omitted when there is no GitHub remote.

The public profile carries none of it: no tab, no document, no data, no repo URL.

**App layout (`--app`; the default of `deploy-main`, which takes `--legacy` to opt out).** Instead of the iframe shell, the build is the React app
under `frontend/` (`vite build --mode share`, one build per profile so the route set is fixed at build
time: public = graph + pages, private = + lifecycle; chat, ops, pipeline and scopes are not imported at
all). The data comes from the same `collect_data` / `collect_lifecycle` / `apply_profile`, so the public
privacy cuts are the legacy ones, baked into `<script type="application/json" id="kb-data">` of the
app's `index.html` (the id `share audit` already scans). The output directory is `index.html` +
`assets/` + `manifest.json` (`layout: "app"`, `sha256` = tree digest); the Worker serves it with a
single-page-application fallback. See skills/share-kb/SKILL.md.
"""
import argparse
import datetime as _dt
import hashlib
import html as _html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import webbrowser
from pathlib import Path

from .contracts import EXPORT_DIR, PROFILES, REPO, BuildResult, Manifest, raw_is_email
from .home import apply_home, load_home, strip_my_notes

SHARE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = REPO / "frontend"
APP_FLAG = "--app-index"      # the inner CLI flag a viewer must know to render the app layout
VENDOR_DIR = SHARE_DIR / "vendor"
VENDOR_LOCK = VENDOR_DIR / "vendor.lock"
SHIM_PATH = SHARE_DIR / "static" / "kb-static.js"
# Snapshots tab (private profile only): the panel code, its CSS, and the env var through which the
# outer build hands the inner one the knowledge versions for the "New snapshot" picker (an env var,
# not a flag, so older viewers that do not know it simply ignore it).
PANEL_JS = "panel.js"
PANEL_CSS = "panel.css"
VERSIONS_ENV = "KB_SHARE_VERSIONS"
# The real repo (the one `git archive` read from): the inner build runs read-only history commands
# there, at the content sha, for the Digestion and Lifecycle tabs. Unset → those tabs are omitted.
GIT_ROOT_ENV = "KB_SHARE_GIT_ROOT"
LIFECYCLE_LIMIT = 150          # timeline rows, as the dashboard's default
LIFECYCLE_WINDOW_DAYS = 30     # stats.ops_30d, counted back from the content commit date

# Every tab the shell can hold, in display order: view → (label, dashboard page or None for a
# non-iframe tab). The public profile keeps only PUBLIC_VIEWS.
TABS = (
    ("start", "Start", "start.html"),
    ("graph", "Graph", "graph.html"),
    ("explore", "Explore", "explore.html"),
    ("health", "Health", "template.html"),
    ("digestion", "Digestion", "digestion.html"),
    ("lifecycle", "Lifecycle", "lifecycle.html"),
    ("snapshots", "Snapshots", None),
)
PUBLIC_VIEWS = ("graph", "explore")
PRIVATE_DATA_KEYS = ("digestion", "lifecycle")   # kb-data keys that exist in private builds only

# CDN URL the dashboard loads → vendored file (sha256 pinned in vendor.lock).
CDN_FILES = {
    "https://cdn.jsdelivr.net/npm/force-graph@1.43.5/dist/force-graph.min.js": "force-graph-1.43.5.min.js",
    "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js": "marked-12.0.2.min.js",
    "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js": "katex-0.16.11.min.js",
    "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css": "katex-0.16.11.min.css",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js": "chart.js-4.4.1.umd.min.js",
}
KATEX_FONTS_URL = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/fonts/"

PUBLIC_DROP_KEYS = ("raw", "path", "email", "original_name", "scopes")
# Not content: scopes are private working sets and distilled-think pages are transient review drafts.
# LLM chats and person pages (profiles built from public sources) are the owner's and are public.
PUBLIC_EXCLUDE_TYPES = frozenset({"distilled-think", "scope"})

# Routes the shim answers; the static scan in the tests checks nothing else is fetched.
SHIMMED_API = ("/api/graph", "/api/schema", "/api/explore/index", "/api/explore/page", "/api/explore/search", "/api/explore/path",
               "/api/pipeline", "/api/digestion", "/api/lifecycle",   # Digestion (+ its old alias) and Lifecycle tabs (private): answered from kb-data
               "/api/health",                       # only named in the Health footer text; the shim answers 404
               "/api/scope", "/api/scopes", "/api/scope/resolve", "/api/scope/save", "/api/scope/delete",
               "/api/scope/duplicate",              # private scopes (scopes*.js): the shim answers 404
               "/api/corpus", "/api/raw", "/api/citations",   # private data layer (datalayer.js): named in the bundle, never served; the shim answers 404 and graph.js hides the toggle
               "/api/share/status")  # the deploy-status chip (shell.js); the shim answers it 404 so the chip stays hidden

# Snapshot keys that carry local checkout state or absolute paths — never shared.
DIGESTION_DROP_KEYS = ("server", "failures", "recent", "active_ingest")
LIFECYCLE_DROP_KEYS = ("working", "nightly", "stale_worktrees", "unpushed", "infra_branches")
_ABS_PATH = re.compile(r"^/|^~/|/Users/|OneDrive|\\\\Users\\\\")

VERSION_RE = re.compile(r"^(?:kb-)?(\d+)\.(\d+)\.(\d+)$")
_GITHUB_REMOTE = re.compile(r"^(?:https?://|ssh://)?(?:[\w.-]+@)?github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
# The Start page's footer links the Chat tab; the chat is never shared, so the link goes at build time.
_START_CHAT_LINK = ' · <a href="/chat">Chat</a>'
_NAV_PATCH = re.compile(r"\blocation\.href\s*=\s*([^;]+);")
# One pass each, in document order, so deferred scripts keep their relative order (Health:
# Chart.js from the CDN must run before dashboard.js).
_SCRIPT = re.compile(r'<script src="(/static/[^"?]+|https://cdn\.jsdelivr\.net/[^"?]+)(?:\?v=\d+)?"(\s+defer)?></script>')
_LINK = re.compile(r'<link rel="stylesheet" href="(/static/[^"?]+|https://cdn\.jsdelivr\.net/[^"?]+)(?:\?v=\d+)?">')


# Cloudflare Workers serves the page from the static-assets directory, which caps one file at
# 25 MiB; a build above that cannot be deployed at all. The page grows with the wiki (each page's
# body, the graph and the digestion table are embedded), so the builder says how close it is
# instead of a test discovering it: a warning from 80 % up, a BuildError at the limit.
MAX_HTML_BYTES = 25 * 1024 * 1024
WARN_HTML_BYTES = int(MAX_HTML_BYTES * 0.8)


def size_verdict(n_bytes, name="index.html"):
    """None when fine, a warning string from WARN_HTML_BYTES, raises BuildError at MAX_HTML_BYTES."""
    mb = n_bytes / 1_048_576
    if n_bytes > MAX_HTML_BYTES:
        raise BuildError(f"{name} is {mb:.1f} MB, over the {MAX_HTML_BYTES / 1_048_576:.0f} MB "
                         "Cloudflare static-asset limit — it cannot be deployed; shrink the page "
                         "(embedded pages / digestion rows) before sharing")
    if n_bytes > WARN_HTML_BYTES:
        return (f"{name} is {mb:.1f} MB — {100 * n_bytes / MAX_HTML_BYTES:.0f} % of the "
                f"{MAX_HTML_BYTES / 1_048_576:.0f} MB Cloudflare static-asset limit")
    return None


class BuildError(Exception):
    """A build that cannot proceed; the message is meant for the user, not a traceback."""


# ---------- git ----------

def _git(root, *args, binary=False):
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=False,
                          text=not binary)
    if proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
        raise BuildError(f"git {' '.join(args[:2])} failed: {err.strip()}")
    return proc.stdout


def _rev_parse(root, rev):
    proc = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                          cwd=str(root), capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def resolve_ref(root, ref):
    """Commit sha for `ref`: a commit-ish, a kb-x.y.z tag, or a knowledge version x.y.z."""
    ref = (ref or "").strip()
    if not ref:
        raise BuildError("empty ref")
    m = VERSION_RE.match(ref)
    if m:
        version = tuple(int(x) for x in m.groups())
        tag = "kb-%d.%d.%d" % version
        sha = _rev_parse(root, f"refs/tags/{tag}")
        if sha:
            return sha
        from kb.git import commit_policy
        sha = commit_policy.version_commit(str(root), version, rev="main")
        if sha:
            return sha
        raise BuildError(f"unknown ref {ref!r}: no tag {tag} and no commit on main with KB-Version "
                         f"{'.'.join(map(str, version))} (see `share versions`)")
    sha = _rev_parse(root, ref)
    if not sha:
        raise BuildError(f"unknown ref {ref!r}: not a branch, tag or commit in {root}")
    return sha


def kb_version_of(root, sha, ref=""):
    """Knowledge version at `sha` from the KB-Version trailers; falls back to a kb-x.y.z ref name."""
    from kb.git import commit_policy
    v = commit_policy.last_version(str(root), rev=sha)
    if v:
        return commit_policy.fmt_version(v)
    m = VERSION_RE.match(ref or "")
    if m:
        return ".".join(m.groups())
    return "none"


def commit_date(root, sha):
    return _git(root, "show", "-s", "--format=%cI", sha).strip()


def github_url(remote):
    """`git@github.com:x/y.git` / `https://github.com/x/y(.git)` / `ssh://git@github.com/x/y.git`
    → `https://github.com/x/y`; None for anything that is not a GitHub remote."""
    m = _GITHUB_REMOTE.match((remote or "").strip())
    return f"https://github.com/{m.group(1)}/{m.group(2)}" if m else None


def repo_github(root):
    """The GitHub URL of `root`'s origin remote, or None (no remote, or not on GitHub)."""
    proc = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                          capture_output=True, text=True, check=False)
    return github_url(proc.stdout) if proc.returncode == 0 else None


APP_LAYOUT = "backend/src/kb/share/build.py"      # viewer code since the app layout (package kb)
LEGACY_LAYOUT = "meta/share/build.py"             # refs before it: the code lived in meta/


def viewer_layout(root, sha):
    """"app" | "legacy" | None: which layout the viewer ref has (so any old ref can still render a page)."""
    for probe, name in ((APP_LAYOUT, "app"), (LEGACY_LAYOUT, "legacy")):
        cp = subprocess.run(["git", "cat-file", "-e", f"{sha}:{probe}"], cwd=str(root),
                            capture_output=True, check=False)
        if cp.returncode == 0:
            return name
    return None


def archive(root, sha, dest, pathspec=()):
    """Extract the tracked files of `sha` (optionally only `pathspec`) into `dest`."""
    tar_bytes = _git(root, "archive", "--format=tar", sha, *pathspec, binary=True)
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python < 3.12
            tar.extractall(dest)


# ---------- vendor ----------

def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_lock(lock_path=VENDOR_LOCK):
    out = {}
    for line in Path(lock_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        out[name.strip()] = digest.strip()
    return out


def load_vendor(vendor_dir=VENDOR_DIR):
    """{filename: text} of the vendored libs, each verified against vendor.lock."""
    vendor_dir = Path(vendor_dir)
    lock_path = vendor_dir / "vendor.lock"
    if not lock_path.exists():
        raise BuildError(f"vendor lock missing: {lock_path}")
    lock = read_lock(lock_path)
    out = {}
    for name in CDN_FILES.values():
        path = vendor_dir / name
        if not path.exists():
            raise BuildError(f"vendored file missing: {path}")
        data = path.read_bytes()
        want = lock.get(name)
        got = _sha256_bytes(data)
        if want != got:
            raise BuildError(f"vendor lock mismatch for {name}: vendor.lock says {want}, file is {got}")
        out[name] = data.decode("utf-8")
    return out


# ---------- data ----------

def _epoch(iso):
    iso = iso[:-1] + "+00:00" if iso.endswith("Z") else iso  # git prints UTC as Z; py<3.11 can't parse it
    return int(_dt.datetime.fromisoformat(iso).timestamp())


def collect_data(meta_dir, built_at, content_sha):
    """Graph snapshot, explorer index and every page, read from KB_ROOT through the viewer's builders."""
    meta_dir = str(meta_dir)
    from kb.services import pages as explore_data
    from kb.services import graph as graph_data  # noqa: WPS433 (viewer code)
    from kb.search.semfind import load_pages

    pages = load_pages()
    cached = lambda: pages  # noqa: E731
    graph_data.load_pages = cached
    explore_data.load_pages = cached
    graph_memo = {}
    orig_graph = explore_data._graph

    def memo_graph(p):
        if id(p) not in graph_memo:
            graph_memo[id(p)] = orig_graph(p)
        return graph_memo[id(p)]

    explore_data._graph = memo_graph
    epoch = _epoch(built_at)
    explore_data._mtime = lambda rel: epoch
    graph_data._etag = lambda p: content_sha[:16]
    graph_data._now = lambda: built_at
    explore_data._now = lambda: built_at

    snapshot = graph_data.build_graph_snapshot()
    index = explore_data.build_index()
    page_docs = {}
    for slug in sorted(pages):
        doc = explore_data.build_page(slug)
        if doc is not None:
            page_docs[slug] = doc
    return normalise(snapshot, index, page_docs, built_at, content_sha)


def normalise(snapshot, index, page_docs, built_at, content_sha):
    snapshot["generated_at"] = built_at
    snapshot["etag"] = content_sha[:16]
    snapshot["nodes"] = sorted(snapshot.get("nodes", []), key=lambda n: n["id"])
    snapshot["links"] = sorted(snapshot.get("links", []),
                               key=lambda l: (l["source"], l["target"], l.get("kind", "")))
    index["generated_at"] = built_at
    index["pages"] = sorted(index.get("pages", []), key=lambda c: c["id"])
    index["links"] = sorted(index.get("links", []))
    return {"graph": snapshot, "index": index, "pages": page_docs}


def _scrub(obj):
    """Blank every string that looks like an absolute/home path (defence in depth: the builders
    below only produce repo-relative paths, but a stray one must never reach the page)."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str) and _ABS_PATH.search(obj):
        return ""
    return obj


def collect_health(meta_dir, built_at):
    """The Health snapshot of the content checkout (KB_CI semantics), frozen to the commit date."""
    meta_dir = str(meta_dir)
    from kb.lint import lint  # noqa: WPS433 (viewer code)
    snap = lint.collect_snapshot(quiet=True)
    rows = snap.pop("_rows", None) or {}
    if rows:                                     # KB_CI: the manifest, not the (binary-less) checkout
        snap["raw_files"] = len(rows)
    snap["generated_at"] = built_at
    values = snap.setdefault("values", {})
    for k in ("lint_ms", "sha1_ms", "wiki_ms", "links_ms"):
        values[k] = 0
    graphs = snap.setdefault("graphs", {})
    graphs["lint_phases_ms"] = {"sha1": 0, "wiki": 0, "links": 0}
    graphs["lint_phases_pct"] = {"sha1": 0, "wiki": 0, "links": 0}
    values["hooks"] = "n/a"                      # editor hook config is local, not knowledge
    snap.setdefault("statuses", {})["hooks"] = "ok"
    snap["hooks_ok"] = True
    return _scrub(snap)


def collect_digestion(meta_dir, built_at, git_root, content_sha):
    """The Pipeline snapshot of the content checkout, without local state or wall-clock fields."""
    meta_dir = str(meta_dir)
    from kb.services import pipeline as digestion_data  # noqa: WPS433 (viewer code)
    orig_times = digestion_data._wiki_commit_times
    digestion_data._wiki_commit_times = lambda: orig_times(git_root, content_sha)
    try:
        snap = digestion_data.build_digestion_snapshot()
    finally:
        digestion_data._wiki_commit_times = orig_times
    snap["generated_at"] = built_at
    for k in DIGESTION_DROP_KEYS:
        snap.pop(k, None)
    snap.get("summary", {}).pop("active_ingest", None)
    for item in list(snap.get("items", [])) + list(snap.get("inbox", [])):
        item["age_days"] = None                  # file mtimes are the archive's extraction time
        if item.get("last_op") == "modified":    # the mtime fallback, same reason
            item["last_op"], item["last_op_at"] = "", ""
        item["failure"] = ""
    snap["distill_review"] = [{"slug": r["slug"], "proposals": r.get("proposals", 0)}
                              for r in snap.get("distill_review", [])]   # no think/ paths
    return _scrub(snap)


def collect_lifecycle(meta_dir, built_at, git_root, content_sha, content_dir, content_ref=""):
    """The Lifecycle snapshot as of the content commit: its first-parent history, versions,
    annotated kb-* tags on that history and the migration state in the checkout. Nothing about
    the working tree, remotes, worktrees or the nightly job — none of that is fixed by the sha."""
    meta_dir = str(meta_dir)
    from kb.git import commit_policy as cp  # noqa: WPS433 (viewer code)
    from kb.ops.history import timeline
    from kb.ops.migrate import _applied, pending_migrations
    from kb.core.schema import GIT_POLICY_MODE, OPS_STRICT, SCHEMA_VERSION

    rows = timeline(git_root, content_sha, limit=LIFECYCLE_LIMIT)
    shas = {r["sha"] for r in rows}
    tags = {}
    out = _git(git_root, "for-each-ref", "--sort=-creatordate", "refs/tags/kb-*",
               "--format=%(refname:short)\x1f%(objecttype)\x1f%(*objectname)\x1f%(creatordate:short)\x1f%(contents:subject)")
    snapshots = []
    for line in out.splitlines():
        tag, kind, target, date, label = (line.split("\x1f") + ["", "", "", ""])[:5]
        if kind != "tag" or target not in shas:       # lightweight tags / tags off this history
            continue
        tags.setdefault(target, tag)
        snapshots.append({"tag": tag, "date": date, "label": label})
    for r in rows:
        r["snapshot_tag"] = tags.get(r["sha"])

    since = _epoch(built_at) - LIFECYCLE_WINDOW_DAYS * 86400
    ops_30d = {}
    for r in rows:
        if r["kind"] != "kb":
            continue
        if _epoch(r["date"]) >= since:
            key = r["op"] or r["scope"]
            ops_30d[key] = ops_30d.get(key, 0) + 1

    on_main = subprocess.run(["git", "merge-base", "--is-ancestor", content_sha, "main"], cwd=str(git_root),
                             capture_output=True, check=False).returncode == 0
    version = cp.last_version(git_root, content_sha)
    return _scrub({
        "generated_at": built_at,
        "branch": "main" if on_main else (content_ref or "detached"),
        "head": content_sha[:9],
        "version": cp.fmt_version(version) if version else None,
        "next_version": cp.fmt_version(cp.next_version(git_root, content_sha)),
        "github": repo_github(git_root),
        "schema": {
            "version": f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}",
            "applied": [r[0] for r in _applied(content_dir).values()],
            "pending": pending_migrations(content_dir),
        },
        "policy": {"mode": GIT_POLICY_MODE, "strict": OPS_STRICT},
        "timeline": rows,
        "snapshots": snapshots,
        "stats": {
            "kb_steps": sum(1 for r in rows if r["kind"] == "kb"),
            "pr_merges": sum(1 for r in rows if r["kind"] == "pr-merge"),
            "ops_30d": dict(sorted(ops_30d.items())),
            "undone": sum(1 for r in rows if r["reverted_by"]),
        },
    })


def apply_profile(data, profile):
    if profile == "private":
        return data
    if profile != "public":
        raise BuildError(f"unknown profile {profile!r}; choose one of {', '.join(PROFILES)}")
    for k in PRIVATE_DATA_KEYS:
        data.pop(k, None)
    graph, index, pages = data["graph"], data["index"], data["pages"]
    drop = {n["id"] for n in graph["nodes"] if n.get("type") in PUBLIC_EXCLUDE_TYPES}
    drop |= {c["id"] for c in index["pages"] if c.get("type") in PUBLIC_EXCLUDE_TYPES}
    drop |= {s for s, p in pages.items() if (p.get("card") or {}).get("type") in PUBLIC_EXCLUDE_TYPES}
    # Email-derived pages involve another person's correspondence: dropped (page, node, card, links, search,
    # backlinks) through the same `drop` set, wherever `raw:` is still visible (before PUBLIC_DROP_KEYS strips it).
    drop |= {n["id"] for n in graph["nodes"] if raw_is_email((n.get("properties") or {}).get("raw"))}
    drop |= {s for s, p in pages.items() if raw_is_email((p.get("frontmatter") or {}).get("raw"))}
    keep = lambda s: s not in drop  # noqa: E731

    nodes = []
    for n in graph["nodes"]:
        if not keep(n["id"]):
            continue
        n.pop("path", None)
        props = n.get("properties") or {}
        for k in PUBLIC_DROP_KEYS:
            props.pop(k, None)
        nodes.append(n)
    graph["nodes"] = nodes
    graph["links"] = [l for l in graph["links"] if keep(l["source"]) and keep(l["target"])]
    graph["concept_links"] = [l for l in graph.get("concept_links") or [] if keep(l["source"]) and keep(l["target"])]
    schema = graph.get("schema")
    if schema:                                   # private-only types are not even named publicly
        schema["types"] = [t for t in schema["types"] if t["id"] not in PUBLIC_EXCLUDE_TYPES]
        for layer in schema.get("layers", []):
            layer["types"] = [t for t in layer["types"] if t not in PUBLIC_EXCLUDE_TYPES]
    graph["node_count"] = len(graph["nodes"])
    graph["link_count"] = len(graph["links"])
    facets = graph.get("facets") or {}
    facets["types"] = sorted({n.get("type", "unknown") for n in nodes})
    graph["facets"] = facets

    index["pages"] = [c for c in index["pages"] if keep(c["id"])]
    index["links"] = [l for l in index["links"] if keep(l[0]) and keep(l[1])]
    for w in index.get("wanted", []):
        w["from"] = [s for s in w.get("from", []) if keep(s)]

    out_pages = {}
    for slug, p in pages.items():
        if not keep(slug):
            continue
        p.pop("path", None)
        if "markdown" in p:                      # the synthesis is public, the user's own notes are not
            p["markdown"] = strip_my_notes(p["markdown"])
        fm = p.get("frontmatter") or {}
        for k in PUBLIC_DROP_KEYS:
            fm.pop(k, None)
        p["backlinks"] = [b for b in p.get("backlinks", []) if keep(b["id"])]
        p["outbound"] = [s for s in p.get("outbound", []) if keep(s)]
        sugg = []
        for s in p.get("suggested", []):
            if not keep(s["id"]):
                continue
            s["via"] = [v for v in s.get("via", []) if keep(v)]
            sugg.append(s)
        p["suggested"] = sugg
        out_pages[slug] = p
    data["pages"] = out_pages
    return data


# ---------- html ----------

def embed_json(obj):
    """Compact, key-sorted JSON safe inside a <script> element."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.replace("</", "\\u003c/").replace("<!--", "\\u003c!--")


def _js_safe(text):
    return text.replace("</script", "<\\/script")


def _css_safe(text):
    return text.replace("</style", "<\\/style")


def inline_view(html_path, static_dir, vendor, shim, text=None):
    """One dashboard page with its /static and CDN assets inlined and the shim as the first script.

    `text` is the page when it is server-rendered (Health: `dashboard.render.render_page`);
    otherwise `html_path` is read. Build-time patch (documented): `location.href = X;` →
    `window.KB_STATIC.navigate(X);` in the dashboard scripts, because `location` cannot be
    intercepted at runtime. Everything else goes through the shim's fetch override and click capture.
    """
    html_path = Path(html_path)
    text = (text if text is not None else html_path.read_text(encoding="utf-8")).replace("{{NAV}}", "")
    static_dir = Path(static_dir)
    deferred = []
    patched = [0]

    def script_tag(js):
        return "<script>\n" + _js_safe(js) + "\n</script>"

    def script(m):
        src = m.group(1)
        if src.startswith("/static/"):
            js = (static_dir / src[len("/static/"):]).read_text(encoding="utf-8")
            js, n = _NAV_PATCH.subn(r"window.KB_STATIC.navigate(\1);", js)
            patched[0] += n
        else:
            name = CDN_FILES.get(src)
            if not name:
                raise BuildError(f"unvendored CDN script in {html_path.name}: {src}")
            js = vendor[name]
        tag = script_tag(js)
        if m.group(2):
            deferred.append(tag)
            return ""
        return tag

    def link(m):
        src = m.group(1)
        if src.startswith("/static/"):
            css = (static_dir / src[len("/static/"):]).read_text(encoding="utf-8")
        else:
            name = CDN_FILES.get(src)
            if not name:
                raise BuildError(f"unvendored CDN stylesheet in {html_path.name}: {src}")
            css = vendor[name].replace("url(fonts/", "url(" + KATEX_FONTS_URL)
        return "<style>\n" + _css_safe(css) + "\n</style>"

    text = _SCRIPT.sub(script, text)
    text = _LINK.sub(link, text)
    leftover = re.search(r'<(?:script src|link rel="stylesheet" href)="(?:https?:|/)', text)
    if leftover:
        raise BuildError(f"{html_path.name}: asset reference left after inlining at {leftover.start()}")
    text = text.replace("<head>", "<head>\n" + script_tag(shim), 1)
    text = text.replace("</body>", "\n".join(deferred) + "\n</body>", 1)
    return text, patched[0]


SHELL_CSS = """
:root{--bg:#f7f7f8;--fg:#1c1c1e;--muted:#6b6b70;--border:#d9d9de;--accent:#2f6fdd;--tab:#ffffff}
:root[data-theme="dark"]{--bg:#121214;--fg:#ececf1;--muted:#9a9aa3;--border:#2c2c32;--accent:#7aa2ff;--tab:#1b1b1f}
html,body{height:100%;margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
body{display:flex;flex-direction:column}
.kb-nav{display:flex;align-items:center;gap:.5rem;padding:.35rem .75rem;border-bottom:1px solid var(--border);background:var(--tab)}
.kb-tabs{display:flex;gap:.25rem}
.kb-tabs button{border:0;background:transparent;color:var(--muted);padding:.35rem .7rem;border-radius:6px;cursor:pointer;font:inherit}
.kb-tabs button.active{color:var(--fg);background:var(--bg);font-weight:600}
.kb-tabs button[hidden]{display:none}
.kb-spacer{flex:1}
.kb-brand{color:var(--muted);font-size:.85rem}
#kb-theme,#kb-github{border:1px solid var(--border);background:transparent;color:var(--fg);border-radius:6px;padding:.2rem .5rem;cursor:pointer;font:inherit;text-decoration:none;line-height:1.4}
#kb-github:hover{color:var(--accent)}
main{flex:1;min-height:0;display:flex}
main>section{flex:1;min-width:0;display:flex}
main>section[hidden]{display:none}
iframe{flex:1;border:0;width:100%;height:100%;background:var(--bg)}
.kb-foot{padding:.25rem .75rem;border-top:1px solid var(--border);color:var(--muted);font-size:.75rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kb-empty{margin:2rem auto;color:var(--muted)}
"""

SHELL_JS = r"""
(function () {
  "use strict";
  const THEME_KEY = "dashboard-theme";
  const data = JSON.parse(document.getElementById("kb-data").textContent);
  window.KB_DATA = data;
  // One <script type="application/json" id="kb-doc-<view>"> per iframe tab the build included.
  const docs = {};
  document.querySelectorAll('script[type="application/json"][id^="kb-doc-"]').forEach((s) => {
    docs[s.id.slice("kb-doc-".length)] = JSON.parse(s.textContent);
  });
  const frames = {};
  const pending = {};
  let active = null;

  function theme() {
    let t = null;
    try { t = localStorage.getItem(THEME_KEY); } catch (_e) { /* file:// or blocked storage */ }
    return t || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function setTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(THEME_KEY, t); } catch (_e) { /* ignore */ }
    Object.values(frames).forEach((f) => { if (f.contentWindow) f.contentWindow.postMessage({ type: "kb:theme", theme: t }, "*"); });
  }

  function frame(view) {
    if (frames[view]) return frames[view];
    const f = document.getElementById("frame-" + view);
    f.addEventListener("load", () => {
      f.dataset.ready = "1";
      f.contentWindow.postMessage({ type: "kb:theme", theme: theme() }, "*");
      if (pending[view]) { f.contentWindow.postMessage(pending[view], "*"); pending[view] = null; }
    });
    f.srcdoc = docs[view];
    frames[view] = f;
    return f;
  }

  function send(view, msg) {
    const f = frame(view);
    if (f.dataset.ready) f.contentWindow.postMessage(msg, "*");
    else pending[view] = msg;
  }

  // Extra (non-iframe) tabs register an opener here before this script runs: {view: open()}.
  const extra = window.KB_EXTRA_TABS || {};
  function known(view) { return Boolean(docs[view]) || typeof extra[view] === "function"; }

  function show(view, opts) {
    opts = opts || {};
    if (!known(view)) view = "graph";
    document.querySelectorAll("main > section").forEach((s) => { s.hidden = s.id !== "tab-" + view; });
    document.querySelectorAll(".kb-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    active = view;
    if (extra[view]) extra[view]();
    else frame(view);
    if (view === "explore") send("explore", { type: "kb:show", hash: opts.hash || "#/" });
    if (view === "graph" && opts.focus) send("graph", { type: "kb:show", focus: opts.focus });
    const h = view === "explore" ? "#explore" + ((opts.hash || "#/").replace(/^#\/?/, "/")).replace(/\/$/, "") : "#" + view;
    if (location.hash !== h) history.replaceState(null, "", h);
  }

  function fromHash() {
    const raw = location.hash.replace(/^#/, "");
    const m = /^(start|graph|explore|health|digestion|lifecycle|snapshots)(\/.*)?$/.exec(raw);
    if (!m) return { view: "graph" };
    if (m[1] === "explore") return { view: "explore", hash: "#" + (m[2] || "/") };
    return { view: m[1] };
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (!m || typeof m !== "object") return;
    if (m.type === "kb:nav") show(m.view, { hash: m.hash, focus: m.focus });
    else if (m.type === "kb:hash" && active === "explore") {
      const h = "#explore" + String(m.hash || "#/").replace(/^#\/?/, "/").replace(/\/$/, "");
      if (location.hash !== h) history.replaceState(null, "", h);
    }
  });
  window.addEventListener("hashchange", () => {
    const want = fromHash();
    if (want.view !== active || want.view === "explore") show(want.view, want);
  });

  document.querySelectorAll(".kb-tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
  document.getElementById("kb-theme").addEventListener("click", () => setTheme(theme() === "dark" ? "light" : "dark"));
  document.documentElement.setAttribute("data-theme", theme());
  const first = fromHash();
  show(first.view, first);
})();
"""


def panel_parts(versions, static_dir):
    """(tab button, section body, head extras, scripts) of the Snapshots tab — private builds only."""
    static_dir = Path(static_dir)
    js = (static_dir / PANEL_JS).read_text(encoding="utf-8")
    css = (static_dir / PANEL_CSS).read_text(encoding="utf-8")
    button = "<button type=\"button\" data-view=\"snapshots\" role=\"tab\">Snapshots</button>"
    section = "<section id=\"tab-snapshots\" hidden><div id=\"kb-panel\" class=\"kb-panel\"></div></section>\n"
    head = (f"<style>{_css_safe(css)}</style>\n"
            f"<script type=\"application/json\" id=\"kb-versions\">{embed_json(versions)}</script>\n")
    scripts = f"<script>{_js_safe(js)}</script>\n"
    return button, section, head, scripts


def shell_html(data, docs, manifest_fields, panel=None, github=None):
    """The shell page. `docs` = {view: srcdoc html} for the iframe tabs (graph + explore always;
    start/health/digestion/lifecycle in private builds); `panel` = panel_parts(...) for the private
    profile; None → no Snapshots tab at all; `github` = repo URL for the top-bar link (private
    builds with a GitHub remote) or None → no link. Tab order is TABS."""
    kb_version = manifest_fields["kb_version"]
    footer = (f"kb {kb_version} · {manifest_fields['content_sha'][:7]} · viewer "
              f"{manifest_fields['viewer_sha'][:7]} · {manifest_fields['profile']} · built "
              f"{manifest_fields['built_at']}")
    title = f"Thesis Wiki — kb {kb_version}"
    empty = ""
    button, section, head, scripts = panel or ("", "<section id=\"tab-snapshots\" hidden></section>\n", "", "")
    if not data["graph"]["nodes"]:
        empty = '<p class="kb-empty">This version has no wiki pages.</p>'
    gh_link = (f"<a id=\"kb-github\" href=\"{_html.escape(github, quote=True)}\" target=\"_blank\" "
               f"rel=\"noopener\" title=\"Open the repository on GitHub\">GitHub ↗</a>\n") if github else ""
    doc_tags, buttons, sections = [], [], []
    for view, label, page in TABS:
        if page is None:                      # the Snapshots panel: not an iframe
            buttons.append(button)
            sections.append(section)
            continue
        if view not in docs:
            continue
        doc_tags.append(f"<script type=\"application/json\" id=\"kb-doc-{view}\">{embed_json(docs[view])}</script>\n")
        buttons.append(f"<button type=\"button\" data-view=\"{view}\" role=\"tab\">{label}</button>")
        hidden = "" if view == "graph" else " hidden"
        lead = empty if view == "graph" else ""
        sections.append(f"<section id=\"tab-{view}\"{hidden}>{lead}<iframe id=\"frame-{view}\" title=\"{label}\"></iframe></section>\n")
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_html.escape(title)}</title>\n"
        f"<style>{SHELL_CSS}</style>\n"
        f"<script type=\"application/json\" id=\"kb-data\">{embed_json(data)}</script>\n"
        f"{''.join(doc_tags)}"
        f"{head}"
        "</head>\n<body>\n"
        "<nav class=\"kb-nav\" aria-label=\"Views\">\n"
        "<div class=\"kb-tabs\" role=\"tablist\">"
        f"{''.join(buttons)}"
        "</div>\n<span class=\"kb-spacer\"></span>\n"
        f"<span class=\"kb-brand\">{_html.escape(title)}</span>\n"
        f"{gh_link}"
        "<button type=\"button\" id=\"kb-theme\" title=\"Toggle theme\" aria-label=\"Toggle light/dark theme\">☀ / ☾</button>\n"
        "</nav>\n<main>\n"
        f"{''.join(sections)}"
        "</main>\n"
        f"<footer class=\"kb-foot\" id=\"kb-foot\">{_html.escape(footer)}</footer>\n"
        f"{scripts}"
        f"<script>{SHELL_JS}</script>\n"
        "</body>\n</html>\n"
    )


def health_page(meta_dir, snapshot):
    """Health is server-rendered: the template filled by the viewer's dashboard.render (no nav)."""
    meta_dir = str(meta_dir)
    from kb.dashboard import render as dash_render  # noqa: WPS433 (viewer code)
    orig_nav = dash_render.render_nav
    dash_render.render_nav = lambda active: "{{NAV}}"
    try:
        return dash_render.render_page(snapshot)
    finally:
        dash_render.render_nav = orig_nav


def render(meta_dir, data, manifest_fields, vendor_dir=None, shim_path=None, versions=None, health=None,
           github=None):
    """`health` = the Health snapshot (private builds); the Digestion/Lifecycle tabs are included
    when `data` carries their keys; `github` = repo URL for the top-bar link. Public builds get
    graph + explore only."""
    meta_dir = Path(meta_dir)
    vendor = load_vendor(vendor_dir or meta_dir / "share" / "vendor")
    shim = Path(shim_path or meta_dir / "share" / "static" / "kb-static.js").read_text(encoding="utf-8")
    dash = meta_dir / "dashboard"
    private = manifest_fields["profile"] == "private"
    docs = {}
    for view, _label, page in TABS:
        if page is None or (view not in PUBLIC_VIEWS and not private):
            continue
        if view == "health":
            if health is None:
                continue
            docs[view], _ = inline_view(dash / page, dash / "static", vendor, shim, text=health_page(meta_dir, health))
        elif view in PRIVATE_DATA_KEYS:
            if view not in data:
                continue
            docs[view], _ = inline_view(dash / page, dash / "static", vendor, shim)
        elif view == "start":
            text = (dash / page).read_text(encoding="utf-8").replace(_START_CHAT_LINK, "")
            docs[view], _ = inline_view(dash / page, dash / "static", vendor, shim, text=text)
        else:
            docs[view], _ = inline_view(dash / page, dash / "static", vendor, shim)
    panel = None
    if private:
        panel = panel_parts(versions or [], meta_dir / "share" / "static")
    return shell_html(data, docs, manifest_fields, panel, github=github if private else None)


def inner_build(args):
    """Runs inside the viewer checkout with KB_ROOT pointing at the content checkout."""
    meta_dir = Path(__file__).resolve().parents[1]
    fields = {"content_ref": args.content_ref, "content_sha": args.content_sha,
              "kb_version": args.kb_version, "viewer_sha": args.viewer_sha,
              "profile": args.profile, "built_at": args.built_at}
    data = collect_data(meta_dir, args.built_at, args.content_sha)
    health = github = None
    git_root = os.environ.get(GIT_ROOT_ENV)
    if args.profile == "private":
        health = collect_health(meta_dir, args.built_at)
        if git_root and os.path.isdir(git_root):
            github = repo_github(git_root)
            data["digestion"] = collect_digestion(meta_dir, args.built_at, git_root, args.content_sha)
            data["lifecycle"] = collect_lifecycle(meta_dir, args.built_at, git_root, args.content_sha,
                                                  os.environ.get("KB_ROOT", "."), args.content_ref)
    data = apply_profile(data, args.profile)
    versions = []
    vpath = os.environ.get(VERSIONS_ENV)
    if args.profile == "private" and vpath and os.path.isfile(vpath):
        versions = json.loads(Path(vpath).read_text(encoding="utf-8"))
    page = render(meta_dir, data, fields, versions=versions, health=health, github=github)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"{out} ({len(data['graph']['nodes'])} nodes, {len(data['pages'])} pages, "
          f"{out.stat().st_size // 1024} KB)")
    return 0


# ---------- app layout ----------

_DATA_TAG = '<script type="application/json" id="kb-data">%s</script>\n'
_TITLE_RE = re.compile(r"<title>.*?</title>", re.S)


def app_page(template, data, manifest_fields):
    """The built app's index.html with the data blob baked in (before </head>) and a versioned title.

    `data` = {graph, index, pages[, lifecycle]} after `apply_profile`; the blob also carries `meta`
    (what the footer line shows). The module script runs after parsing, so it finds `#kb-data`."""
    meta = {k: manifest_fields[k] for k in ("kb_version", "content_sha", "viewer_sha", "profile", "built_at")}
    blob = dict(data, meta=meta)
    title = f"<title>{_html.escape('Thesis Wiki — kb ' + manifest_fields['kb_version'])}</title>"
    if "</head>" not in template or not _TITLE_RE.search(template):
        raise BuildError("the app's index.html has no <title> / </head>; rebuild the frontend (pixi run web-install)")
    page = _TITLE_RE.sub(lambda _m: title, template, count=1)
    return page.replace("</head>", _DATA_TAG % embed_json(blob) + "</head>", 1)


def inner_build_app(args):
    """Inside the viewer checkout, KB_ROOT = content: the same data as the legacy build, in the app's page."""
    meta_dir = Path(__file__).resolve().parents[1]
    fields = {"content_ref": args.content_ref, "content_sha": args.content_sha,
              "kb_version": args.kb_version, "viewer_sha": args.viewer_sha,
              "profile": args.profile, "built_at": args.built_at}
    data = collect_data(meta_dir, args.built_at, args.content_sha)
    git_root = os.environ.get(GIT_ROOT_ENV)
    if args.profile == "private" and git_root and os.path.isdir(git_root):
        data["lifecycle"] = collect_lifecycle(meta_dir, args.built_at, git_root, args.content_sha,
                                              os.environ.get("KB_ROOT", "."), args.content_ref)
    data = apply_profile(data, args.profile)      # the one place the public cuts live
    data = apply_home(data, load_home())          # Home cards + tour from share.toml `[home]`
    page = app_page(Path(args.app_index).read_text(encoding="utf-8"), data, fields)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"{out} ({len(data['graph']['nodes'])} nodes, {len(data['pages'])} pages, {out.stat().st_size // 1024} KB, app)")
    return 0


def frontend_source_hash(frontend=FRONTEND_DIR):
    """Digest of what the share bundle is made of: the app sources (not tests), its config and lockfile."""
    frontend = Path(frontend)
    h = hashlib.sha256()
    files = [p for p in (frontend / "src").rglob("*") if p.is_file() and ".test." not in p.name
             and "test" not in p.relative_to(frontend / "src").parts[:1]]
    files += [frontend / n for n in ("index.html", "vite.config.ts", "tsconfig.json", "package.json", "package-lock.json")
              if (frontend / n).is_file()]
    for p in sorted(files):
        h.update(p.relative_to(frontend).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def ensure_frontend_dist(profile, frontend=FRONTEND_DIR, runner=None):
    """`frontend/dist-share/<profile>/` built from the current sources (rebuilt when they changed).

    `vite build --mode share` with VITE_SHARE_PROFILE=<profile>; needs `pixi run web-install` once."""
    frontend = Path(frontend)
    dist = frontend / "dist-share" / profile
    stamp = dist / ".src-hash"
    want = frontend_source_hash(frontend)
    if (dist / "index.html").is_file() and stamp.is_file() and stamp.read_text().strip() == want:
        return dist
    if not (frontend / "node_modules").is_dir():
        raise BuildError("frontend/node_modules is missing — run `pixi run web-install` once, then retry")
    env = dict(os.environ, VITE_SHARE_PROFILE=profile)
    proc = (runner or subprocess.run)(["npm", "run", "build:share", "--prefix", str(frontend)], env=env,
                                      capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        raise BuildError("frontend share build failed:\n" + "\n".join(tail))
    stamp.write_text(want + "\n")
    return dist


def tree_files(directory):
    """Every file under `directory` as sorted POSIX relative paths."""
    directory = Path(directory)
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())


def tree_digest(directory):
    """sha256 over (relative path, file sha256) of every file except manifest.json — the app layout's `sha256`."""
    directory = Path(directory)
    h = hashlib.sha256()
    for rel in tree_files(directory):
        if rel == "manifest.json":
            continue
        h.update(rel.encode() + b"\0" + hashlib.sha256((directory / rel).read_bytes()).digest())
    return h.hexdigest()


def assemble_app(dist, page_path, out_dir):
    """`out_dir` = a clean copy of the built app (minus its template index.html) + the data-carrying page."""
    dist, out_dir = Path(dist), Path(out_dir)
    for child in list(out_dir.iterdir()) if out_dir.is_dir() else []:
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel in tree_files(dist):
        if rel == "index.html" or rel.startswith(".") or "/." in rel:
            continue
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dist / rel, dest)
    shutil.copyfile(page_path, out_dir / "index.html")


# ---------- outer ----------

def _safe_name(ref):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ref).strip("-") or "ref"


_SCHEMA_RE = re.compile(r"^SCHEMA_VERSION\s*=\s*\((\d+)\s*,\s*(\d+)\)", re.M)


def schema_major(root, sha):
    """x of SCHEMA_VERSION = (x, y) in the schema at `sha` (backend/src/kb/core/schema.py, or meta/schema.py
    before the app layout), or None."""
    for rel in ("backend/src/kb/core/schema.py", "meta/schema.py"):
        cp = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(root), capture_output=True,
                            text=True, check=False)
        m = _SCHEMA_RE.search(cp.stdout or "") if cp.returncode == 0 else None
        if m:
            return int(m.group(1))
    return None


def build(content_ref, viewer_ref="main", profile="private", *, root=REPO, viewer_root=None,
          out_root=EXPORT_DIR, viewer_worktree=False, label=None, app=False, frontend_dist=None):
    """Build `content_ref` with the viewer at `viewer_ref` → BuildResult(dir, manifest).

    `root` is the repo the content comes from; `viewer_root` (default: the same repo) is where
    the viewer code is taken from — a committed ref, or its working tree with `viewer_worktree`.

    `app=True` (opt-in) builds the React app layout instead of the iframe shell: `frontend_dist` is
    its built `dist-share/<profile>` (default: built/reused from this checkout's `frontend/`). The
    legacy path below is untouched when `app` is False.
    """
    root = Path(root)
    viewer_root = Path(viewer_root or root)
    if profile not in PROFILES:
        raise BuildError(f"unknown profile {profile!r}; choose one of {', '.join(PROFILES)}")
    content_sha = resolve_ref(root, content_ref)
    built_at = commit_date(root, content_sha)
    kb_version = kb_version_of(root, content_sha, content_ref)
    if viewer_ref == "main" and not viewer_worktree:
        # A paradigm change (schema x.0) renames types; the new viewer keeps no aliases for the old
        # names. Content from another paradigm is rendered by the viewer of its own commit.
        cmaj, vmaj = schema_major(root, content_sha), schema_major(viewer_root, resolve_ref(viewer_root, "main"))
        if cmaj is not None and vmaj is not None and cmaj != vmaj:
            print(f"share build: {content_ref} is schema {cmaj}.x, main is {vmaj}.x — rendering it "
                  "with its own viewer", file=sys.stderr)
            viewer_ref = content_sha
    if viewer_worktree:
        viewer_sha = _rev_parse(viewer_root, "HEAD") or "worktree"
    else:
        viewer_sha = resolve_ref(viewer_root, viewer_ref)
    out_dir = Path(out_root) / (_safe_name(label or content_ref) + ("-app" if app and not label else ""))
    html_path = out_dir / "index.html"
    if app:
        dist = Path(frontend_dist) if frontend_dist else ensure_frontend_dist(profile)
        if not (dist / "index.html").is_file():
            raise BuildError(f"{dist} has no index.html — build the frontend first (pixi run web-install)")
    with tempfile.TemporaryDirectory(prefix="kb-share-") as tmp:
        content_dir = os.path.join(tmp, "content")
        archive(root, content_sha, content_dir)
        if viewer_worktree:
            viewer_dir = str(viewer_root)
            layout = "app" if os.path.isfile(os.path.join(viewer_dir, APP_LAYOUT)) else (
                "legacy" if os.path.isfile(os.path.join(viewer_dir, LEGACY_LAYOUT)) else None)
        else:
            viewer_dir = os.path.join(tmp, "viewer")
            layout = viewer_layout(viewer_root, viewer_sha)
            if layout:
                archive(viewer_root, viewer_sha, viewer_dir, ("backend",) if layout == "app" else ("meta",))
        if layout is None:
            raise BuildError(f"viewer {viewer_ref} ({viewer_sha[:7]}) has no share builder (backend/src/kb/share/build.py, or meta/share/build.py before the app layout) — "
                             "pick a viewer ref that contains the share builder (--viewer <branch|sha>), "
                             "or --viewer-worktree to use this checkout's code")
        if app and (layout != "app" or APP_FLAG not in (Path(viewer_dir) / APP_LAYOUT).read_text(encoding="utf-8")):
            raise BuildError(f"viewer {viewer_ref} ({viewer_sha[:7]}) predates the app layout (no {APP_FLAG}) — "
                             "use --viewer-worktree, or a viewer ref that contains it")
        if app:
            html_path = Path(tmp) / "app-index.html"   # assembled into out_dir below, after the guard
        out_dir.mkdir(parents=True, exist_ok=True)
        # PYTHONHASHSEED=0: set iteration order in the viewer's data builders (e.g. tie-breaks in
        # explore_data._suggest) must not vary between runs or machines. KB_CI=1: the content
        # checkout has no raw binaries (gitignored) — lint must trust meta/corpus.tsv and never
        # regenerate index.md/corpus.tsv. KB_SHARE_GIT_ROOT: the real repo, for history reads.
        env = dict(os.environ, KB_ROOT=content_dir, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0",
                   KB_CI="1")
        env.pop("PYTHONPATH", None)
        if layout == "app":      # the viewer's own kb package, not whatever is installed
            env["PYTHONPATH"] = os.path.join(viewer_dir, "backend", "src")
        env.pop(VERSIONS_ENV, None)
        env.pop(GIT_ROOT_ENV, None)
        if profile == "private":
            env[GIT_ROOT_ENV] = str(root)
            vfile = os.path.join(tmp, "versions.json")
            with open(vfile, "w", encoding="utf-8") as f:
                json.dump(panel_versions(root, content_sha), f)
            env[VERSIONS_ENV] = vfile
        cmd = [sys.executable, "-m", "kb.share.build" if layout == "app" else "meta.share.build", "--inner",
               "--out", str(html_path), "--profile", profile,
               "--content-ref", content_ref, "--content-sha", content_sha,
               "--kb-version", kb_version, "--viewer-sha", viewer_sha, "--built-at", built_at]
        if app:
            cmd += [APP_FLAG, str(dist / "index.html")]
        proc = subprocess.run(cmd, cwd=viewer_dir, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
            raise BuildError("inner build failed in viewer %s:\n%s" % (viewer_sha[:7], "\n".join(tail)))
        if app:
            for rel in tree_files(dist):       # the 25 MiB guard applies to every file the Worker serves
                if not (rel == "index.html" or rel.startswith(".")):
                    size_verdict((dist / rel).stat().st_size, rel)
            warning = size_verdict(html_path.stat().st_size)
            if warning:
                print(f"share build: {warning}", file=sys.stderr)
            assemble_app(dist, html_path, out_dir)
    if app:
        manifest = Manifest(content_ref=content_ref, content_sha=content_sha, kb_version=kb_version,
                            viewer_sha=viewer_sha, profile=profile, sha256=tree_digest(out_dir),
                            built_at=built_at, layout="app")
        (out_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
        return BuildResult(dir=out_dir, manifest=manifest)
    page = html_path.read_bytes()
    warning = size_verdict(len(page))          # BuildError above the deployable size
    if warning:
        print(f"share build: {warning}", file=sys.stderr)
    manifest = Manifest(content_ref=content_ref, content_sha=content_sha, kb_version=kb_version,
                        viewer_sha=viewer_sha, profile=profile,
                        sha256=_sha256_bytes(page), built_at=built_at)
    (out_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    return BuildResult(dir=out_dir, manifest=manifest)


def versions(root=REPO, rev="main"):
    """Knowledge steps on `rev` (default main; newest first) with their tags: [{version, sha, date, subject, tags}]."""
    from kb.git import commit_policy
    from kb.ops.core import snapshots
    out = _git(root, "log", "--first-parent", "--format=%H%x1f%cs%x1f%s%x1f%B%x1e", rev, "--")
    tags = {}
    for s in snapshots(str(root)):
        sha = _rev_parse(root, s["tag"])
        tags.setdefault(sha, []).append(s["tag"])
    rows = []
    for rec in out.split("\x1e"):
        if "\x1f" not in rec:
            continue
        sha, date, subject, body = rec.strip("\n").split("\x1f", 3)
        v = commit_policy.parse_version(commit_policy.parse_trailers(body).get("KB-Version"))
        if not v:
            continue
        rows.append({"version": commit_policy.fmt_version(v), "sha": sha, "date": date,
                     "subject": subject, "tags": tags.get(sha, [])})
    return rows


def panel_versions(root, sha):
    """The Snapshots tab's version picker: knowledge steps up to `sha` (first parent, newest first).

    Only what `sha`'s history fixes — no tags (a tag added later must not change the bytes) — so the
    same content + viewer + profile still builds byte-identically. Distinct versions only.
    """
    seen, out = set(), []
    for r in versions(root, rev=sha):
        if r["version"] in seen:
            continue
        seen.add(r["version"])
        out.append({"version": r["version"], "sha": r["sha"][:12], "date": r["date"], "subject": r["subject"][:80]})
    return out


def cmd_versions(args):
    rows = versions(args.root)
    if not rows:
        print("no knowledge versions on main")
        return 0
    for r in rows[: args.limit]:
        tag = " ".join(r["tags"])
        print(f"kb-{r['version']:<9} {r['sha'][:7]}  {r['date']}  {tag:<10} {r['subject'][:70]}")
    return 0


def cmd_build(args):
    try:
        result = build(args.ref, viewer_ref=args.viewer, profile=args.profile, root=args.root,
                       viewer_worktree=args.viewer_worktree, app=args.app,
                       frontend_dist=args.frontend_dist)
    except BuildError as e:
        print(f"share build: {e}", file=sys.stderr)
        return 1
    m = result.manifest
    html = result.dir / "index.html"
    print(f"{html}  ({html.stat().st_size / 1_048_576:.1f} MB of {MAX_HTML_BYTES / 1_048_576:.0f} MB)")
    if m.layout == "app":
        total = sum((result.dir / rel).stat().st_size for rel in tree_files(result.dir))
        print(f"app layout: {len(tree_files(result.dir))} files, {total / 1_048_576:.1f} MB in total")
    print(f"kb {m.kb_version} · {m.content_sha[:7]} · viewer {m.viewer_sha[:7]} · {m.profile} · "
          f"built {m.built_at} · sha256 {m.sha256[:12]}")
    if args.open:
        webbrowser.open(html.resolve().as_uri())
    return 0


def register(sub):
    b = sub.add_parser("build", help="build a self-contained graph+explorer page from a git ref")
    b.add_argument("ref", help="main, a commit, a kb-x.y.z tag or a knowledge version x.y.z")
    b.add_argument("--profile", choices=PROFILES, default="private")
    b.add_argument("--viewer", default="main", help="ref whose dashboard code renders the page (default main)")
    b.add_argument("--open", action="store_true", help="open the result in the browser")
    b.add_argument("--viewer-worktree", action="store_true",
                   help="dev only: use this worktree's dashboard code instead of a committed ref")
    b.add_argument("--app", action="store_true",
                   help="opt in: build the React app layout (index.html + assets/) instead of the iframe shell")
    b.add_argument("--frontend-dist", default=None, help=argparse.SUPPRESS)
    b.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("versions", help="list knowledge versions on main and their tags")
    v.add_argument("--limit", type=int, default=40)
    v.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    v.set_defaults(func=cmd_versions)


def _inner_parser():
    p = argparse.ArgumentParser(prog="kb.share.build --inner")
    p.add_argument("--inner", action="store_true", required=True)
    for name in ("out", "profile", "content-ref", "content-sha", "kb-version", "viewer-sha", "built-at"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument(APP_FLAG, default=None, help="the built app's index.html: render the app layout, not the shell")
    return p


if __name__ == "__main__":
    try:
        _args = _inner_parser().parse_args()
        sys.exit((inner_build_app if _args.app_index else inner_build)(_args))
    except BuildError as e:
        print(f"share build: {e}", file=sys.stderr)
        sys.exit(1)

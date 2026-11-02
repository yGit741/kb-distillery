"""Build the shared site (the React app + the wiki data) from a git ref (0 LLM).

    pixi run share -- build <ref> [--profile private|public] [--viewer <ref>] [--open] [--viewer-worktree]
    pixi run share -- versions

Two processes:

* **outer** (`build()`): resolves refs, `git archive`s the *content* ref into a temp `content/` and the *viewer*
  ref's code into a temp `viewer/` (tracked files only: never the working tree, never gitignored raw/ binaries), then runs
  the viewer's own copy of this module (`python -m kb_distillery.publish.site.build --inner …`, cwd=viewer/, `KB_ROOT=content/`)
  so old content is rendered by whichever viewer code was asked for. Writes `index.html` + `assets/` + `manifest.json`
  under `.exported/share/<ref>-app/`.
* **inner** (`--inner`): collects the graph, the explorer index and every page from `KB_ROOT` through the services
  builders, normalises them (commit date instead of wall clock, sorted nodes/links), applies the profile and bakes the
  result into the built app's `index.html` as `<script type="application/json" id="kb-data">` (the id `share audit`
  scans).

A `<ref>` is `main`, any commit-ish, a `kb-x.y.z` tag, or a bare knowledge version `x.y.z` (resolved through the
`KB-Version` trailers on main). `built_at` is the content commit's date, so the same content + viewer + profile always
yields the same bytes.

The app is `web/` built with `vite build --mode share`, one build per profile so the route set is fixed at build time
(`web/src/routes/modules.share-<profile>.ts`, generated from the `screen.*` flags): public = Home, Graph, Pages; private
adds Lifecycle, Start and the Share panel. Chat, ops, pipeline and scopes are not imported at all. The private profile also
carries the Lifecycle snapshot of the content commit (`collect_lifecycle`: its first-parent history, versions and
annotated `kb-*` tags; nothing about the working tree, remotes or the nightly job). The public profile carries none of it.
`manifest.json` has `layout: "app"` and `sha256` = the digest of the tree; the Worker serves it with a single-page-app
fallback. See .claude/skills/share-kb/SKILL.md.
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

from kb_distillery.core import links as page_links
from kb_distillery.webbuild import frontend_source_hash as _frontend_source_hash

from kb_distillery.publish.cloudflare.contracts import EXPORT_DIR, PROFILES, REPO, BuildResult, Manifest, raw_is_email
from kb_distillery.publish.site.home import ShareConfigError, apply_home, load_home, strip_my_notes
from kb_distillery.publish.site.predicate import add_predicate_args, predicate_fn

FRONTEND_DIR = REPO / "web"
APP_FLAG = "--app-index"      # the inner CLI flag a viewer must know to render the app layout
# The real repo (the one `git archive` read from): the inner build runs read-only history commands
# there, at the content sha, for the Lifecycle snapshot (private profile). Unset → no Lifecycle.
GIT_ROOT_ENV = "KB_SHARE_GIT_ROOT"
RAW_ROOT_ENV = "KB_SHARE_RAW_ROOT"
LIFECYCLE_LIMIT = 150          # timeline rows
LIFECYCLE_WINDOW_DAYS = 30     # stats.ops_30d, counted back from the content commit date

PRIVATE_DATA_KEYS = ("digestion", "lifecycle")   # kb-data keys that exist in private builds only (the public cut drops them)

PUBLIC_DROP_KEYS = ("raw", "path", "email", "original_name", "scopes", "generated")     # generated: names the owner
# Not content: scopes are private working sets and distilled-think pages are transient review drafts.
# LLM chats and person pages (profiles built from public sources) are the owner's and are public.
PUBLIC_EXCLUDE_TYPES = frozenset({"distilled-think", "scope"})
_VIEW_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")   # a story id in web/src/features/graph/lab/views.ts

_ABS_PATH = re.compile(r"^/|^~/|/Users/|OneDrive|\\\\Users\\\\")

VERSION_RE = re.compile(r"^(?:kb-)?(\d+)\.(\d+)\.(\d+)$")
_GITHUB_REMOTE = re.compile(r"^(?:https?://|ssh://)?(?:[\w.-]+@)?github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


# Cloudflare Workers serves the page from the static-assets directory, which caps one file at
# 25 MiB; a build above that cannot be deployed at all. The page grows with the wiki (each page's
# body and the graph are embedded), so the builder says how close it is
# instead of a test discovering it: a warning from 80 % up, a BuildError at the limit.
MAX_HTML_BYTES = 25 * 1024 * 1024
WARN_HTML_BYTES = int(MAX_HTML_BYTES * 0.8)


def size_verdict(n_bytes, name="index.html"):
    """None when fine, a warning string from WARN_HTML_BYTES, raises BuildError at MAX_HTML_BYTES."""
    mb = n_bytes / 1_048_576
    if n_bytes > MAX_HTML_BYTES:
        raise BuildError(f"{name} is {mb:.1f} MB, over the {MAX_HTML_BYTES / 1_048_576:.0f} MB "
                         "Cloudflare static-asset limit — it cannot be deployed; shrink the page "
                         "(embedded pages) before sharing")
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
        from kb_distillery.git import commit_policy
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
    from kb_distillery.git import commit_policy
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


APP_LAYOUT = "src/kb_distillery/publish/site/build.py"       # viewer code since publish/ absorbed share/
APP_LAYOUT_SHARE = "src/kb_distillery/share/build.py"        # ... before that (package kb_distillery, share/)
APP_LAYOUT_OLD = "backend/src/kb/share/build.py"             # ... and before the move to src/kb_distillery (package kb)
# app-layout generations, newest first: (probe file, archive pathspec, PYTHONPATH under the viewer dir, inner module).
# An older viewer ref keeps building with its own module path, so the retired names stay here and nowhere else.
APP_GENERATIONS = ((APP_LAYOUT, "src", "src", "kb_distillery.publish.site.build"),
                   (APP_LAYOUT_SHARE, "src", "src", "kb_distillery.share.build"),
                   (APP_LAYOUT_OLD, "backend", os.path.join("backend", "src"), "kb.share.build"))


def viewer_gen(root, sha=None):
    """The APP_GENERATIONS row of the viewer ref `sha` (or, with no sha, of the checkout at `root`), else None."""
    for gen in APP_GENERATIONS:
        if sha is None:
            ok = os.path.isfile(os.path.join(str(root), gen[0]))
        else:
            ok = subprocess.run(["git", "cat-file", "-e", f"{sha}:{gen[0]}"], cwd=str(root),
                                capture_output=True, check=False).returncode == 0
        if ok:
            return gen
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


# ---------- data ----------

def _epoch(iso):
    iso = iso[:-1] + "+00:00" if iso.endswith("Z") else iso  # git prints UTC as Z; py<3.11 can't parse it
    return int(_dt.datetime.fromisoformat(iso).timestamp())


def collect_data(meta_dir, built_at, content_sha):
    """Graph snapshot, explorer index and every page, read from KB_ROOT through the viewer's builders."""
    meta_dir = str(meta_dir)
    from kb_distillery.services import pages as explore_data
    from kb_distillery.graph import snapshot as graph_data  # noqa: WPS433 (viewer code)
    from kb_distillery.search.semfind import load_pages

    pages = load_pages()
    cached = lambda root=None: pages  # noqa: E731
    graph_data.load_pages = cached
    explore_data.load_pages = cached
    graph_memo = {}
    orig_graph = explore_data._graph

    def memo_graph(p, titles=None):
        if id(p) not in graph_memo:
            graph_memo[id(p)] = orig_graph(p, titles)
        return graph_memo[id(p)]

    explore_data._graph = memo_graph
    epoch = _epoch(built_at)
    explore_data._mtime = lambda rel, root=None: epoch
    graph_data._etag = lambda p, root=None: content_sha[:16]
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


def collect_lifecycle(meta_dir, built_at, git_root, content_sha, content_dir, content_ref=""):
    """The Lifecycle snapshot as of the content commit: its first-parent history, versions,
    annotated kb-* tags on that history and the migration state in the checkout. Nothing about
    the working tree, remotes, worktrees or the nightly job — none of that is fixed by the sha."""
    meta_dir = str(meta_dir)
    from kb_distillery.git import commit_policy as cp  # noqa: WPS433 (viewer code)
    from kb_distillery.ops.history import timeline
    from kb_distillery.ops.migrate import _applied, pending_migrations
    from kb_distillery.core.schema import GIT_POLICY_MODE, OPS_STRICT, SCHEMA_VERSION

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


def scope_keep(slug, hops=1):
    """Slugs a scoped build keeps: the `slug` page (a scope, collection or person), its corpus members'
    pages (`kb_distillery.core.scopes.projection`: hop0 + ideas/questions shared by >= 2 of them) and, with
    `hops=1`, every page linked to or from that set. Read from KB_ROOT (the content checkout)."""
    from kb_distillery.core import scopes as core
    from kb_distillery.lint.lint import read_manifest
    from kb_distillery.paths import vault_root
    from kb_distillery.services.scopes import load_pages
    root = vault_root()
    pages = load_pages(root)
    if slug not in pages:
        raise BuildError(f"--scope {slug!r}: no such page at this ref")
    manifest = read_manifest(root)
    if pages[slug][1].get("type") == "scope":
        rows = core.rows_of(slug, manifest)
    else:
        rows = sorted(p for p, r in manifest.items() if slug in core.collections_of(r))
    index = core.build_index(pages)
    proj = core.projection(rows, pages, manifest, index)
    keep = {slug, *proj["hop0"], *proj["hop1"]}
    if hops:
        ring = set()
        for s in keep:
            ring |= set(index["out"].get(s, ()))
            ring |= {t for t, outs in index["out"].items() if s in outs}
        keep |= {s for s in ring if s in pages}
    return keep


_SCOPE_WIKILINK = re.compile(r"\[\[([^\]|#\\]+)(#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]")

_SLUG_LIST = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:, [a-z0-9]+(?:-[a-z0-9]+)*)+$")


def _unlink(value, drop, titles):
    """A scoped build names no dropped page: `[label](dropped.md)` / `[[dropped|label]]` → label (else its title) as plain
    text in strings, dropped slugs removed from lists — recursively through frontmatter/properties."""
    if isinstance(value, str):
        if value.strip() in drop or (value.strip().endswith(page_links.PAGE_SUFFIX)
                                     and page_links.page_slug(value) in drop):       # a `related` page path
            return None
        if _SLUG_LIST.match(value):              # graph properties join list fields with ", "
            return ", ".join(s for s in value.split(", ") if s not in drop)
        value = page_links.PAGE_LINK.sub(lambda m: page_links.link_parts(m)[0]
                                         if page_links.link_parts(m)[1] in drop else m.group(0), value)
        return _SCOPE_WIKILINK.sub(lambda m: (m.group(3) or titles.get(m.group(1).strip()) or m.group(1)).strip()
                                   if m.group(1).strip() in drop else m.group(0), value)
    if isinstance(value, list):
        return [v for v in (_unlink(x, drop, titles) for x in value) if v is not None]
    if isinstance(value, dict):
        out = {k: v for k, v in ((k, _unlink(x, drop, titles)) for k, x in value.items()) if v is not None}
        return None if "resource" in value and "resource" not in out else out      # a `sources` entry for a dropped page
    return value


def apply_profile(data, profile, scope_slugs=None):
    """`scope_slugs` (public only): a set from `scope_keep` — every other page, node, card, link,
    backlink and search entry is dropped through the same `drop` set as the type/email cuts."""
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
    if scope_slugs is not None:
        drop |= {n["id"] for n in graph["nodes"] if n["id"] not in scope_slugs}
        drop |= {c["id"] for c in index["pages"] if c["id"] not in scope_slugs}
        drop |= {s for s in pages if s not in scope_slugs}
        unlink_dropped(data, drop)
    drop_pages(data, drop)
    graph, pages = data["graph"], data["pages"]
    schema = graph.get("schema")
    if schema:                                   # private-only types are not even named publicly
        schema["types"] = [t for t in schema["types"] if t["id"] not in PUBLIC_EXCLUDE_TYPES]
        for layer in schema.get("layers", []):
            layer["types"] = [t for t in layer["types"] if t not in PUBLIC_EXCLUDE_TYPES]
    for n in graph["nodes"]:
        n.pop("path", None)
        props = n.get("properties") or {}
        for k in PUBLIC_DROP_KEYS:
            props.pop(k, None)
    for p in pages.values():
        p.pop("path", None)
        if "markdown" in p:                      # the synthesis is public, the user's own notes are not
            p["markdown"] = strip_my_notes(p["markdown"])
        fm = p.get("frontmatter") or {}
        for k in PUBLIC_DROP_KEYS:
            fm.pop(k, None)
    return data


def unlink_dropped(data, drop):
    """A subset build names no dropped page: `[label](dropped.md)` / `[[dropped|label]]` → label (else its title) as plain text,
    dropped slugs removed from list fields (related, sources, …) — in every kept node, card and body
    (`_unlink`, recursive through frontmatter / properties). Before `drop_pages`, while titles are known."""
    graph, index, pages = data["graph"], data["index"], data["pages"]
    titles = {s: (p.get("card") or {}).get("title") for s, p in pages.items() if s in drop}
    titles.update({n["id"]: n.get("title") for n in graph["nodes"] if n["id"] in drop and n.get("title")})
    for n in graph["nodes"]:
        if n["id"] not in drop:
            n.update(_unlink({k: v for k, v in n.items() if k not in ("id", "type")}, drop, titles))
    for c in index["pages"]:
        if c["id"] not in drop:
            c.update(_unlink({k: v for k, v in c.items() if k not in ("id", "type")}, drop, titles))
    for slug, pg in pages.items():
        if slug not in drop:
            pg.update(_unlink({k: v for k, v in pg.items() if k not in ("backlinks", "outbound", "suggested", "card")},
                              drop, titles))
            if pg.get("card"):
                pg["card"] = dict(pg["card"], **_unlink({k: v for k, v in pg["card"].items() if k not in ("id", "type")},
                                                       drop, titles))
    return data


def drop_pages(data, drop):
    """Remove every page in `drop` from the blob, wherever a slug can surface: graph nodes, links and
    concept links, the explorer index (cards, link pairs, wanted-from), the page bodies and their
    backlinks / outbound / suggested lists. Counts and type facets are recomputed. In place; returns `data`."""
    graph, index, pages = data["graph"], data["index"], data["pages"]
    keep = lambda s: s not in drop  # noqa: E731
    graph["nodes"] = [n for n in graph["nodes"] if keep(n["id"])]
    graph["links"] = [l for l in graph["links"] if keep(l["source"]) and keep(l["target"])]
    concept_links = []
    for l in graph.get("concept_links") or []:
        if not (keep(l["source"]) and keep(l["target"])):
            continue
        if "via" in l:
            l["via"] = [v for v in l["via"] if keep(v)]
        concept_links.append(l)
    graph["concept_links"] = concept_links
    graph["node_count"] = len(graph["nodes"])
    graph["link_count"] = len(graph["links"])
    facets = graph.get("facets") or {}
    facets["types"] = sorted({n.get("type", "unknown") for n in graph["nodes"]})
    graph["facets"] = facets

    index["pages"] = [c for c in index["pages"] if keep(c["id"])]
    index["links"] = [l for l in index["links"] if keep(l[0]) and keep(l[1])]
    for w in index.get("wanted", []):
        w["from"] = [s for s in w.get("from", []) if keep(s)]

    out_pages = {}
    for slug, p in pages.items():
        if not keep(slug):
            continue
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


def apply_predicate(data, predicate):
    """After `apply_profile`: keep only the nodes passing `predicate` (`kb_distillery.publish.site.predicate`), and drop
    everything that names a failing page (links, cards, bodies, search entries — `drop_pages`).
    Returns (data, dropped) where `dropped` is the number of graph nodes removed; no predicate → (data, 0).

    The test reads each node's `inDegree` / `outDegree` as the graph snapshot computed them on the
    FULL graph, before the public profile or this cut removed any neighbour — the same numbers
    `/api/graph` reports and the app's `isPublic` sees."""
    test = predicate_fn(predicate)
    if test is None:
        return data, 0
    graph = data["graph"]
    drop = {n["id"] for n in graph["nodes"] if not test(n)}
    dropped = len(drop)                                   # graph nodes removed — what the manifest reports
    present = {n["id"] for n in graph["nodes"]}
    # a card or body without a graph node has no degrees to judge: it goes with the dropped ones
    drop |= {c["id"] for c in data["index"]["pages"] if c["id"] not in present}
    drop |= {s for s in data["pages"] if s not in present}
    unlink_dropped(data, drop)                            # no kept page names a dropped slug
    drop_pages(data, drop)
    return data, dropped


# ---------- data blob ----------

def embed_json(obj):
    """Compact, key-sorted JSON safe inside a <script> element."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.replace("</", "\\u003c/").replace("<!--", "\\u003c!--")


def _scope_arg(args):
    return scope_keep(args.scope, int(args.hops)) if getattr(args, "scope", None) else None


def write_stats(path, dropped):
    """What the inner build learnt that the manifest records — `{"dropped": n}`, the graph nodes the
    predicate removed — written to `--stats <path>` (a file in the outer build's temp dir, never the
    published directory); no path → nothing written."""
    if path:
        Path(path).write_text(json.dumps({"dropped": dropped}), encoding="utf-8")


def read_stats(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


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


def raw_paths_of(nodes):
    """{source slug: its first raw/... file} from the graph nodes' `raw` property."""
    out = {}
    for n in nodes:
        raw = (n.get("properties") or {}).get("raw") or ""
        first = next((r.strip() for r in str(raw).replace("[", "").replace("]", "").split(",") if r.strip().startswith("raw/")), None)
        if first:
            out[n["id"]] = first
    return out


def bake_raw_cards(data, raw_of, profile):
    """Home pipeline cards for the kept sources (kb_distillery.services.raw_card), read from the real working tree:
    raw PDFs are not tracked, so the content checkout has none. Public: the privacy column, no file names."""
    from kb_distillery.services.raw_card import bake_cards
    root = os.environ.get(RAW_ROOT_ENV) or os.environ.get("KB_ROOT", ".")
    return bake_cards(data["graph"]["nodes"], raw_of, root, public=profile != "private")


def inner_build_app(args):
    """Inside the viewer checkout, KB_ROOT = content: the wiki data baked into the built app's page."""
    try:
        home = load_home(strict=True)       # first: a build without its share config stops before any work
    except ShareConfigError as e:
        raise BuildError(str(e)) from None
    meta_dir = Path(__file__).resolve().parents[2]
    fields = {"content_ref": args.content_ref, "content_sha": args.content_sha,
              "kb_version": args.kb_version, "viewer_sha": args.viewer_sha,
              "profile": args.profile, "built_at": args.built_at}
    data = collect_data(meta_dir, args.built_at, args.content_sha)
    git_root = os.environ.get(GIT_ROOT_ENV)
    if args.profile == "private" and git_root and os.path.isdir(git_root):
        data["lifecycle"] = collect_lifecycle(meta_dir, args.built_at, git_root, args.content_sha,
                                              os.environ.get("KB_ROOT", "."), args.content_ref)
    raw_of = raw_paths_of(data["graph"]["nodes"])             # before the public cut drops `raw`
    data = apply_profile(data, args.profile, _scope_arg(args))      # the one place the public cuts live
    data, dropped = apply_predicate(data, args.predicate)          # --predicate public: the Map view's pages only
    data = apply_home(data, home, view=args.view)   # Home cards + tour from share.toml `[home]`, --view
    data["rawCards"] = bake_raw_cards(data, raw_of, args.profile)
    page = app_page(Path(args.app_index).read_text(encoding="utf-8"), data, fields)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    write_stats(args.stats, dropped)
    print(f"{out} ({len(data['graph']['nodes'])} nodes, {len(data['pages'])} pages, {out.stat().st_size // 1024} KB)")
    return 0


def frontend_source_hash(frontend=FRONTEND_DIR):
    """Digest of what the share bundle is made of (the algorithm lives in `kb_distillery.webbuild`, which core uses too)."""
    return _frontend_source_hash(frontend)


def ensure_frontend_dist(profile, frontend=FRONTEND_DIR, runner=None):
    """`web/dist-share/<profile>/` built from the current sources (rebuilt when they changed).

    `vite build --mode share` with VITE_SHARE_PROFILE=<profile>; needs `pixi run web-install` once."""
    frontend = Path(frontend)
    dist = frontend / "dist-share" / profile
    stamp = dist / ".src-hash"
    want = frontend_source_hash(frontend)
    if (dist / "index.html").is_file() and stamp.is_file() and stamp.read_text().strip() == want:
        return dist
    if not (frontend / "node_modules").is_dir():
        raise BuildError("web/node_modules is missing — run `pixi run web-install` once, then retry")
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
    """x of SCHEMA_VERSION = (x, y) in the schema at `sha` (src/kb_distillery/core/schema.py, or meta/schema.py
    before the app layout), or None."""
    for rel in ("src/kb_distillery/core/schema.py", "backend/src/kb/core/schema.py", "meta/schema.py"):
        cp = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(root), capture_output=True,
                            text=True, check=False)
        m = _SCHEMA_RE.search(cp.stdout or "") if cp.returncode == 0 else None
        if m:
            return int(m.group(1))
    return None


STORIES_FILE = "web/src/features/graph/lab/views.ts"
_STORY_ID = re.compile(r'^\s*id:\s*"([a-z0-9-]+)"', re.M)


def story_ids(viewer_root, viewer_sha=None):
    """The graph view ids the viewer knows (`STORIES[].id` in views.ts): from the working tree when
    `viewer_sha` is None, else from that commit. None when the file cannot be read."""
    try:
        if viewer_sha is None:
            text = (Path(viewer_root) / STORIES_FILE).read_text(encoding="utf-8")
        else:
            text = _git(viewer_root, "show", f"{viewer_sha}:{STORIES_FILE}")
    except (OSError, subprocess.CalledProcessError, BuildError):
        return None
    ids = _STORY_ID.findall(text or "")
    return ids or None


def build(content_ref, viewer_ref="main", profile="private", *, root=REPO, viewer_root=None,
          out_root=EXPORT_DIR, viewer_worktree=False, label=None, frontend_dist=None,
          scope=None, hops=1, predicate=None, view=None):
    """Build `content_ref` with the viewer at `viewer_ref` → BuildResult(dir, manifest).

    `predicate="public"` (public profile only) keeps just the pages the app's Map view draws
    (`kb_distillery.publish.site.predicate.is_public`); `view` is the graph view id the app opens on (`home.view`
    in the blob). Both land in the manifest.

    `root` is the repo the content comes from; `viewer_root` (default: the same repo) is where
    the viewer code is taken from — a committed ref, or its working tree with `viewer_worktree`.

    `frontend_dist` is the built app, `web/dist-share/<profile>` (default: built, or reused when the sources are
    unchanged, from this checkout's `web/`).
    """
    root = Path(root)
    viewer_root = Path(viewer_root or root)
    if scope and profile != "public":
        raise BuildError("--scope builds a public subset; use --profile public")
    if predicate and profile != "public":
        raise BuildError("--predicate builds a public subset; use --profile public")
    try:
        predicate_fn(predicate)
    except ValueError as e:
        raise BuildError(str(e)) from None
    if view and not _VIEW_ID.match(view):
        raise BuildError(f"--view {view!r}: a view id is lowercase [a-z0-9-]")
    predicate = predicate or None
    view = view or None
    if profile not in PROFILES:
        raise BuildError(f"unknown profile {profile!r}; choose one of {', '.join(PROFILES)}")
    content_sha = resolve_ref(root, content_ref)
    built_at = commit_date(root, content_sha)
    kb_version = kb_version_of(root, content_sha, content_ref)
    own_viewer = ""
    if viewer_ref == "main" and not viewer_worktree:
        # A paradigm change (schema x.0) renames types; the new viewer keeps no aliases for the old
        # names. Content from another paradigm is rendered by the viewer of its own commit.
        cmaj, vmaj = schema_major(root, content_sha), schema_major(viewer_root, resolve_ref(viewer_root, "main"))
        if cmaj is not None and vmaj is not None and cmaj != vmaj:
            print(f"share build: {content_ref} is schema {cmaj}.x, main is {vmaj}.x — rendering it "
                  "with its own viewer", file=sys.stderr)
            viewer_ref = content_sha
            own_viewer = f"{content_ref} is schema {cmaj}.x (main is {vmaj}.x), so only its own viewer can render it, and "
    if viewer_worktree:
        viewer_sha = _rev_parse(viewer_root, "HEAD") or "worktree"
    else:
        viewer_sha = resolve_ref(viewer_root, viewer_ref)
    if view:
        known = story_ids(viewer_root, None if viewer_worktree else viewer_sha)
        if known is None:
            print(f"share build: cannot read the viewer's view list ({STORIES_FILE}); --view {view!r} checked for syntax only",
                  file=sys.stderr)
        elif view not in known:
            print(f"share build: --view {view!r} is not a view of this viewer ({', '.join(known)}); "
                  "the app will ignore it", file=sys.stderr)
    out_dir = Path(out_root) / (_safe_name(label or content_ref) + ("" if label else "-app"))
    dist = Path(frontend_dist) if frontend_dist else ensure_frontend_dist(profile)
    if not (dist / "index.html").is_file():
        raise BuildError(f"{dist} has no index.html — build the frontend first (pixi run web-install)")
    with tempfile.TemporaryDirectory(prefix="kb-share-") as tmp:
        content_dir = os.path.join(tmp, "content")
        archive(root, content_sha, content_dir)
        if viewer_worktree:
            viewer_dir = str(viewer_root)
            gen = viewer_gen(viewer_dir)
        else:
            viewer_dir = os.path.join(tmp, "viewer")
            gen = viewer_gen(viewer_root, viewer_sha)
            if gen:
                archive(viewer_root, viewer_sha, viewer_dir, (gen[1],))
        if gen is None:
            raise BuildError(f"{own_viewer}viewer {viewer_ref} ({viewer_sha[:7]}) has no app-layout share builder (src/kb_distillery/publish/site/build.py) — "
                             "the shared site is the React app only; pick a viewer ref that contains it (--viewer <branch|sha>), "
                             "or --viewer-worktree to use this checkout's code")
        if APP_FLAG not in (Path(viewer_dir) / gen[0]).read_text(encoding="utf-8"):
            raise BuildError(f"viewer {viewer_ref} ({viewer_sha[:7]}) predates the app layout (no {APP_FLAG}) — "
                             "use --viewer-worktree, or a viewer ref that contains it")
        html_path = Path(tmp) / "app-index.html"   # assembled into out_dir below, after the guard
        out_dir.mkdir(parents=True, exist_ok=True)
        # PYTHONHASHSEED=0: set iteration order in the viewer's data builders (e.g. tie-breaks in
        # explore_data._suggest) must not vary between runs or machines. KB_CI=1: the content
        # checkout has no raw binaries (gitignored) — lint must trust meta/corpus.tsv and never
        # regenerate wiki/index.md/corpus.tsv. KB_SHARE_GIT_ROOT: the real repo, for history reads.
        env = dict(os.environ, KB_ROOT=content_dir, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0",
                   KB_CI="1")
        env["PYTHONPATH"] = os.path.join(viewer_dir, gen[2])     # the viewer's own kb package, not whatever is installed
        env.pop(GIT_ROOT_ENV, None)
        # the export has no history: the pages' added / changed dates, at the content commit, come in a file
        from kb_distillery.graph import snapshot as graph_data  # noqa: WPS433

        dfile = os.path.join(tmp, "graph-dates.json")
        with open(dfile, "w", encoding="utf-8") as f:
            json.dump(graph_data._git_dates(str(root), content_sha), f)
        env[graph_data.DATES_ENV] = dfile
        env[RAW_ROOT_ENV] = str(root)        # Home raw cards read raw/ from the working tree (both profiles)
        if profile == "private":
            env[GIT_ROOT_ENV] = str(root)
        cmd = [sys.executable, "-m", gen[3], "--inner",
               "--out", str(html_path), "--profile", profile,
               "--content-ref", content_ref, "--content-sha", content_sha,
               "--kb-version", kb_version, "--viewer-sha", viewer_sha, "--built-at", built_at,
               APP_FLAG, str(dist / "index.html")]
        if scope:
            cmd += ["--scope", scope, "--hops", str(int(hops))]
        stats_path = os.path.join(tmp, "stats.json")
        if predicate:
            cmd += ["--predicate", predicate, "--stats", stats_path]
        if view:
            cmd += ["--view", view]
        proc = subprocess.run(cmd, cwd=viewer_dir, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
            hint = ""
            if (predicate or view) and "unrecognized arguments" in (proc.stderr or ""):
                hint = ("\nhint: this viewer predates --predicate/--view — use --viewer-worktree or a viewer ref "
                        "that has kb_distillery.publish.site.predicate (--viewer <branch|sha>)")
            raise BuildError("inner build failed in viewer %s:\n%s%s" % (viewer_sha[:7], "\n".join(tail), hint))
        dropped = int(read_stats(stats_path).get("dropped", 0)) if predicate else None
        for rel in tree_files(dist):       # the 25 MiB guard applies to every file the Worker serves
            if not (rel == "index.html" or rel.startswith(".")):
                size_verdict((dist / rel).stat().st_size, rel)
        warning = size_verdict(html_path.stat().st_size)
        if warning:
            print(f"share build: {warning}", file=sys.stderr)
        assemble_app(dist, html_path, out_dir)
    manifest = Manifest(content_ref=content_ref, content_sha=content_sha, kb_version=kb_version,
                        viewer_sha=viewer_sha, profile=profile, sha256=tree_digest(out_dir),
                        built_at=built_at, layout="app", scope=scope, hops=int(hops) if scope else None,
                        predicate=predicate, dropped=dropped, view=view)
    (out_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    return BuildResult(dir=out_dir, manifest=manifest)


def versions(root=REPO, rev="main"):
    """Knowledge steps on `rev` (default main; newest first) with their tags: [{version, sha, date, subject, tags}]."""
    from kb_distillery.git import commit_policy
    from kb_distillery.ops.core import snapshots
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
                       scope=args.scope, hops=args.hops, predicate=args.predicate, view=args.view,
                       viewer_worktree=args.viewer_worktree,
                       frontend_dist=args.frontend_dist)
    except BuildError as e:
        print(f"share build: {e}", file=sys.stderr)
        return 1
    m = result.manifest
    html = result.dir / "index.html"
    print(f"{html}  ({html.stat().st_size / 1_048_576:.1f} MB of {MAX_HTML_BYTES / 1_048_576:.0f} MB)")
    total = sum((result.dir / rel).stat().st_size for rel in tree_files(result.dir))
    print(f"app layout: {len(tree_files(result.dir))} files, {total / 1_048_576:.1f} MB in total")
    print(f"kb {m.kb_version} · {m.content_sha[:7]} · viewer {m.viewer_sha[:7]} · {m.profile} · "
          f"built {m.built_at} · sha256 {m.sha256[:12]}")
    if args.open:
        webbrowser.open(html.resolve().as_uri())
    return 0


def register(sub):
    b = sub.add_parser("build", help="build the React app with the wiki data of a git ref baked in")
    b.add_argument("ref", help="main, a commit, a kb-x.y.z tag or a knowledge version x.y.z")
    b.add_argument("--profile", choices=PROFILES, default="private")
    b.add_argument("--viewer", default="main", help="ref whose code renders the site (default main)")
    b.add_argument("--open", action="store_true", help="open the result in the browser")
    b.add_argument("--scope", default=None, metavar="SLUG",
                   help="public only: keep this scope / collection / person page, its members and their neighbours")
    b.add_argument("--hops", type=int, choices=(0, 1), default=1, help="with --scope: 1 adds linked neighbours (default)")
    add_predicate_args(b)
    b.add_argument("--viewer-worktree", action="store_true",
                   help="dev only: use this worktree's code instead of a committed ref")
    b.add_argument("--app", action="store_true", help=argparse.SUPPRESS)      # the only layout now; accepted for old scripts
    b.add_argument("--frontend-dist", default=None, help=argparse.SUPPRESS)
    b.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("versions", help="list knowledge versions on main and their tags")
    v.add_argument("--limit", type=int, default=40)
    v.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    v.set_defaults(func=cmd_versions)


def _inner_parser():
    p = argparse.ArgumentParser(prog="kb_distillery.publish.site.build --inner")
    p.add_argument("--inner", action="store_true", required=True)
    for name in ("out", "profile", "content-ref", "content-sha", "kb-version", "viewer-sha", "built-at"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--scope", default=None)
    p.add_argument("--hops", default="1")
    p.add_argument("--predicate", default=None)
    p.add_argument("--view", default=None)
    p.add_argument("--stats", default=None, help="write {dropped} here (the outer build's temp dir)")
    p.add_argument(APP_FLAG, required=True, help="the built app's index.html, which the data blob is baked into")
    return p


if __name__ == "__main__":
    try:
        _args = _inner_parser().parse_args()
        sys.exit(inner_build_app(_args))
    except BuildError as e:
        print(f"share build: {e}", file=sys.stderr)
        sys.exit(1)

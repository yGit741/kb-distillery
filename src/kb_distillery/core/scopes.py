"""Scopes (schema 0.13): personal working sets of RAW files. Pure functions, no network, no I/O.

A scope is a set of corpus rows (corpus.tsv column `scopes`, comma-separated `scope-*` slugs) plus a
wiki page `wiki/scope-<slug>.md` with a hand-owned `## Why` and a lint-generated `## Members`.
Raw files never move, knowledge pages may split or rename, so the knowledge subgraph of a scope is
a PROJECTION computed on the fly from the rows:

    hop0  pages whose `raw:` (or corpus `slug`) is a scope row
    hop1  idea/question pages linked (wikilinks / related) by >= 2 hop0 pages

Coverage = scope rows source|partial over the rows that can be digested at all (skip, asset, ink,
dupe and sidecar rows are ignored). Uncovered = queued rows.

`pages` is the lint shape `{slug: (rel, frontmatter, text)}`; `manifest` is `{path: row dict}`.
"""
import os
import re
import sys

from kb_distillery.core import frontmatter
from kb_distillery.core.graph import outbound_links
from kb_distillery.core.schema import COLLECTION_TYPES, SOURCE_TYPES, SLUG_PREFIX
from kb_distillery.core import links as page_links
from kb_distillery.core.schema import is_page_file

PREFIX = SLUG_PREFIX["scope"]
MEMBERS_HEADING = "## Members"
WHY_HEADING = "## Why"
MARKER = "<!-- generated: scopes — rewritten by lint; edit ## Why, never this section -->"
COMPANIONS = ("asset:", "ink:", "dupe:")
HOP1_MIN = 2
HOP1_TYPES = ("idea", "question")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


# ---------------------------------------------------------------- rows

def split_cell(cell):
    return [c.strip() for c in (cell or "").split(",") if c.strip()]


def scopes_of_row(row):
    """corpus `scopes` cell → list of scope slugs."""
    return split_cell((row or {}).get("scopes"))


def all_scopes(manifest):
    return sorted({s for r in manifest.values() for s in scopes_of_row(r)})


def rows_of(scope_slug, manifest):
    return sorted(p for p, r in manifest.items() if scope_slug in scopes_of_row(r))


def is_companion(row):
    """asset/ink/dupe/sidecar rows ride with their parent: never members, never backlog."""
    d = (row or {}).get("disposition") or ""
    return d == "sidecar" or d.startswith(COMPANIONS)


def is_member_path(path):
    parts = path.split("/")
    return path.startswith("raw/") and len(parts) >= 3 and parts[1] != "inbox" and ".." not in parts


def raw_paths(fm):
    v = (fm or {}).get("raw")
    vals = v if isinstance(v, list) else [v]
    return [str(x).strip() for x in vals if x and str(x).strip() and str(x).strip() != "none"]


def collections_of(row):
    return split_cell((row or {}).get("collection"))


def write_scope_rows(manifest_rows, slug, paths):
    """Mutate `scopes` cells: `slug` on exactly `paths`, removed from every other row.
    Returns (added, removed) path lists."""
    want = set(paths)
    added, removed = [], []
    for p, r in manifest_rows.items():
        cur = scopes_of_row(r)
        if p in want and slug not in cur:
            r["scopes"] = ",".join(sorted(set(cur) | {slug}))
            added.append(p)
        elif p not in want and slug in cur:
            r["scopes"] = ",".join(sorted(set(cur) - {slug}))
            removed.append(p)
    return sorted(added), sorted(removed)


def delete_scope(manifest_rows, slug):
    return write_scope_rows(manifest_rows, slug, [])[1]


# ---------------------------------------------------------------- indexes

def build_index(pages):
    """Computed once per lint/API call: raw path → citing slugs, slug → outbound links, inbound."""
    raw_to = {}
    out = {}
    inbound = dict((s, set()) for s in pages)
    for slug, (_rel, fm, text) in pages.items():
        for p in raw_paths(fm):
            raw_to.setdefault(p, set()).add(slug)
        links = outbound_links(text, fm)
        out[slug] = links
        for t in links:
            if t in inbound and t != slug:
                inbound[t].add(slug)
    return dict(raw_to=raw_to, out=out, inbound=inbound)


def _ptype(pages, slug):
    return (pages.get(slug) or (None, dict(), ""))[1].get("type")


def _real_rows(paths, manifest):
    return [p for p in paths if p in manifest and not is_companion(manifest[p])]


# ---------------------------------------------------------------- projection

def projection(paths, pages, manifest, index=None):
    index = index or build_index(pages)
    paths = sorted(set(paths))
    real = _real_rows(paths, manifest)
    hop0, sources = set(), dict()
    for p in real:
        slugs = set(index["raw_to"].get(p, ()))
        row_slug = (manifest[p].get("slug") or "").strip()
        if row_slug in pages:
            slugs.add(row_slug)
        for s in slugs:
            if _ptype(pages, s) == "scope":
                continue
            hop0.add(s)
            sources.setdefault(s, []).append(p)
    counts = dict()
    for s in hop0:
        for t in index["out"].get(s, ()):
            if t not in hop0 and _ptype(pages, t) in HOP1_TYPES:
                counts[t] = counts.get(t, 0) + 1
    hop1 = sorted(t for t, n in counts.items() if n >= HOP1_MIN)

    covered = [p for p in real if manifest[p].get("disposition") in ("source", "partial")]
    uncovered = [p for p in real if manifest[p].get("disposition") == "queued"]
    skipped = [p for p in real if manifest[p].get("disposition") == "skip"]
    denom = len(covered) + len(uncovered)

    hub_of, hubs = dict(), set()
    for p in real:
        hs = [c for c in collections_of(manifest[p]) if _ptype(pages, c) in COLLECTION_TYPES]
        hub_of[p] = hs
        hubs.update(hs)
    themes = set()
    for s in hop0:
        area = pages[s][1].get("area") or []
        for a in [area] if isinstance(area, str) else area:
            if f"theme-{a}" in pages:
                themes.add(f"theme-{a}")
    return dict(
        hop0=sorted(hop0), hop1=hop1, covered=covered, uncovered=uncovered, skipped=skipped,
        coverage=(len(covered) / denom) if denom else None,
        hubs=sorted(hubs), themes=sorted(themes),
        sources=dict((s, sorted(v)) for s, v in sources.items()), hub_of=hub_of)


# ---------------------------------------------------------------- resolve (graph nodes → raw files)

HUBS_WITH_RAW = tuple(COLLECTION_TYPES)
UNITS = tuple(SOURCE_TYPES) + ("book", "notebook")


def resolve(node_ids, pages, manifest, mode="sources", index=None):
    """Graph node ids (wiki slugs or `raw:<path>`) → sorted unique member raw paths."""
    index = index or build_index(pages)
    out = set()

    def hub_rows(slug):
        return [p for p, r in manifest.items() if slug in collections_of(r)]

    for nid in node_ids:
        if nid.startswith("raw:"):
            out.add(nid[4:])
            continue
        if nid not in pages:
            continue
        fm = pages[nid][1]
        t = fm.get("type")
        if t in COLLECTION_TYPES:
            out.update(hub_rows(nid))
            out.update(raw_paths(fm))
        elif t == "person":
            out.update(hub_rows(nid))
        elif t == "topic":
            area = nid[len("theme-"):]
            for _s, (_r, f, _t) in pages.items():
                if f.get("type") in UNITS:
                    a = f.get("area") or []
                    if area in ([a] if isinstance(a, str) else a):
                        out.update(raw_paths(f))
        elif t in HOP1_TYPES:
            for s in set(index["inbound"].get(nid, ())) | set(index["out"].get(nid, ())):
                if _ptype(pages, s) in SOURCE_TYPES:
                    out.update(raw_paths(pages[s][1]))
        elif t in SOURCE_TYPES:
            out.update(raw_paths(fm))
        elif t == "scope":
            out.update(p for p, r in manifest.items() if nid in scopes_of_row(r))
    return sorted(p for p in out if p in manifest and not is_companion(manifest[p]) and is_member_path(p))


def citation_neighbors(slugs, cache=None):
    """Vault papers citing / cited by the given paper slugs (kb_distillery.search.citations cache). Silent -> []."""
    try:
        from kb_distillery.search import citations
        cache = cache if cache is not None else citations.load_cache()
        vids = citations.vault_ids(cache)
        found = set()
        for s in slugs:
            pid = cache.get("slugs", dict()).get(s)
            if not pid or pid not in cache.get("papers", dict()):
                continue
            o, i = citations.direct(cache, pid)
            found.update(vids[x] for x in (set(o) | set(i)) if x in vids)
        return sorted(found - set(slugs))
    except Exception:  # noqa: BLE001 — optional enrichment, never an error
        return []


# ---------------------------------------------------------------- scope context (scoped query)

class ScopeUnknown(Exception):
    """The slug names no scope page (and no corpus row carries it)."""


_CTX_CACHE = dict()


def _stamp(root):
    """Cheap change detector: corpus mtime + wiki dir mtime + newest wiki file mtime."""
    wiki = os.path.join(root, "wiki")
    try:
        names = [n for n in os.listdir(wiki) if is_page_file(n) or not n.endswith(".md")]
        newest = max([os.path.getmtime(os.path.join(wiki, n)) for n in names] or [0])
        return (os.path.getmtime(os.path.join(root, "meta", "corpus.tsv")), os.path.getmtime(wiki),
                newest, len(names))
    except OSError:
        return None


def scope_context(slug, root=None):
    """Everything a scoped question needs, from the vault at `root`:

        {slug, title, pages: set(hop0 + hop1 + the scope page), covered: [paths],
         uncovered: [{path, name, format}], coverage: float|None, rows: [every member path]}

    Raises ScopeUnknown for a slug that is not a scope. Cached per (root, slug) by corpus + wiki mtimes."""
    from kb_distillery.lint import lint
    root = os.path.abspath(root or lint.ROOT)
    stamp = _stamp(root)
    key = (root, slug)
    hit = _CTX_CACHE.get(key)
    if hit and stamp is not None and hit[0] == stamp:
        return hit[1]
    pages = dict()
    wiki = os.path.join(root, "wiki")
    for name in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not is_page_file(name) or "excalidraw" in name:
            continue
        with open(os.path.join(wiki, name), encoding="utf-8") as f:
            text = f.read()
        fm = lint.parse_frontmatter(text)
        if fm:
            pages[name[:-3]] = (f"wiki/{name}", fm, text)
    manifest = lint.read_manifest(root)
    is_scope = slug in pages and pages[slug][1].get("type") == "scope"
    paths = rows_of(slug, manifest)
    if not is_scope or not slug.startswith(PREFIX):
        raise ScopeUnknown(f"unknown scope {slug!r} (known: {', '.join(known_scopes(pages)) or 'none'})")
    proj = projection(paths, pages, manifest, build_index(pages))
    ctx = dict(slug=slug, title=title_of(pages[slug][2], slug),
               pages=set(proj["hop0"]) | set(proj["hop1"]) | {slug},
               covered=list(proj["covered"]), rows=list(paths),
               uncovered=[dict(path=p, name=os.path.basename(p), format=_fmt(p)) for p in proj["uncovered"]],
               coverage=proj["coverage"])
    _CTX_CACHE[key] = (stamp, ctx)
    return ctx


def known_scopes(pages):
    return sorted(s for s, (_r, fm, _t) in pages.items() if fm.get("type") == "scope")


def coverage_line(ctx):
    n_cov, n_unc = len(ctx["covered"]), len(ctx["uncovered"])
    total = n_cov + n_unc
    if not total:
        return "Coverage: no digestible files yet"
    return f"Coverage: {n_cov}/{total} files digested ({round(100 * n_cov / total)}%) · {n_unc} undigested"


# ---------------------------------------------------------------- page text

def section(text, heading):
    """Body of `## heading` up to the next `## ` heading ('' when absent)."""
    if heading not in text:
        return ""
    rest = text.split(heading, 1)[1]
    lines = rest.split("\n")
    end = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), len(lines))
    return "\n".join(lines[1:end]).strip("\n")


def why_text(text):
    """The hand-owned `## Why` without HTML comments ('' = empty)."""
    return _COMMENT.sub("", section(text, WHY_HEADING)).strip()


def why_links(text):
    return page_links.targets(why_text(text))


def title_of(text, slug=""):
    m = re.search(r"^# (.+)$", text.split("\n---", 1)[-1], re.M)
    return m.group(1).strip() if m else slug


def _fmt(path):
    parts = path.split("/")
    return parts[1] if len(parts) > 2 else ""


def _page(pages, slug):
    """A page link whose text is the page title (the text a reader showed for the old bare wikilink)."""
    return page_links.link(slug, page_links.shown_title(page_links.title_of(pages[slug][2], slug)) if slug in pages else slug)


def render_members(scope_slug, proj, pages):
    n_cov, n_unc = len(proj["covered"]), len(proj["uncovered"])
    total = n_cov + n_unc
    if total:
        cov = (f"**Coverage:** {n_cov}/{total} files digested ({round(100 * n_cov / total)}%)"
               f" · {n_unc} undigested")
    else:
        cov = "**Coverage:** no digestible files yet"
    out = [MARKER, "", cov, "", "### Covered", ""]
    if proj["hop0"]:
        out += ["| Page | Type | Digestion | Source |", "|------|------|-----------|--------|"]
        for s in proj["hop0"]:
            fm = pages[s][1]
            src = ", ".join(f"`{p}`" for p in proj["sources"].get(s, ()))
            out.append(f"| {_page(pages, s)} | {fm.get('type', '')} | {fm.get('depth', '') or '—'} | {src} |")
    else:
        out.append("_No digested pages yet._")
    out += ["", "### Uncovered", ""]
    if proj["uncovered"]:
        out += ["| Raw | Format | Hub |", "|-----|--------|-----|"]
        for p in proj["uncovered"]:
            hubs = ", ".join(_page(pages, h) for h in proj["hub_of"].get(p, ())) or "—"
            out.append(f"| `{p}` | {_fmt(p)} | {hubs} |")
    else:
        out.append("_Nothing queued._")
    ctx = []
    if proj["hubs"]:
        ctx.append("Collections: " + ", ".join(_page(pages, h) for h in proj["hubs"]))
    if proj["themes"]:
        ctx.append("Topics: " + ", ".join(_page(pages, t) for t in proj["themes"]))
    out += ["", "### Context", "", " · ".join(ctx) if ctx else "_No hubs or themes._"]
    return "\n".join(out) + "\n"


def replace_members(text, rendered):
    """Rewrite only the `## Members` section; `## Why` and everything else stay verbatim."""
    body = rendered.strip("\n")
    if MEMBERS_HEADING not in text:
        return text.rstrip("\n") + f"\n\n{MEMBERS_HEADING}\n\n{body}\n"
    head, rest = text.split(MEMBERS_HEADING, 1)
    lines = rest.split("\n")
    tail = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), None)
    after = "\n".join(lines[tail:]).rstrip("\n") if tail is not None else ""
    return f"{head}{MEMBERS_HEADING}\n\n{body}\n" + (f"\n{after}\n" if after else "")


def set_why(text, why):
    """Replace the hand-owned `## Why` body (append the section if missing)."""
    if WHY_HEADING not in text:
        return text.rstrip("\n") + f"\n\n{WHY_HEADING}\n\n{why.strip()}\n"
    head, rest = text.split(WHY_HEADING, 1)
    lines = rest.split("\n")
    tail = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), None)
    after = "\n".join(lines[tail:]) if tail is not None else ""
    return f"{head}{WHY_HEADING}\n\n{why.strip()}\n" + (f"\n{after}" if after else "")


def new_page(title, why, template_text):
    """Fresh scope page from meta/templates/scope.md with the given title and Why."""
    return set_why(frontmatter.fill_title(template_text.replace("{{title}}", title)), why)

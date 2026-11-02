"""Scopes API for the dashboard (schema 0.13): list / get / resolve (read-only) and save / delete /
duplicate (one kb(refine) knowledge step each, through src/kb_distillery/ops/core.py).

Everything takes an explicit `root` (default: the checkout the dashboard serves) so tests can run
against a temp vault. Raises ScopeError(status, message) for the HTTP layer to relay.
"""
import datetime
import os
import re
import sys

from kb_distillery.paths import META_DEFAULTS_PATH, vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.git import commit_policy as cp
from kb_distillery.core import scopes as sc
from kb_distillery.lint.lint import parse_frontmatter, read_manifest, write_manifest
from kb_distillery.ops import core
from kb_distillery.core.schema import is_page_file

DEFAULT_ROOT = vault_root()
TEMPLATE = os.path.join("meta", "templates", "scope.md")
MAX_PATHS = 5000


class ScopeError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def load_pages(root):
    pages = dict()
    wiki = os.path.join(root, "wiki")
    for name in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not is_page_file(name) or "excalidraw" in name:
            continue
        with open(os.path.join(wiki, name), encoding="utf-8") as f:
            text = f.read()
        fm = parse_frontmatter(text)
        if fm:
            pages[name[:-3]] = (f"wiki/{name}", fm, text)
    return pages


def _row_dict(path, manifest, pages, index):
    r = manifest[path]
    disp = (r.get("disposition") or "queued").partition(":")[0]
    slug = (r.get("slug") or "").strip()
    if slug not in pages:
        citing = sorted(index["raw_to"].get(path, ()))
        slug = citing[0] if citing else ""
    fm = pages[slug][1] if slug else dict()
    m = re.match(r"^((?:18|19|20)\d{2})-", os.path.basename(path))
    parts = path.split("/")
    return dict(path=path, format=parts[1] if len(parts) > 2 else "", disposition=disp,
                slug=slug or None, page_type=fm.get("type"), digestion=fm.get("depth") or "",
                collection=sc.collections_of(r), year=int(m.group(1)) if m else None)


def _proj_public(proj):
    keys = ("hop0", "hop1", "covered", "uncovered", "coverage", "hubs", "themes")
    return dict((k, proj[k]) for k in keys)


def _mtime_iso(root, rel):
    try:
        ts = os.path.getmtime(os.path.join(root, rel))
        return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    except OSError:
        return None


def list_scopes(root=None):
    root = root or DEFAULT_ROOT
    pages, manifest = load_pages(root), read_manifest(root)
    index = sc.build_index(pages)
    out = []
    for slug in sorted(s for s, (_r, fm, _t) in pages.items() if fm.get("type") == "scope"):
        rel, fm, text = pages[slug]
        paths = sc.rows_of(slug, manifest)
        proj = sc.projection(paths, pages, manifest, index)
        out.append(dict(slug=slug, title=sc.title_of(text, slug), maturity=fm.get("maturity") or "active",
                        files=len(paths), digested=len(proj["covered"]), uncovered=len(proj["uncovered"]),
                        coverage=proj["coverage"], updated=_mtime_iso(root, rel)))
    return dict(scopes=out)


def get_scope(slug, root=None):
    root = root or DEFAULT_ROOT
    pages, manifest = load_pages(root), read_manifest(root)
    if slug not in pages or pages[slug][1].get("type") != "scope":
        return None
    index = sc.build_index(pages)
    rel, fm, text = pages[slug]
    paths = sc.rows_of(slug, manifest)
    proj = sc.projection(paths, pages, manifest, index)
    return dict(slug=slug, title=sc.title_of(text, slug), why=sc.why_text(text),
                maturity=fm.get("maturity") or "active",
                rows=[_row_dict(p, manifest, pages, index) for p in paths], projection=_proj_public(proj))


def resolve_nodes(nodes, root=None):
    root = root or DEFAULT_ROOT
    if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
        raise ScopeError(400, "nodes must be a list of ids")
    pages, manifest = load_pages(root), read_manifest(root)
    index = sc.build_index(pages)
    paths = sc.resolve(nodes, pages, manifest, index=index)
    return dict(paths=paths, rows=[_row_dict(p, manifest, pages, index) for p in paths])


# ---------------------------------------------------------------- writes

def normalize_slug(slug):
    slug = (slug or "").strip().lower()
    if not slug.startswith(sc.PREFIX):
        slug = sc.PREFIX + slug
    stem = slug[len(sc.PREFIX):]
    if not stem or not sc.SLUG_RE.match(stem) or len(stem) > 60:
        raise ScopeError(400, "scope slug must be kebab-case (letters, digits, hyphens), e.g. scope-my-set")
    return slug


def _validate_paths(paths, manifest):
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ScopeError(400, "paths must be a list of raw file paths")
    if len(paths) > MAX_PATHS:
        raise ScopeError(400, f"too many files (max {MAX_PATHS})")
    for p in paths:
        if not sc.is_member_path(p):
            raise ScopeError(400, f"{p}: not a raw file a scope may hold (raw/inbox/ and traversal are refused)")
        if p not in manifest:
            raise ScopeError(400, f"{p}: not in the corpus")
        if sc.is_companion(manifest[p]):
            raise ScopeError(400, f"{p}: asset/ink/dupe/sidecar rows ride with their parent file")
    return sorted(set(paths))


def _template(root):
    """meta/templates/scope.md from the vault, else the explorer's src/kb_distillery/kits/base/defaults/templates/scope.md."""
    own = _read(root, TEMPLATE)
    return own if own is not None else _read(META_DEFAULTS_PATH, TEMPLATE.split("/", 1)[1])


def _read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _write(root, rel, text):
    full = os.path.join(root, rel)
    if text is None:
        if os.path.exists(full):
            os.remove(full)
        return
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


def _check_session(root):
    s = core.current_session(root)
    if s:
        raise ScopeError(409, "an ops session is open (" + s["op"] + " " + s["target"] + ") — finish it first")


def _step(root, slug, summary, rel, before, lint, push):
    """The single kb(refine) step; on any failure the files go back as they were."""
    try:
        sha = core.commit_op("refine", slug, summary, paths=["meta/corpus.tsv", rel], lint=lint,
                             root=root, push=push)
    except Exception as e:  # noqa: BLE001
        for r, text in before.items():
            _write(root, r, text)
        raise ScopeError(500, "knowledge step failed: " + str(e)) from e
    v = cp.last_version(root)
    return dict(ok=True, sha=sha, slug=slug, version=("kb-" + cp.fmt_version(v)) if v else None)


def _apply(root, slug, title, why, paths, create, manifest, pages, template):
    """Mutate corpus cells and write the page text; returns (rel, before-snapshot)."""
    rel = f"wiki/{slug}.md"
    from kb_distillery.core import links
    titles = {s: links.title_of(p[2], s) for s, p in pages.items()}
    why = links.to_disk(why, titles)               # a typed [[wikilink]] is stored as [Title](slug.md)
    before = dict((r, _read(root, r)) for r in ("meta/corpus.tsv", rel))
    sc.write_scope_rows(manifest, slug, paths)
    write_manifest(manifest, root)
    if create:
        text = sc.new_page(title, why, template)
    else:
        text = sc.set_why(before[rel], why)
        if title:
            text = re.sub(r"^# .+$", lambda m: "# " + title, text, count=1, flags=re.M)
    pages = dict(pages)
    pages[slug] = (rel, parse_frontmatter(text), text)
    proj = sc.projection(paths, pages, manifest, sc.build_index(pages))
    _write(root, rel, sc.replace_members(text, sc.render_members(slug, proj, pages)))
    return rel, before


def save_scope(payload, root=None, lint=True, push=True):
    root = root or DEFAULT_ROOT
    slug = normalize_slug(payload.get("slug"))
    why = (payload.get("why") or "").strip()
    if not why:
        raise ScopeError(400, "a scope needs a Why — one paragraph on what this working set is for")
    create = bool(payload.get("create"))
    _check_session(root)
    pages, manifest = load_pages(root), read_manifest(root)
    exists = slug in pages
    if create and exists:
        raise ScopeError(409, slug + " already exists")
    if not create and not (exists and pages[slug][1].get("type") == "scope"):
        raise ScopeError(404, slug + " does not exist (pass create: true)")
    paths = _validate_paths(payload.get("paths", []), manifest)
    title = (payload.get("title") or "").strip().replace("\n", " ")
    if create and not title:
        title = slug[len(sc.PREFIX):].replace("-", " ").capitalize()
    template = _template(root)
    if create and template is None:
        raise ScopeError(500, "meta/templates/scope.md is missing")
    rel, before = _apply(root, slug, title, why, paths, create, manifest, pages, template)
    verb = "create" if create else "update"
    return _step(root, slug, f"{verb} scope {slug} ({len(paths)} files)", rel, before, lint, push)


def delete_scope(payload, root=None, lint=True, push=True):
    root = root or DEFAULT_ROOT
    slug = normalize_slug(payload.get("slug"))
    _check_session(root)
    pages, manifest = load_pages(root), read_manifest(root)
    if slug not in pages or pages[slug][1].get("type") != "scope":
        raise ScopeError(404, slug + " does not exist")
    rel = f"wiki/{slug}.md"
    before = dict((r, _read(root, r)) for r in ("meta/corpus.tsv", rel))
    sc.delete_scope(manifest, slug)
    write_manifest(manifest, root)
    _write(root, rel, None)
    return _step(root, slug, "delete scope " + slug, rel, before, lint, push)


def duplicate_scope(payload, root=None, lint=True, push=True):
    root = root or DEFAULT_ROOT
    src = normalize_slug(payload.get("slug"))
    dst = normalize_slug(payload.get("new_slug"))
    _check_session(root)
    pages, manifest = load_pages(root), read_manifest(root)
    if src not in pages or pages[src][1].get("type") != "scope":
        raise ScopeError(404, src + " does not exist")
    if dst in pages:
        raise ScopeError(409, dst + " already exists")
    title = (payload.get("title") or "").strip() or sc.title_of(pages[src][2], src) + " (copy)"
    paths = sc.rows_of(src, manifest)
    template = _template(root)
    if template is None:
        raise ScopeError(500, "meta/templates/scope.md is missing")
    rel, before = _apply(root, dst, title, sc.why_text(pages[src][2]), paths, True, manifest, pages, template)
    return _step(root, dst, f"duplicate scope {src} as {dst}", rel, before, lint, push)

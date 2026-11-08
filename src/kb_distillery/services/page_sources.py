"""The sources behind one wiki page (0 LLM, read-only): the raw files named by its `raw:` field, the pages and
URLs named by its `sources:` field, and the corpus rows that cite it, each with title, format, disposition and
the sections of the page that mention it. Built from `meta/corpus.tsv`, the page frontmatter and `raw_card.kind_of`."""
import os
import re
from collections import Counter

from kb_distillery.config import paths
from kb_distillery.graph.raw_layer import prettify, raw_format, split_disposition
from kb_distillery.lint.lint import raw_paths
from kb_distillery.search.semfind import load_pages
from kb_distillery.services.raw_card import kind_of
from kb_distillery.vault.links import page_slug
from kb_distillery.vault.pages import read_manifest

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _resources(fm):
    """Raw `resource` strings of the `sources:` field (objects with a `resource`, or bare strings)."""
    v = fm.get("sources")
    if v in (None, ""):
        return []
    items = [v] if isinstance(v, (str, dict)) else list(v)
    out = []
    for it in items:
        res = it.get("resource") if isinstance(it, dict) else it
        if isinstance(res, str) and res.strip():
            out.append(res.strip())
    return out


def _title(text, slug):
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else slug.replace("-", " ")


def _body(text):
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            return parts[1].lstrip("\n")
    return text


def _sections(body, needles):
    """Headings of the sections of `body` whose text contains any of `needles`, in page order."""
    heading, hits, in_code = "", [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING.match(line)
        if m:
            heading = m.group(2)
            continue
        if heading and heading not in hits and any(n and n in line for n in needles):
            hits.append(heading)
    return hits


def _added(fm):
    for k in ("added", "created", "date"):
        v = fm.get(k)
        if v:
            return str(v)[:10]
    return None


def build_sources(slug, view=None):
    """{slug, sources, counts} of page `slug` in the active knowledge base (or of `view`), or None when unknown."""
    root = view.root if view else None
    pages = load_pages(root)
    if slug not in pages:
        return None
    _rel, fm, text = pages[slug]
    manifest = read_manifest(root or paths.ROOT)
    body = _body(text)
    items: dict[str, dict] = {}

    def row_of(path):
        return manifest.get(path)

    def add_raw(path, via, page_slug_=None):
        key = path
        row = row_of(path)
        disp, _comp = split_disposition((row or {}).get("disposition")) if row else (None, None)
        fmt = raw_format(path, row)
        owner = page_slug_ if page_slug_ in pages else ((row or {}).get("slug") or "")
        owner = owner if owner in pages else None
        ofm = pages[owner][1] if owner else fm
        title = _title(pages[owner][2], owner) if owner else prettify(path)
        url = str(ofm.get("url") or ofm.get("source") or "")
        it = items.setdefault(key, {
            "id": key, "title": title, "kind": kind_of(fmt, os.path.splitext(path)[1].lower(), url), "format": fmt,
            "disposition": disp or "unlisted", "path_rel": path, "slug": owner, "url": None,
            "route": None, "via": [], "cited_in_sections": [], "added": _added(ofm)})
        it["route"] = f"/pipeline?q={path}"
        if via not in it["via"]:
            it["via"].append(via)
        needles = [path, os.path.basename(path)] + ([f"{owner}.md", f"[[{owner}]]"] if owner else [])
        it["cited_in_sections"] = _sections(body, needles)

    for p in raw_paths(fm):
        add_raw(p, "raw")
    for res in _resources(fm):
        ps = page_slug(res)
        if ps and ps in pages and ps != slug:
            sfm = pages[ps][1]
            sub_paths = raw_paths(sfm)
            if sub_paths:
                for p in sub_paths:
                    add_raw(p, "sources", ps)
                continue
            items.setdefault(ps, {
                "id": ps, "title": _title(pages[ps][2], ps), "kind": str(sfm.get("type") or "page"), "format": "page",
                "disposition": "page", "path_rel": None, "slug": ps, "url": None, "route": f"/pages/{ps}",
                "via": ["sources"], "cited_in_sections": _sections(body, [f"{ps}.md", f"[[{ps}]]"]),
                "added": _added(sfm)})
        elif re.match(r"https?://", res, re.I):
            url = res
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            kind = kind_of("web-clips", "", url)
            items.setdefault(url, {
                "id": url, "title": host + (url.split(host, 1)[1].rstrip("/") if host in url else ""), "kind": kind,
                "format": "web-clips", "disposition": "external", "path_rel": None, "slug": None, "url": url,
                "route": None, "via": ["sources"], "cited_in_sections": _sections(body, [url]), "added": None})
    for path, row in manifest.items():
        if (row.get("slug") or "").strip() == slug and row.get("disposition") != "sidecar" and path not in items:
            add_raw(path, "corpus", slug)

    out = list(items.values())
    counts = {"total": len(out), "raw": sum(1 for i in out if i["path_rel"]),
              "pages": sum(1 for i in out if i["format"] == "page"),
              "external": sum(1 for i in out if i["disposition"] == "external"),
              "by_disposition": dict(Counter(i["disposition"] for i in out))}
    return {"slug": slug, "sources": out, "counts": counts}

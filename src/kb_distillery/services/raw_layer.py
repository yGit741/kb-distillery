"""The raw-data layer of the graph (0 LLM): one node per corpus row, bundled into one pile per format.

Read-only view over meta/corpus.tsv + the wiki pages' `raw:` lists + hub Contents tables. Nothing
here is written back to the vault, and nothing here may reach the public share build.
"""
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.core.hubs import parse_contents
from kb_distillery.lint.lint import collections_of, raw_paths, read_manifest

ROOT = vault_root()
FORMATS = ("printed-docs", "handwritten", "presentations", "llm-chats", "emails", "web-clips", "images", "videos", "inbox")
COMPANIONS = ("asset", "ink", "dupe")
from kb_distillery.core.schema import COLLECTION_TYPES
_YEAR = re.compile(r"^((?:18|19|20)\d{2})-")
_PAGE_STATUS = ("source", "partial", "queued", "skip")


def split_disposition(disp):
    """'asset:raw/x.md' -> ('asset', 'raw/x.md'); 'source' -> ('source', None)."""
    head, _, rest = (disp or "").partition(":")
    return (head, rest) if head in COMPANIONS else (disp or "queued", None)


def raw_format(path, row=None):
    parts = path.split("/")
    folder = parts[1] if len(parts) > 2 else ""
    if folder in FORMATS:
        return folder
    return (row or {}).get("kind") or folder or "unknown"


def prettify(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^(?:18|19|20)\d{2}-", "", stem)
    return stem.replace("-", " ").replace("_", " ").strip() or stem


def year_of(path):
    m = _YEAR.match(os.path.basename(path))
    return int(m.group(1)) if m else None


def corpus_stat():
    p = os.path.join(ROOT, "meta", "corpus.tsv")
    try:
        st = os.stat(p)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "none"


def page_sources(pages):
    """raw path -> set of wiki slugs citing it via `raw:`."""
    out = defaultdict(set)
    for slug, (_rel, fm, _text) in pages.items():
        for p in raw_paths(fm):
            out[p].add(slug)
    return out


def _title_of(text, slug):
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else slug.replace("-", " ")


def _new_pile(fmt):
    return {"format": fmt, "count": 0, "source": 0, "partial": 0, "queued": 0, "skip": 0,
            "companions": 0, "pages_fed": 0, "links_to_pages": Counter()}


def build_raw_layer(pages):
    """{raw_nodes, raw_links, piles, pile_links} for build_graph_snapshot(layer='raw')."""
    rows = {p: r for p, r in read_manifest().items() if r.get("disposition") != "sidecar"}
    cites = page_sources(pages)
    fmt_of = {p: raw_format(p, r) for p, r in rows.items()}

    nodes, links = [], []
    seen_links = set()

    def add_link(src, tgt, kind):
        key = (src, tgt, kind)
        if key not in seen_links:
            seen_links.add(key)
            links.append({"source": src, "target": tgt, "kind": kind})

    for path, row in sorted(rows.items()):
        disp, companion_of = split_disposition(row.get("disposition"))
        row_slug = (row.get("slug") or "").strip()
        citing = sorted(cites.get(path, ()))
        slug = row_slug if row_slug in pages else (citing[0] if citing else "")
        collection = collections_of(row)
        nid = f"raw:{path}"
        nodes.append({
            "id": nid, "path": path, "format": fmt_of[path],
            "ext": os.path.splitext(path)[1].lstrip(".").lower(),
            "disposition": disp, "companion_of": companion_of, "collection": collection,
            "slug": slug or None, "year": year_of(path), "sha1": (row.get("sha1") or "")[:10],
            "title": _title_of(pages[slug][2], slug) if slug else prettify(path),
        })
        for s in ([row_slug] if row_slug in pages else []) + citing:
            add_link(nid, s, "source")
        if companion_of:
            add_link(nid, f"raw:{companion_of}", disp)
        for c in collection:
            if c in pages:
                add_link(nid, c, "member")

    piles = {f: _new_pile(f) for f in FORMATS}
    for n in nodes:
        pile = piles.setdefault(n["format"], _new_pile(n["format"]))
        pile["count"] += 1
        d = n["disposition"]
        if d in COMPANIONS:
            pile["companions"] += 1
        elif d in _PAGE_STATUS:
            pile[d] += 1
        else:
            pile["queued"] += 1
    fed = defaultdict(set)
    for l in links:
        if l["kind"] == "source":
            f = fmt_of[l["source"][4:]]
            fed[f].add(l["target"])
            piles[f]["links_to_pages"][l["target"]] += 1
    out_piles = []
    for f, p in piles.items():
        p["pages_fed"] = len(fed[f])
        p["links_to_pages"] = dict(p["links_to_pages"].most_common())
        out_piles.append(p)

    agg = Counter()
    for n in nodes:
        if n["companion_of"] and n["companion_of"] in rows:
            a, b = n["format"], fmt_of[n["companion_of"]]
            if a != b:
                agg[(a, b, n["disposition"])] += 1

    def pairs(paths, kind):
        fs = sorted({fmt_of[p] for p in paths if p in fmt_of})
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                agg[(a, b, kind)] += 1

    for _slug, (_rel, fm, text) in pages.items():
        if fm.get("type") in COLLECTION_TYPES:
            try:
                for r in parse_contents(text):
                    pairs(r["raws"], "hub")
            except Exception:  # noqa: BLE001 — a malformed hub must not break the graph
                pass
        pairs(raw_paths(fm), "page")
    pile_links = [{"source": a, "target": b, "kind": k, "count": c} for (a, b, k), c in sorted(agg.items())]

    return {"raw_nodes": nodes, "raw_links": links, "piles": out_piles, "pile_links": pile_links}


def layer_etag(base_etag):
    return hashlib.sha1(f"{base_etag}|raw|{corpus_stat()}".encode()).hexdigest()[:16]

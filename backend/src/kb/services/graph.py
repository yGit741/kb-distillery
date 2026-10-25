"""Build wiki link graph for the interactive explorer (0 LLM)."""
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb.core.books import DIGESTED, coverage, parse_partition
from kb.core.graph import inbound_index, outbound_links
from kb.search.semfind import load_pages
from kb.core.schema import LAYER_OF

ROOT = vault_root()
TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
YEAR_PREFIX = re.compile(r"^(1[89]|20)\d{2}-")
WIKILINK = re.compile(r"\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]")
FM_SKIP = frozenset({"type", "layer", "status", "area", "year", "role", "affiliation", "lab", "email",
                   "url", "raw", "related", "depth", "citekey", "authors",
                   "recommended_by", "discussed_with", "scholar", "tau_profile", "optional",
                   "book", "section", "section_pages", "book_pages"})
FM_ORDER = ("type", "status", "area", "year", "role", "affiliation", "lab", "email",
            "url", "raw", "related", "citekey", "authors")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _title(text, slug):
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    m = TITLE.search(body)
    if m:
        return m.group(1).strip()
    return slug.replace("-", " ")


def _preview(text, max_len=480):
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    paras = []
    past_title = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            past_title = True
            continue
        if not past_title:
            continue
        if s.startswith("## "):
            if paras:
                break
            continue
        if not s or s.startswith(("!", "|", "- ", ">", "<!--")):
            continue
        paras.append(s)
    blob = " ".join(paras[:4])
    blob = WIKILINK.sub(lambda m: m.group(2) or m.group(1), blob)
    blob = re.sub(r"`([^`]+)`", r"\1", blob)
    blob = re.sub(r"\$[^$]+\$", "", blob)
    blob = re.sub(r"\*\*([^*]+)\*\*", r"\1", blob)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:max_len]


def _properties(fm, slug, in_degree, out_degree):
    props = {}
    for k in FM_ORDER:
        if k not in fm or not fm[k]:
            continue
        v = fm[k]
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        props[k] = str(v).strip()
    for k, v in sorted(fm.items()):
        if k in props or k in FM_SKIP or not v:
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        props[k] = str(v).strip()
    props["links_in"] = str(in_degree)
    props["links_out"] = str(out_degree)
    props["slug"] = slug
    return props


def _year(slug, fm):
    y = fm.get("year")
    if y:
        try:
            return int(str(y).strip())
        except ValueError:
            pass
    m = YEAR_PREFIX.match(slug)
    if m:
        try:
            return int(slug[:4])
        except ValueError:
            pass
    return None


def _areas(fm):
    area = fm.get("area")
    if not area:
        return []
    if isinstance(area, str):
        area = [area]
    return [a.strip() for a in area if a and str(a).strip()]


def _book_info(fm, text):
    """Partition summary for a book hub node: coverage + rows (digested ones link a part)."""
    rows = [r for r in parse_partition(text) if r["start"] is not None]
    done, content = coverage(rows)
    total = str(fm.get("book_pages") or "").strip()
    return {
        "done": done,
        "content": content,
        "total": int(total) if total.isdigit() else 0,
        "parts": [{"title": r["title"], "start": r["start"], "end": r["end"],
                   "status": r["status"], "slug": r["slug"] if r["status"] in DIGESTED else ""}
                  for r in sorted(rows, key=lambda r: r["start"])],
    }


def _part_info(fm):
    return {"book": str(fm.get("book") or ""), "pages": str(fm.get("section_pages") or ""),
            "section": str(fm.get("section") or "")}


def _etag(pages):
    parts = []
    for slug in sorted(pages):
        rel = pages[slug][0]
        path = os.path.join(ROOT, rel)
        st = os.stat(path)
        parts.append(f"{slug}:{st.st_mtime_ns}:{st.st_size}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


DATES_ENV = "KB_GRAPH_DATES"   # a JSON file of {path: [added, changed]}: the share build's dates for its export


def _git_dates(root=ROOT, rev="HEAD"):
    """{wiki path: (added, changed)} as YYYY-MM-DD from one `git log` pass (newest first); {} without git."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", root, "log", rev, "--format=@%cs", "--name-only", "--no-renames", "--", "wiki"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    dates, day = {}, ""
    for line in out.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line:
            added, changed = dates.get(line, (day, day))
            dates[line] = (day, changed)   # older commits come later: the last seen is when it was added
    return dates


def build_graph_snapshot(layer=None):
    pages = load_pages()
    inbound = inbound_index(pages)
    dates = _git_dates()
    if not dates and os.environ.get(DATES_ENV):   # a share build's export has no history: its dates come in a file
        import json

        with open(os.environ[DATES_ENV], encoding="utf-8") as f:
            dates = {k: tuple(v) for k, v in json.load(f).items()}
    nodes = []
    links = []
    link_keys = set()
    types = set()
    statuses = set()
    areas = set()

    for slug, (rel, fm, text) in pages.items():
        ntype = fm.get("type", "unknown")
        status = fm.get("status", "")
        node_areas = _areas(fm)
        types.add(ntype)
        if status:
            statuses.add(status)
        for a in node_areas:
            areas.add(a)
        extra = {}
        if ntype == "book":
            extra["book"] = _book_info(fm, text)
        elif ntype == "part":
            extra["part"] = _part_info(fm)
        nodes.append(
            {
                **extra,
                "id": slug,
                "label": slug,
                "title": _title(text, slug),
                "type": ntype,
                "layer": fm.get("layer") or LAYER_OF.get(ntype, ""),
                "status": status,
                "depth": fm.get("depth", ""),
                "areas": node_areas,
                "year": _year(slug, fm),
                "inDegree": len(inbound.get(slug, set())),
                "outDegree": len(outbound_links(text, fm) & set(pages)),
                "path": rel,
                # when the page came into the vault and last changed (git); "" without history, never a guess
                "added": dates.get(rel, ("", ""))[0],
                "changed": dates.get(rel, ("", ""))[1],
                "preview": _preview(text),
                "properties": _properties(
                    fm, slug, len(inbound.get(slug, set())),
                    len(outbound_links(text, fm) & set(pages)),
                ),
            }
        )

    for slug, (rel, fm, text) in pages.items():
        outbound = outbound_links(text, fm)
        for target in sorted(outbound):
            if target not in pages:
                continue
            key = (slug, target)
            if key in link_keys:
                continue
            link_keys.add(key)
            kind = "related" if target in _related_set(fm) and target not in _wikilink_set(text) else "wikilink"
            links.append({"source": slug, "target": target, "kind": kind})
        book = str(fm.get("book") or "") if fm.get("type") == "part" else ""
        if book in pages and (slug, book) not in link_keys:      # a part always hangs off its book
            link_keys.add((slug, book))
            links.append({"source": slug, "target": book, "kind": "book"})

    snap = {
        "generated_at": _now(),
        "etag": _etag(pages),
        "node_count": len(nodes),
        "link_count": len(links),
        "nodes": nodes,
        "links": links,
        "schema": _schema(),
        "concept_links": concept_links(nodes, links),
        "facets": {
            "types": sorted(types),
            "statuses": sorted(statuses),
            "areas": sorted(areas),
        },
    }
    if layer == "raw":      # private data layer; the share build never passes a layer
        from kb.services import raw_layer
        snap.update(raw_layer.build_raw_layer(pages))
        snap["etag"] = raw_layer.layer_etag(snap["etag"])
        snap["layer"] = "raw"
    return snap


def _schema():
    from kb.services.schema import schema_payload
    return schema_payload()


def concept_links(nodes, links):
    """Concept pairs that share sources: [{source, target, shared}] — drawn as thin edges labelled
    with the count when the source layer is hidden. A source is shared when it links to (or is
    linked from) both concepts."""
    layer = {n["id"]: n.get("layer") for n in nodes}
    touching = {}
    for l in links:
        a, b = l["source"], l["target"]
        for src, other in ((a, b), (b, a)):
            if layer.get(src) == "source" and layer.get(other) == "concept":
                touching.setdefault(src, set()).add(other)
    shared = {}
    for concepts in touching.values():
        cs = sorted(concepts)
        for i, x in enumerate(cs):
            for y in cs[i + 1:]:
                shared[(x, y)] = shared.get((x, y), 0) + 1
    return [{"source": x, "target": y, "shared": n} for (x, y), n in sorted(shared.items())]


def _wikilink_set(text):
    from kb.lint.lint import LINK

    return {m.strip() for m in LINK.findall(text or "")}


def _related_set(fm):
    related = fm.get("related")
    if not related:
        return set()
    if isinstance(related, str):
        related = [related]
    return {r.strip() for r in related if r}

"""Build wiki link graph for the interactive explorer (0 LLM)."""
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.core.books import DIGESTED, coverage, parse_partition
from kb_distillery.core.graph import inbound_index, outbound_links
from kb_distillery.search.semfind import load_pages
from kb_distillery.core import frontmatter
from kb_distillery.core import links as page_links
from kb_distillery.core.schema import LAYER_OF

ROOT = vault_root()
TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
YEAR_PREFIX = re.compile(r"^(1[89]|20)\d{2}-")
FM_SKIP = frozenset({"type", "layer", "maturity", "status", "title", "generated", "area", "year", "role", "affiliation", "lab", "email",
                   "url", "raw", "related", "depth", "citekey", "authors",
                   "recommended_by", "discussed_with", "scholar", "tau_profile", "optional",
                   "book", "section", "section_pages", "book_pages"})
FM_ORDER = ("type", "maturity", "area", "year", "role", "affiliation", "lab", "email",
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
    blob = re.sub(r"<!--.*?-->", "", " ".join(paras[:4]))
    blob = page_links.plain(blob)
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
        v = frontmatter.display(k, fm[k])
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        props[k] = str(v).strip()
    for k, v in sorted(fm.items()):
        if k in props or k in FM_SKIP or not v:
            continue
        v = frontmatter.display(k, v)
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


def _etag(pages, root=ROOT):
    parts = []
    for slug in sorted(pages):
        rel = pages[slug][0]
        path = os.path.join(root, rel)
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


_DATES_CACHE = {}    # root → (HEAD sha, dates): another kb's history is read once per commit


def _dates_for(root):
    from kb_distillery.services.kbview import head
    sha = head(root)
    hit = _DATES_CACHE.get(root)
    if sha and hit and hit[0] == sha:
        return hit[1]
    dates = _git_dates(root)
    if sha:
        _DATES_CACHE[root] = (sha, dates)
    return dates


def build_graph_snapshot(layer=None, view=None):
    """The link graph of the active knowledge base, or of `view` (a `kbview.KbView`, read-only).
    Every node carries its `kb` and `slug`; `id` is the slug here (`merge_snapshots` namespaces it)."""
    root = view.root if view else ROOT
    layer_of = view.types.layer_of if view else LAYER_OF
    kb_id = view.id if view else _active_id()
    pages = load_pages(root)
    inbound = inbound_index(pages)
    dates = _git_dates() if view is None or view.active else _dates_for(root)
    if not dates and os.environ.get(DATES_ENV):   # a share build's export has no history: its dates come in a file
        import json

        with open(os.environ[DATES_ENV], encoding="utf-8") as f:
            dates = {k: tuple(v) for k, v in json.load(f).items()}
    nodes = []
    links = []
    link_keys = set()
    types = set()
    maturities = set()
    areas = set()

    for slug, (rel, fm, text) in pages.items():
        ntype = fm.get("type", "unknown")
        maturity = fm.get("maturity", "")
        node_areas = _areas(fm)
        types.add(ntype)
        if maturity:
            maturities.add(maturity)
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
                "kb": kb_id,
                "slug": slug,
                "label": slug,
                "title": _title(text, slug),
                "type": ntype,
                "layer": fm.get("layer") or layer_of.get(ntype, ""),
                "maturity": maturity,
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
        "etag": _etag(pages, root),
        "node_count": len(nodes),
        "link_count": len(links),
        "nodes": nodes,
        "links": links,
        "schema": _schema(view.types if view else None),
        "concept_links": concept_links(nodes, links),
        "facets": {
            "types": sorted(types),
            "maturities": sorted(maturities),
            "areas": sorted(areas),
        },
    }
    if relations_on():      # typed relations, a separate list: `links` (what the canvas draws) stays as it was
        snap["relations"] = _relations(pages, nodes, links, snap["concept_links"], root, view)
        snap["etag"] = _relations_etag(snap["etag"], root)
    if layer == "raw":      # private data layer; the share build never passes a layer
        from kb_distillery.services import raw_layer
        snap.update(raw_layer.build_raw_layer(pages))
        snap["etag"] = raw_layer.layer_etag(snap["etag"])
        snap["layer"] = "raw"
    return snap


RELATIONS_FLAG = "graph-relations"


def relations_on():
    from kb_distillery.services.pages import _flag_on
    return _flag_on(RELATIONS_FLAG)


def _relations_etag(etag, root):
    """The page etag plus what relations read besides pages (kb.toml [edges], aliases, card vectors), so a
    snapshot with relations never shares an etag with one without, nor with one built from older inputs."""
    parts = [etag, "relations"]
    for rel in ("kb.toml", os.path.join("meta", "aliases.tsv"), os.path.join(".cache", "vectors.sqlite")):
        try:
            st = os.stat(os.path.join(root, rel))
            parts.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{rel}:-")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _relations(pages, nodes, links, concept, root, view=None):
    """kb_distillery.graph.relations for this knowledge base, with its own `[edges]` table (another kb's for a view)."""
    from kb_distillery import kbconfig
    from kb_distillery.graph import relations
    from kb_distillery.services.cypher import edge_config

    cfg = None
    if view is not None and not view.active:
        try:
            cfg = kbconfig.load_dir(view.root, view.id, strict=False)
        except kbconfig.KbConfigError:
            cfg = None
        config = edge_config(cfg) if cfg else {"types": [], "note_required": set()}
    else:
        config = edge_config()
    return relations.build(pages, nodes, links, concept, config, root)


def _schema(types=None):
    from kb_distillery.services.schema import schema_payload
    return schema_payload(types)


def _active_id():
    from kb_distillery import paths
    return paths.KB.id if paths.KB else ""


def merge_snapshots(snaps):
    """One canvas from several knowledge bases' snapshots [(view, snap)]: ids become `<kb>:<slug>` so equal
    slugs never collide, links are rewritten the same way, and the schema is the union of the types. A type
    id two knowledge bases both declare is shared only when they agree on its layer; otherwise the later kb's
    nodes get the type `<kb>:<type>` so one colour never means two things."""
    nodes, links, concept, kbs, visible = [], [], [], [], set()
    relations = None
    types, type_rows, facets = {}, [], {"types": set(), "maturities": set(), "areas": set()}
    layer_types = {}
    etags = []
    for view, snap in snaps:
        kbs.append({"id": view.id, "name": view.name, "active": view.active})
        etags.append(snap["etag"])
        rename = {}
        for t in snap["schema"].get("types", []):
            prev = types.get(t["id"])
            if prev is None:
                types[t["id"]] = t
                type_rows.append(t)
            elif prev["layer"] != t["layer"]:
                new_id = f"{view.id}:{t['id']}"
                rename[t["id"]] = new_id
                row = {**t, "id": new_id, "label": f"{t['label']} ({view.name})"}
                types[new_id] = row
                type_rows.append(row)
        for l in snap["schema"].get("layers", []):
            bucket = layer_types.setdefault(l["id"], {**l, "types": []})
            for t in l["types"]:
                tid = rename.get(t, t)
                if tid not in bucket["types"]:
                    bucket["types"].append(tid)
        visible.update(rename.get(t, t) for t in snap["schema"].get("default_visible", []))
        ns = lambda s, v=view.id: f"{v}:{s}"
        for n in snap["nodes"]:
            ntype = rename.get(n["type"], n["type"])
            extra = {}
            if "book" in n:             # a book's partition rows link its parts by slug
                extra["book"] = {**n["book"], "parts": [{**p, "slug": ns(p["slug"]) if p["slug"] else ""}
                                                       for p in n["book"]["parts"]]}
            if "part" in n and n["part"].get("book"):
                extra["part"] = {**n["part"], "book": ns(n["part"]["book"])}
            nodes.append({**n, **extra, "id": ns(n["id"]), "type": ntype})
            facets["types"].add(ntype)
        for l in snap["links"]:
            links.append({**l, "source": ns(l["source"]), "target": ns(l["target"])})
        for c in snap.get("concept_links", []):
            concept.append({**c, "source": ns(c["source"]), "target": ns(c["target"])})
        if snap.get("relations") is not None:
            relations = (relations or []) + [{**r, "source": ns(r["source"]), "target": ns(r["target"])}
                                             for r in snap["relations"]]
        facets["maturities"].update(snap["facets"]["maturities"])
        facets["areas"].update(snap["facets"]["areas"])
    first = snaps[0][1]["schema"] if snaps else {}
    schema_ = {**first, "layers": list(layer_types.values()), "types": type_rows,
               "default_visible": sorted(visible)}
    for key in ("source", "collection", "concept"):
        schema_[f"{key}_types"] = sorted(t["id"] for t in type_rows if t["layer"] == key)
    out = {
        "generated_at": _now(),
        "etag": hashlib.sha1("|".join(etags).encode()).hexdigest()[:16],
        "node_count": len(nodes),
        "link_count": len(links),
        "nodes": nodes,
        "links": links,
        "schema": schema_,
        "concept_links": concept,
        "facets": {k: sorted(v) for k, v in facets.items()},
        "kbs": kbs,
    }
    if relations is not None:
        out["relations"] = relations
    return out


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
    return set(page_links.targets(text))


def _related_set(fm):
    return set(page_links.refs(fm.get("related")))

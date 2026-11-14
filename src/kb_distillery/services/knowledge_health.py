"""Knowledge health: anomaly groups over the wiki link graph, computed per request and never stored.

Pure functions over a graph snapshot (`{"nodes": [...], "links": [...]}`, the shape of `/api/graph`); no I/O, no LLM.
Links are treated as undirected for degree and support; a page's *sources* are its distinct neighbours in the
`source` layer.

Groups:
- `undigested_sources`: source pages still at `depth: listed` (cataloged stub, not read yet; page-model doc).
- `orphans`: pages with no links in or out.
- `single_source_concepts`: concept pages with exactly one distinct linked source page.
- `missing_links`: concept pairs with no direct link whose source sets overlap in at least `MIN_SHARED` sources and
  whose Jaccard similarity is at least `min_jaccard`; best score first.
- `unsupported_links`: concept-to-concept links whose two ends share no source.
- `hubs`: pages whose degree is above mean + 3 standard deviations of all degrees and at least `HUB_MIN_DEGREE`.
Each group is `{"count": full count, "items": first `limit`}`.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from statistics import mean, pstdev

MIN_SHARED = 2
HUB_MIN_DEGREE = 10
HUB_SIGMAS = 3.0
DEFAULT_MIN_JACCARD = 0.34
DEFAULT_LIMIT = 50


def _adjacency(nodes: list[dict], links: list[dict]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for lk in links:
        a, b = lk.get("source"), lk.get("target")
        if a in adj and b in adj and a != b:
            adj[a].add(b)
            adj[b].add(a)
    return adj


def _page(n: dict, degree: int) -> dict:
    return {"id": n["id"], "title": n.get("title") or n.get("label") or n["id"],
            "layer": n.get("layer", ""), "type": n.get("type", ""), "degree": degree}


def _group(items: list, limit: int) -> dict:
    return {"count": len(items), "items": items[:max(limit, 0)]}


def compute(snapshot: dict, min_jaccard: float = DEFAULT_MIN_JACCARD, limit: int = DEFAULT_LIMIT) -> dict:
    nodes = snapshot.get("nodes", [])
    by_id = {n["id"]: n for n in nodes}
    adj = _adjacency(nodes, snapshot.get("links", []))
    layer = {i: n.get("layer", "") for i, n in by_id.items()}
    concepts = sorted(i for i, ly in layer.items() if ly == "concept")
    sources_of = {c: {s for s in adj[c] if layer[s] == "source"} for c in concepts}

    undigested = [{**_page(n, len(adj[n["id"]])), "depth": n.get("depth", "")}
                  for n in nodes if n.get("layer") == "source" and n.get("depth") == "listed"]
    orphans = [_page(n, 0) for n in nodes if not adj[n["id"]]]
    single = [{**_page(by_id[c], len(adj[c])), "source": next(iter(s))}
              for c, s in sources_of.items() if len(s) == 1]

    by_source: dict[str, list[str]] = defaultdict(list)
    for c, srcs in sources_of.items():
        for s in srcs:
            by_source[s].append(c)
    candidates: set[tuple[str, str]] = set()
    for cs in by_source.values():
        candidates.update(combinations(sorted(cs), 2))
    missing = []
    for a, b in candidates:
        if b in adj[a]:
            continue
        shared = sources_of[a] & sources_of[b]
        if len(shared) < MIN_SHARED:
            continue
        score = len(shared) / len(sources_of[a] | sources_of[b])
        if score >= min_jaccard:
            missing.append({"a": a, "a_title": _page(by_id[a], 0)["title"], "b": b,
                            "b_title": _page(by_id[b], 0)["title"], "score": round(score, 4),
                            "shared": sorted(shared)})
    missing.sort(key=lambda m: (-m["score"], m["a"], m["b"]))

    unsupported = []
    for a in concepts:
        for b in sorted(adj[a]):
            if a < b and layer[b] == "concept" and not (sources_of[a] & sources_of[b]):
                unsupported.append({"a": a, "a_title": _page(by_id[a], 0)["title"], "b": b,
                                    "b_title": _page(by_id[b], 0)["title"]})

    degrees = [len(v) for v in adj.values()]
    hubs: list[dict] = []
    if degrees:
        cut = max(mean(degrees) + HUB_SIGMAS * pstdev(degrees), HUB_MIN_DEGREE - 1)
        hubs = sorted((_page(by_id[i], len(v)) for i, v in adj.items() if len(v) > cut),
                      key=lambda p: (-p["degree"], p["id"]))

    return {
        "undigested_sources": _group(undigested, limit),
        "orphans": _group(orphans, limit),
        "single_source_concepts": _group(single, limit),
        "missing_links": _group(missing, limit),
        "unsupported_links": _group(unsupported, limit),
        "hubs": _group(hubs, limit),
    }


def build(min_jaccard: float = DEFAULT_MIN_JACCARD, limit: int = DEFAULT_LIMIT) -> dict:
    from kb_distillery.graph.cache import cached_graph_snapshot
    return compute(cached_graph_snapshot(), min_jaccard, limit)

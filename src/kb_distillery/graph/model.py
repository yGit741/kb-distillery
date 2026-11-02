"""Read-only graph queries: a checked subset of Cypher (GrandCypher on NetworkX) plus named queries.

The graph is the `/api/graph` snapshot as a MultiDiGraph: one node per page (key and `slug` = page slug;
labels = its type and its layer in CamelCase, e.g. `:Paper:Source`, `:Idea:Concept`), one edge per
(pair, kind) with the kind upper-cased as its label (`:MENTIONS`, `:BOOK`, `:SHARES_SOURCE`). Symmetric
kinds are stored in both directions, so directed patterns find them.

GrandCypher covers labels, typed edges, `[:A|B]`, property filters, `[*1..3]`, COUNT/ORDER BY/LIMIT, DISTINCT,
CONTAINS/IN/STARTS WITH. It does not parse NOT patterns, OPTIONAL MATCH, shortestPath or COUNT {} and it
silently returns nothing for undirected patterns, so `check` rejects those with a hint to the named query
that answers the same question. Rejections are logged (`.cache/cypher-rejected.jsonl`): when that log
says the subset is too small, swap the engine behind `run` (e.g. Neo4j) and nothing upstream changes.

This module is the model (no services): kb_distillery.graph.query supplies the live vault graph, runs
queries on it and logs rejections.
"""
import re

import networkx as nx

from kb_distillery import kbconfig
from kb_distillery.graph.relations import edge_label, kind_name

MAX_ROWS = 500
TIMEOUT_S = 10.0
# Edge kinds are the knowledge base's: its kb.toml `[edges]` adds to these defaults (a template owns them from
# Phase 2). `labels` maps a snapshot link kind → edge label; wikilink and related are both "the page mentions the
# other". `symmetric` labels are stored in both directions. `types` are the relation kinds a page may state in
# its `relations:` block (kb_distillery.graph.relations; none by default), `note_required` the ones that need a note.
DEFAULT_LABELS = {"wikilink": "MENTIONS", "related": "MENTIONS"}
DEFAULT_SYMMETRIC = frozenset({"SHARES_SOURCE", "COLLABORATES_WITH", "SIMILAR_TO"})   # the symmetric computed kinds
# named queries that mean nothing unless the kb produces these edge labels
NEEDS = {"unaddressed-questions": frozenset({"ADDRESSES", "OPEN_PROBLEM_IN"})}


def _names(value):
    return [str(v) for v in value if v] if isinstance(value, list) else []


def edge_config(cfg=None):
    """{labels, symmetric, types, note_required} for a knowledge base: the defaults plus its `[edges]` table
    (`labels`, `symmetric`, `types`, `note_required`). `cfg` None = the knowledge base this process works on."""
    cfg = cfg if cfg is not None else kbconfig.current()
    section = cfg.section("edges") if cfg else {}
    given = section.get("labels")
    labels = dict(DEFAULT_LABELS)
    labels.update({str(k): str(v).upper() for k, v in given.items()} if isinstance(given, dict) else {})
    # a symmetric name counts in both spellings: as written upper-cased (a link label) and as a relation kind
    symmetric = set(DEFAULT_SYMMETRIC) | {f(s) for s in _names(section.get("symmetric")) for f in (str.upper, edge_label)}
    types = sorted({kind_name(t) for t in _names(section.get("types"))})
    note_required = {kind_name(t) for t in _names(section.get("note_required"))} & set(types)
    return {"labels": labels, "symmetric": symmetric, "types": types, "note_required": note_required}


def relation_label(kind, config):
    """The edge label of a relation kind: a kb `labels` mapping wins, else `open-problem-in` → OPEN_PROBLEM_IN."""
    return config["labels"].get(kind) or edge_label(kind)


_WRITE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL|LOAD|FOREACH)\b", re.I)
_UNSUPPORTED = [   # (pattern, message): checked on the query with string literals blanked out
    (re.compile(r"\bOPTIONAL\s+MATCH\b", re.I), "OPTIONAL MATCH is not supported; use a second query"),
    (re.compile(r"\b(all)?shortestPath\s*\(", re.I), "shortestPath is not supported; use the named query `shortest-path`"),
    (re.compile(r"\b(EXISTS|COUNT|COLLECT)\s*\{", re.I), "subqueries ({ … }) are not supported"),
    (re.compile(r"\bNOT\s*\(", re.I),
     "NOT (pattern) is not supported; use a named query (`list` shows them), e.g. `gaps`"),
    (re.compile(r"\)\s*-\s*(\[[^\]]*\])?\s*-\s*\("),
     "undirected patterns (a)-[r]-(b) are not supported; give the arrow a direction, or use `neighbourhood`"),
    (re.compile(r"\bUNION\b|\bWITH\b|\bUNWIND\b", re.I), "UNION / WITH / UNWIND are not supported"),
]
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


class QueryError(ValueError):
    """A query the engine will not run: `message` says why, `hint` what to do instead."""


def _label(text):
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[^A-Za-z0-9]+", text or "") if p)


def kinds(g, a, b):
    """Edge kinds from a to b."""
    return {d.get("kind") for d in (g.get_edge_data(a, b) or {}).values()}


def add_edge(g, a, b, kind, **attrs):
    """One edge per (a, b, kind). Keys stay NetworkX's integers: with string keys GrandCypher 1.2 silently
    returns nothing once a WHERE filters both ends."""
    if kind not in kinds(g, a, b):
        g.add_edge(a, b, kind=kind, __labels__={kind}, **attrs)


def to_graph(snapshot, config=None):
    """The snapshot dict (`build_graph_snapshot`) → nx.MultiDiGraph with GrandCypher labels (`config`: `edge_config()`)."""
    config = config or edge_config()
    g = nx.MultiDiGraph()
    for n in snapshot.get("nodes", []):
        labels = {lbl for lbl in (_label(n.get("type")), _label(n.get("layer"))) if lbl}
        g.add_node(n["id"], slug=n["id"], title=n.get("title") or n.get("label") or "", type=n.get("type", ""),
                   layer=n.get("layer", ""), depth=n.get("depth", ""), maturity=n.get("maturity", ""),
                   areas=list(n.get("areas") or []), year=n.get("year"), path=n.get("path", ""),
                   __labels__=labels or {"Page"})
    for l in snapshot.get("links", []):
        if l["source"] in g and l["target"] in g:
            kind = config["labels"].get(l.get("kind", "wikilink"), _label(l.get("kind", "")).upper())
            add_edge(g, l["source"], l["target"], kind, via=l.get("kind", ""), origin="computed")
            if kind in config["symmetric"]:
                add_edge(g, l["target"], l["source"], kind, via=l.get("kind", ""), origin="computed")
    for c in snapshot.get("concept_links", []):
        for a, b in ((c["source"], c["target"]), (c["target"], c["source"])):
            if a in g and b in g:
                add_edge(g, a, b, "SHARES_SOURCE", weight=c.get("shared", 0), origin="computed")
    for r in snapshot.get("relations") or []:      # typed relations (flag graph-relations); their mentions and
                                                   # shares-source repeat the edges above and add_edge drops them
        if r["source"] in g and r["target"] in g:
            kind = relation_label(r["kind"], config)
            attrs = {"origin": r.get("origin", ""), "note": r.get("note", ""), "weight": r.get("weight", 1.0),
                     "confidence": 1.0}          # a relation a person wrote is certain
            add_edge(g, r["source"], r["target"], kind, **attrs)
            if kind in config["symmetric"]:
                add_edge(g, r["target"], r["source"], kind, **attrs)
    return g


def add_proposed(g, config=None, root=None):
    """Every LLM relation proposal as an edge `origin="proposed"` with its `confidence` (also `weight`), so a query
    filters at query time: `MATCH (a)-[r:USES]->(b) WHERE r.confidence >= 0.8 RETURN a.slug, b.slug`. Stored and
    computed edges win over a proposal for the same (source, target, kind). Only kinds the kb declares count.
    The proposals are NOT in the graph snapshot (that is what the app draws and the share build publishes)."""
    from kb_distillery.graph.relations import PROPOSED, read_proposals

    config = config or edge_config()
    declared = set(config.get("types") or ())
    n = 0
    for r in read_proposals(root):
        if r["kind"] not in declared or r["from"] not in g or r["to"] not in g:
            continue
        kind = relation_label(r["kind"], config)
        attrs = {"origin": PROPOSED, "note": r["note"], "weight": r["confidence"], "confidence": r["confidence"]}
        add_edge(g, r["from"], r["to"], kind, **attrs)
        if kind in config["symmetric"]:
            add_edge(g, r["to"], r["from"], kind, **attrs)
        n += 1
    return n


def normalize(query):
    """Spellings GrandCypher rejects but means the same: 'single' → "double" quotes, != → <>."""
    q = re.sub(r"'([^'\"\\]*)'", r'"\1"', (query or "").strip().rstrip(";"))
    return re.sub(r"!=", "<>", q)


def check(query):
    """Raise QueryError unless `query` is in the supported read-only subset. Returns the normalized query."""
    q = normalize(query)
    if not q:
        raise QueryError("empty query")
    bare = _STRING.sub('""', q)
    if _WRITE.search(bare):
        raise QueryError("read-only: CREATE/MERGE/SET/DELETE/REMOVE/CALL are not allowed")
    if not re.match(r"MATCH\b", bare, re.I):
        raise QueryError("a query starts with MATCH")
    for pat, msg in _UNSUPPORTED:
        if pat.search(bare):
            raise QueryError(msg)
    if re.search(r"(?<!<)--(?!>)", bare):        # `-->` and `<--` are directed and fine
        raise QueryError("undirected patterns (a)--(b) are not supported; give the arrow a direction, "
                         "or use `neighbourhood`")
    return q


def _jsonable(v):
    if isinstance(v, (set, frozenset)):
        return sorted(_jsonable(x) for x in v)
    if isinstance(v, dict):
        return {str("labels" if k == "__labels__" else k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _table(columns, rows, limit):
    return {"columns": columns, "rows": rows[:limit], "row_count": min(len(rows), limit),
            "truncated": len(rows) > limit}


# ---- named queries: what GrandCypher cannot express, in plain NetworkX ------------------------------------

def _counts(d, min_confidence):
    """Does an edge count? A proposed edge only when a `min_confidence` was asked for and it reaches it."""
    if d.get("origin") != "proposed":
        return True
    return min_confidence is not None and float(d.get("confidence", 0)) >= float(min_confidence)


def _undirected(g, min_confidence=None):
    u = nx.Graph()
    u.add_nodes_from(g.nodes(data=True))
    u.add_edges_from((a, b) for a, b, d in g.edges(data=True) if a != b and _counts(d, min_confidence))
    return u


def _node(g, slug):
    if slug not in g:
        raise QueryError(f"no page `{slug}`")
    d = g.nodes[slug]
    return {"slug": slug, "title": d.get("title", ""), "type": d.get("type", "")}


def gaps(g, min_shared=2, layer="concept", min_confidence=None, limit=MAX_ROWS):
    """Pairs with ≥ min_shared common neighbours and no edge between them (either direction)."""
    u = _undirected(g, min_confidence)
    keep = [n for n, d in u.nodes(data=True) if not layer or d.get("layer") == layer]
    keep_set = set(keep)
    found = []
    for a in keep:
        counts = {}
        for c in u[a]:
            for b in u[c]:
                if b in keep_set and b > a and not u.has_edge(a, b):
                    counts[b] = counts.get(b, 0) + 1
        found += [(n, a, b) for b, n in counts.items() if n >= int(min_shared)]
    found.sort(key=lambda t: (-t[0], t[1], t[2]))
    rows = [[_node(g, a), _node(g, b), n] for n, a, b in found]
    return _table(["a", "b", "shared"], rows, limit)


def unaddressed_questions(g, min_confidence=None, limit=MAX_ROWS):
    """Question pages no page `ADDRESSES`, with what each is an open problem in. Proposed relations count only
    when `min_confidence` is given (and they reach it); stored relations always count."""
    rows = []
    for q, d in sorted(g.nodes(data=True)):
        if d.get("type") != "question":
            continue
        if any(d.get("kind") == "ADDRESSES" and _counts(d, min_confidence) for _, _, d in g.in_edges(q, data=True)):
            continue
        in_ = sorted({t for _, t, d in g.out_edges(q, data=True)
                      if d.get("kind") == "OPEN_PROBLEM_IN" and _counts(d, min_confidence)})
        rows.append([_node(g, q), in_])
    return _table(["question", "open_problem_in"], rows, limit)


def shortest_path(g, source, target, min_confidence=None, limit=MAX_ROWS):
    """The shortest chain of pages between two slugs, ignoring direction."""
    _node(g, source), _node(g, target)
    try:
        path = nx.shortest_path(_undirected(g, min_confidence), source, target)
    except nx.NetworkXNoPath:
        return _table(["path", "length"], [], limit)
    return _table(["path", "length"], [[[_node(g, s) for s in path], len(path) - 1]], limit)


def neighbourhood(g, slug, hops=1, min_confidence=None, limit=MAX_ROWS):
    """Pages within `hops` links of `slug` in either direction, nearest first."""
    _node(g, slug)
    dist = nx.single_source_shortest_path_length(_undirected(g, min_confidence), slug, cutoff=max(1, min(int(hops), 3)))
    rows = [[_node(g, s), d] for s, d in sorted(dist.items(), key=lambda t: (t[1], t[0])) if s != slug]
    return _table(["page", "hops"], rows, limit)


NAMED = {
    "gaps": (gaps, "pairs sharing ≥ min_shared neighbours with no link between them", ["min_shared", "layer", "min_confidence"]),
    "unaddressed-questions": (unaddressed_questions, "question pages nothing addresses (min_confidence also counts proposed relations)", ["min_confidence"]),
    "shortest-path": (shortest_path, "shortest chain of pages between source and target", ["source", "target", "min_confidence"]),
    "neighbourhood": (neighbourhood, "pages within `hops` links of `slug`, any direction", ["slug", "hops", "min_confidence"]),
}

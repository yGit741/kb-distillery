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
"""
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timezone

import networkx as nx

from kb.paths import CACHE_PATH

MAX_ROWS = 500
TIMEOUT_S = 10.0
REJECTED_LOG = os.path.join(CACHE_PATH, "cypher-rejected.jsonl")
SYMMETRIC = {"SHARES_SOURCE"}
# snapshot link kind → edge label; wikilink and related are both "the page mentions the other"
KIND_LABEL = {"wikilink": "MENTIONS", "related": "MENTIONS"}

_WRITE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|CALL|LOAD|FOREACH)\b", re.I)
_UNSUPPORTED = [   # (pattern, message): checked on the query with string literals blanked out
    (re.compile(r"\bOPTIONAL\s+MATCH\b", re.I), "OPTIONAL MATCH is not supported; use a second query"),
    (re.compile(r"\b(all)?shortestPath\s*\(", re.I), "shortestPath is not supported; use the named query `shortest-path`"),
    (re.compile(r"\b(EXISTS|COUNT|COLLECT)\s*\{", re.I), "subqueries ({ … }) are not supported"),
    (re.compile(r"\bNOT\s*\(", re.I),
     "NOT (pattern) is not supported; use the named queries `gaps` or `unaddressed-questions`"),
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


def to_graph(snapshot):
    """The snapshot dict (`build_graph_snapshot`) → nx.MultiDiGraph with GrandCypher labels."""
    g = nx.MultiDiGraph()
    for n in snapshot.get("nodes", []):
        labels = {lbl for lbl in (_label(n.get("type")), _label(n.get("layer"))) if lbl}
        g.add_node(n["id"], slug=n["id"], title=n.get("title") or n.get("label") or "", type=n.get("type", ""),
                   layer=n.get("layer", ""), depth=n.get("depth", ""), status=n.get("status", ""),
                   areas=list(n.get("areas") or []), year=n.get("year"), path=n.get("path", ""),
                   __labels__=labels or {"Page"})
    for l in snapshot.get("links", []):
        if l["source"] in g and l["target"] in g:
            kind = KIND_LABEL.get(l.get("kind", "wikilink"), _label(l.get("kind", "")).upper())
            add_edge(g, l["source"], l["target"], kind, via=l.get("kind", ""), origin="computed")
    for c in snapshot.get("concept_links", []):
        for a, b in ((c["source"], c["target"]), (c["target"], c["source"])):
            if a in g and b in g:
                add_edge(g, a, b, "SHARES_SOURCE", weight=c.get("shared", 0), origin="computed")
    return g


_cache = {"etag": None, "graph": None}
_lock = threading.Lock()


def current_graph():
    """The vault graph, rebuilt only when the snapshot etag changes."""
    from kb.services.graph import build_graph_snapshot

    snap = build_graph_snapshot()
    with _lock:
        if _cache["etag"] != snap["etag"]:
            _cache.update(etag=snap["etag"], graph=to_graph(snap))
        return _cache["graph"]


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


def run(query, limit=MAX_ROWS, graph=None, timeout=TIMEOUT_S):
    """Run a checked query → {columns, rows, row_count, truncated}. Raises QueryError (logged)."""
    from grandcypher import GrandCypher

    limit = max(1, min(int(limit), MAX_ROWS))
    try:
        q = check(query)
    except QueryError as e:
        log_rejected(query, str(e))
        raise
    g = current_graph() if graph is None else graph
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        res = pool.submit(GrandCypher(g).run, q).result(timeout=timeout)
    except FutureTimeout:
        log_rejected(query, "timeout")
        raise QueryError(f"query took longer than {timeout:g}s; add labels or a LIMIT") from None
    except Exception as e:  # noqa: BLE001 — the parser's own errors are the user's syntax errors
        msg = (str(e).splitlines() or [type(e).__name__])[0][:200]
        log_rejected(query, msg)
        raise QueryError(f"could not run the query: {msg}") from None
    finally:
        pool.shutdown(wait=False)
    columns = [str(c) for c in res]
    rows = [list(r) for r in zip(*(_jsonable(v) for v in res.values()))] if columns else []
    return _table(columns, rows, limit)


def log_rejected(query, reason, path=None):
    """Append one line to the rejection log; never raises (logging must not break a query)."""
    path = path or REJECTED_LOG
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "query": query, "reason": reason}) + "\n")
    except OSError:
        pass


# ---- named queries: what GrandCypher cannot express, in plain NetworkX ------------------------------------

def _undirected(g):
    u = nx.Graph()
    u.add_nodes_from(g.nodes(data=True))
    u.add_edges_from((a, b) for a, b in g.edges() if a != b)
    return u


def _node(g, slug):
    if slug not in g:
        raise QueryError(f"no page `{slug}`")
    d = g.nodes[slug]
    return {"slug": slug, "title": d.get("title", ""), "type": d.get("type", "")}


def gaps(g, min_shared=2, layer="concept", limit=MAX_ROWS):
    """Pairs with ≥ min_shared common neighbours and no edge between them (either direction)."""
    u = _undirected(g)
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


def unaddressed_questions(g, limit=MAX_ROWS):
    """Question pages no page `ADDRESSES`, with what each is an open problem in."""
    rows = []
    for q, d in sorted(g.nodes(data=True)):
        if d.get("type") != "question":
            continue
        if any(d.get("kind") == "ADDRESSES" for _, _, d in g.in_edges(q, data=True)):
            continue
        in_ = sorted({t for _, t, d in g.out_edges(q, data=True) if d.get("kind") == "OPEN_PROBLEM_IN"})
        rows.append([_node(g, q), in_])
    return _table(["question", "open_problem_in"], rows, limit)


def shortest_path(g, source, target, limit=MAX_ROWS):
    """The shortest chain of pages between two slugs, ignoring direction."""
    _node(g, source), _node(g, target)
    try:
        path = nx.shortest_path(_undirected(g), source, target)
    except nx.NetworkXNoPath:
        return _table(["path", "length"], [], limit)
    return _table(["path", "length"], [[[_node(g, s) for s in path], len(path) - 1]], limit)


def neighbourhood(g, slug, hops=1, limit=MAX_ROWS):
    """Pages within `hops` links of `slug` in either direction, nearest first."""
    _node(g, slug)
    dist = nx.single_source_shortest_path_length(_undirected(g), slug, cutoff=max(1, min(int(hops), 3)))
    rows = [[_node(g, s), d] for s, d in sorted(dist.items(), key=lambda t: (t[1], t[0])) if s != slug]
    return _table(["page", "hops"], rows, limit)


NAMED = {
    "gaps": (gaps, "pairs sharing ≥ min_shared neighbours with no link between them", ["min_shared", "layer"]),
    "unaddressed-questions": (unaddressed_questions, "question pages nothing addresses", []),
    "shortest-path": (shortest_path, "shortest chain of pages between source and target", ["source", "target"]),
    "neighbourhood": (neighbourhood, "pages within `hops` links of `slug`, any direction", ["slug", "hops"]),
}


def named_list():
    return [{"name": k, "description": d, "params": p} for k, (_, d, p) in NAMED.items()]


def run_named(name, params=None, limit=MAX_ROWS, graph=None):
    """Run a named query with string params → the same table shape as `run`. Raises QueryError."""
    if name not in NAMED:
        raise QueryError(f"unknown named query `{name}`; known: {', '.join(NAMED)}")
    fn, _, allowed = NAMED[name]
    params = dict(params or {})
    extra = set(params) - set(allowed)
    if extra:
        raise QueryError(f"`{name}` takes {', '.join(allowed) or 'no params'}; got {', '.join(sorted(extra))}")
    g = current_graph() if graph is None else graph
    limit = max(1, min(int(limit), MAX_ROWS))
    try:
        return fn(g, **params, limit=limit)
    except TypeError as e:
        raise QueryError(f"`{name}` needs {', '.join(allowed)}: {e}") from None
    except ValueError as e:
        if isinstance(e, QueryError):
            raise
        raise QueryError(f"bad parameter for `{name}`: {e}") from None

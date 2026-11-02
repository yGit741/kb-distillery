"""Read-only graph queries on the live vault graph (the model is kb_distillery.graph.model, the snapshot
kb_distillery.graph.snapshot): a checked subset of Cypher (GrandCypher on NetworkX) plus named queries.

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
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timezone

from kb_distillery.graph.model import (  # noqa: F401 — re-exported: the API and the CLI read the model from here
    DEFAULT_LABELS, DEFAULT_SYMMETRIC, MAX_ROWS, NAMED, NEEDS, TIMEOUT_S, QueryError, _jsonable, _table, add_edge,
    add_proposed, check, edge_config, gaps, kinds, neighbourhood, normalize, relation_label, shortest_path, to_graph,
    unaddressed_questions,
)
from kb_distillery.paths import CACHE_PATH

REJECTED_LOG = os.path.join(CACHE_PATH, "cypher-rejected.jsonl")

_cache = {"etag": None, "graph": None}
_lock = threading.Lock()


def _proposals_stamp(root=None):
    from kb_distillery import paths
    from kb_distillery.graph.relations import PROPOSALS_FILE
    try:
        st = os.stat(os.path.join(root or paths.ROOT, ".cache", PROPOSALS_FILE))
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def current_graph():
    """The vault graph, rebuilt only when the snapshot etag, whether it carries relations, or the proposals change."""
    from kb_distillery.graph.snapshot import build_graph_snapshot, relations_on

    snap = build_graph_snapshot()
    with_proposals = relations_on()
    key = (snap["etag"], snap.get("relations") is not None, _proposals_stamp() if with_proposals else None)
    with _lock:
        if _cache["etag"] != key:
            config = edge_config()
            g = to_graph(snap, config)
            if with_proposals:                       # proposals ride the same flag as stored relations
                add_proposed(g, config)
            _cache.update(etag=key, graph=g)
        return _cache["graph"]


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


def available(config=None):
    """Named queries this knowledge base can answer: those whose edge labels it produces (see NEEDS), i.e. a link
    kind it maps in `[edges] labels`, or (while the graph-relations flag is on) a relation kind it declares in
    `[edges] types`."""
    from kb_distillery.graph.snapshot import relations_on

    config = config or edge_config()
    produced = set(config["labels"].values())
    if relations_on():
        produced |= {relation_label(t, config) for t in config.get("types", ())}
    return [name for name in NAMED if NEEDS.get(name, frozenset()) <= produced]


def named_list(config=None):
    names = available(config)
    return [{"name": k, "description": d, "params": p} for k, (_, d, p) in NAMED.items() if k in names]


def run_named(name, params=None, limit=MAX_ROWS, graph=None, config=None):
    """Run a named query with string params → the same table shape as `run`. Raises QueryError."""
    if name not in NAMED:
        raise QueryError(f"unknown named query `{name}`; known: {', '.join(available(config))}")
    if name not in available(config):
        raise QueryError(f"`{name}` needs the edge kinds {', '.join(sorted(NEEDS[name]))}; this knowledge base "
                         f"declares none: declare them in kb.toml [edges] types. "
                         f"Known: {', '.join(available(config))}")
    fn, _, allowed = NAMED[name]
    params = dict(params or {})
    extra = set(params) - set(allowed)
    if extra:
        raise QueryError(f"`{name}` takes {', '.join(allowed) or 'no params'}; got {', '.join(sorted(extra))}")
    g = current_graph() if graph is None else graph
    limit = max(1, min(int(limit), MAX_ROWS))
    try:
        if "min_confidence" in params:                       # checked up front, not only when a proposed edge is compared
            params["min_confidence"] = float(params["min_confidence"]) if params["min_confidence"] not in (None, "") else None
        return fn(g, **params, limit=limit)
    except TypeError as e:
        raise QueryError(f"`{name}` needs {', '.join(allowed)}: {e}") from None
    except ValueError as e:
        if isinstance(e, QueryError):
            raise
        raise QueryError(f"bad parameter for `{name}`: {e}") from None

#!/usr/bin/env python3
"""Read-only graph queries over the wiki graph (0 LLM). Logic: kb_distillery.graph.query.

  python3 -m kb_distillery.search.cypher run 'MATCH (p:Source)-[:MENTIONS]->(i:Idea) RETURN p.slug, i.slug' [--limit N]
  python3 -m kb_distillery.search.cypher named gaps [--param min_shared=3] [--limit N]
  python3 -m kb_distillery.search.cypher list                     # the named queries and their params
  add --json for the raw table

Strings in a query take double quotes. Supported: labels (:Paper, :Idea, :Source, :Concept …), typed edges
(:MENTIONS, :BOOK, :SHARES_SOURCE), [:A|B], WHERE filters, [*1..3], COUNT/ORDER BY/LIMIT, DISTINCT,
CONTAINS/IN/STARTS WITH. Not supported (rejected with a hint): NOT patterns, OPTIONAL MATCH, shortestPath,
subqueries, undirected patterns — use the named queries instead.
"""
import argparse
import json
import sys

from kb_distillery.graph import query as cypher


def _cell(v):
    if isinstance(v, dict):
        return v.get("slug") or json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return ", ".join(_cell(x) for x in v)
    return "" if v is None else str(v)


def _print(table, as_json):
    if as_json:
        print(json.dumps(table, ensure_ascii=False, indent=1))
        return
    print("\t".join(table["columns"]))
    for row in table["rows"]:
        print("\t".join(_cell(v) for v in row))
    more = " (truncated)" if table["truncated"] else ""
    print(f"-- {table['row_count']} row(s){more}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kb_distillery.search.cypher", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a Cypher query (supported subset)")
    r.add_argument("query")
    n = sub.add_parser("named", help="run a named query")
    n.add_argument("name")
    n.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    sub.add_parser("list", help="list named queries")
    for p in (r, n):
        p.add_argument("--limit", type=int, default=cypher.MAX_ROWS)
        p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for q in cypher.named_list():
            print(f"{q['name']}\t{' '.join(q['params']) or '-'}\t{q['description']}")
        return 0
    try:
        if a.cmd == "run":
            table = cypher.run(a.query, limit=a.limit)
        else:
            params = dict(kv.split("=", 1) for kv in a.param if "=" in kv)
            table = cypher.run_named(a.name, params, limit=a.limit)
    except cypher.QueryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _print(table, a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

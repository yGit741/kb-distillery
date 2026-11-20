"""The IR is one typed property graph: nodes and edges, each edge tagged with the layer that found it and
the exact place (repo, path, line) the fact was read from. JSON for diffing, SQLite for querying."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

LAYERS = ["file", "include", "symbol", "call", "config", "history"]


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._seen: set[tuple] = set()
        self.meta: dict = {}

    def node(self, id_: str, kind: str, name: str, **attrs) -> str:
        n = self.nodes.get(id_)
        if n is None:
            n = self.nodes[id_] = {"id": id_, "kind": kind, "name": name}
        for k, v in attrs.items():
            if v in (None, "", [], {}):
                continue
            if k == "locs":  # extra anchors (declaration + definition, overloads)
                n.setdefault("locs", [])
                n["locs"] += [x for x in v if x not in n["locs"]]
            elif k not in n or k in ("line", "end", "path", "repo") and attrs.get("primary"):
                n[k] = v
        n.pop("primary", None)
        return id_

    def edge(self, src: str, dst: str, kind: str, layer: str, repo: str | None = None, path: str | None = None,
             line: int | None = None, conf: str = "exact", **attrs) -> None:
        key = (src, dst, kind, layer, repo, path, line, attrs.get("port"), attrs.get("via"))
        if key in self._seen:
            return
        self._seen.add(key)
        e = {"src": src, "dst": dst, "kind": kind, "layer": layer, "conf": conf}
        if repo:
            e.update(repo=repo, path=path, line=line)
        e.update({k: v for k, v in attrs.items() if v not in (None, "", [], {})})
        self.edges.append(e)

    # ---- queries
    def out(self, src: str, kind: str | None = None, layer: str | None = None) -> list[dict]:
        return [e for e in self.edges if e["src"] == src and (kind is None or e["kind"] == kind) and (layer is None or e["layer"] == layer)]

    def into(self, dst: str, kind: str | None = None, layer: str | None = None) -> list[dict]:
        return [e for e in self.edges if e["dst"] == dst and (kind is None or e["kind"] == kind) and (layer is None or e["layer"] == layer)]

    def stats(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodes_by_kind": dict(Counter(n["kind"] for n in self.nodes.values()).most_common()),
            "edges_by_layer": dict(Counter(e["layer"] for e in self.edges).most_common()),
            "edges_by_kind": dict(Counter(f'{e["layer"]}.{e["kind"]}' for e in self.edges).most_common()),
            "edges_by_conf": dict(Counter(e["conf"] for e in self.edges).most_common()),
        }

    # ---- persistence
    def save(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        nodes = sorted(self.nodes.values(), key=lambda n: n["id"])
        edges = sorted(self.edges, key=lambda e: (e["layer"], e["kind"], e["src"], e["dst"], e.get("path") or "", e.get("line") or 0))
        (out / "ir.json").write_text(json.dumps({"meta": self.meta, "stats": self.stats(), "nodes": nodes, "edges": edges}, indent=1, sort_keys=True))
        db = out / "ir.db"
        db.unlink(missing_ok=True)
        con = sqlite3.connect(db)
        con.executescript(
            """
            create table nodes(id text primary key, kind text, name text, repo text, path text, line int, end int, attrs text);
            create table edges(src text, dst text, kind text, layer text, conf text, repo text, path text, line int, attrs text);
            create index e_src on edges(src); create index e_dst on edges(dst); create index e_layer on edges(layer, kind);
            create index n_kind on nodes(kind); create index n_path on nodes(repo, path);
            """
        )
        core = {"id", "kind", "name", "repo", "path", "line", "end"}
        con.executemany("insert into nodes values(?,?,?,?,?,?,?,?)", [
            (n["id"], n["kind"], n["name"], n.get("repo"), n.get("path"), n.get("line"), n.get("end"),
             json.dumps({k: v for k, v in n.items() if k not in core}, sort_keys=True)) for n in nodes])
        ecore = {"src", "dst", "kind", "layer", "conf", "repo", "path", "line"}
        con.executemany("insert into edges values(?,?,?,?,?,?,?,?,?)", [
            (e["src"], e["dst"], e["kind"], e["layer"], e["conf"], e.get("repo"), e.get("path"), e.get("line"),
             json.dumps({k: v for k, v in e.items() if k not in ecore}, sort_keys=True)) for e in edges])
        con.commit()
        con.close()

    @classmethod
    def load(cls, out: Path) -> "Graph":
        d = json.loads((out / "ir.json").read_text())
        g = cls()
        g.meta = d["meta"]
        g.nodes = {n["id"]: n for n in d["nodes"]}
        g.edges = d["edges"]
        return g

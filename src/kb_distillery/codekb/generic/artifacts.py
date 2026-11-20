"""The artifact graph: the part of the IR a knowledge-base app draws between the concepts and the sources.

The IR (ir.json, tens of thousands of nodes) stays on the machine that built it. The artifact graph is its small
projection, written to `<kb>/artifacts/graph.json`:

    nodes  typed (Repo, Folder, File, Class, Function, Option, ...), each with one `parent` (containment), so a viewer
           can draw repositories first and drill into a folder, a file, a class
    links  typed and directed (imports, inherits, calls, runs, co-changes, reads, ...), with a weight and the first
           place the fact was read (`at`). An IR edge whose end is not exported is lifted to that end's nearest
           exported ancestor (a neighbour repo's file becomes its folder), so no dependency is dropped
    repos  the pinned commit of every repository and the web address of its files; a node's address is
           `repos[node.repo].web + node.path (+ "#L" + node.line)`, a link's is `repos[<repo>].web + <path#Lline>`
           for `at: "<repo>:<path#Lline>"`. Addresses are not repeated on every record: the file stays small
    cards  for every fact of every card, the artifact nodes its anchors fall in: a wiki page that cites the fact is
           thereby connected to those nodes, with nothing written by hand
    views  how a viewer should draw it (which types and relations, how to nest and colour); empty here: the viewer decides

Nothing here is written by a model, and the output is sorted: the same commits give the same file.
"""
from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict
from pathlib import Path

from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.project import Project

VERSION = 1
FILE_ROLES = ("focus", "platform")          # repos whose files and classes are exported; the rest stop at folders
CODE_LANG = {"cpp", "python"}
CONFIG_KINDS = {"reads_env": "reads", "defines": "defines"}
NEIGHBOUR_DIR_DEPTH = 1


class Artifacts:
    def __init__(self, g: Graph, p: Project):
        self.g, self.p = g, p
        self.nodes: dict[str, dict] = {}
        self.links: dict[tuple, dict] = {}
        self.alias: dict[str, str | None] = {}
        self.role = {r.name: r.role for r in p.repos}
        self.spans: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
        self.web = {r.name: p.permalink(r.name, g.meta["repos"][r.name]["sha"], "") for r in p.repos if r.name in g.meta["repos"]}
        self.web = {k: v for k, v in self.web.items() if v}

    # ---- nodes
    def add(self, id_: str, type_: str, name: str, parent: str | None = None, **attrs) -> str:
        n = self.nodes.get(id_)
        if n is None:
            n = self.nodes[id_] = {"id": id_, "type": type_, "name": name}
            if parent:
                n["parent"] = parent
        n.update({k: v for k, v in attrs.items() if v not in (None, "", [], {})})
        return id_

    def folder(self, repo: str, d: str) -> str:
        """The Folder node of a directory (created with its ancestors); the Repo node for the root."""
        if not d:
            return f"repo:{repo}"
        id_ = f"dir:{repo}:{d}"
        if id_ not in self.nodes:
            self.add(id_, "Folder", posixpath.basename(d), self.folder(repo, posixpath.dirname(d)), repo=repo, path=d)
        return id_

    def span(self, ir_id: str) -> None:
        n = self.g.nodes[ir_id]
        if n.get("repo") and n.get("path") and n.get("line"):
            self.spans[(n["repo"], n["path"])].append((n["line"], n.get("end") or n["line"], ir_id))
            for loc in n.get("locs") or []:
                self.spans[(loc[0], loc[1])].append((loc[2], loc[3] or loc[2], ir_id))

    # ---- resolution: IR id -> exported id (itself, or the nearest exported ancestor)
    def resolve(self, ir_id: str) -> str | None:
        if ir_id in self.nodes:
            return ir_id
        if ir_id in self.alias:
            return self.alias[ir_id]
        self.alias[ir_id] = None  # guards against a cycle while resolving
        n = self.g.nodes.get(ir_id)
        hit = None
        if n is not None:
            kind = n["kind"]
            if kind in ("method", "function") and n.get("cls"):
                hit = self.resolve(f"class:{n['cls']}")
            if hit is None and n.get("repo") and n.get("path"):
                hit = self.at(n["repo"], n["path"])
            if hit is None and n.get("repo") in self.role:
                hit = f"repo:{n['repo']}"
        self.alias[ir_id] = hit
        return hit

    def at(self, repo: str, path: str) -> str | None:
        """The exported node that stands for a file path: the File, else its deepest exported folder, else the Repo."""
        if repo not in self.role:
            return None
        if f"file:{repo}:{path}" in self.nodes:
            return f"file:{repo}:{path}"
        d = posixpath.dirname(path)
        while d and f"dir:{repo}:{d}" not in self.nodes:
            d = posixpath.dirname(d)
        return f"dir:{repo}:{d}" if d else f"repo:{repo}"

    # ---- links
    def link(self, src: str, dst: str, kind: str, e: dict | None = None, weight: int = 1, loops: bool = False, **attrs) -> None:
        a, b = self.resolve(src), self.resolve(dst)
        if not a or not b or (a == b and not loops) or self.inside(a, b) or self.inside(b, a):
            return
        key = (a, b, kind)
        m = self.links.get(key)
        if m is None:
            m = self.links[key] = {"source": a, "target": b, "kind": kind, "weight": 0}
            if e and e.get("repo") in self.web and e.get("path"):
                m["at"] = f"{e['repo']}:{e['path']}" + (f"#L{e['line']}" if e.get("line") else "")
        m["weight"] += weight
        for k, v in attrs.items():
            if v not in (None, "", [], {}, False):
                m[k] = v

    def inside(self, a: str, b: str) -> bool:
        """True when `a` is a descendant of `b` (a link from a file to its own folder says nothing)."""
        seen = 0
        while a and seen < 64:
            a = self.nodes.get(a, {}).get("parent")
            if a == b:
                return True
            seen += 1
        return False

    # ---- the generic tier: any repo, any language
    def generic(self) -> None:
        g, meta = self.g, self.g.meta["repos"]
        for r in self.p.repos:
            m = meta[r.name]
            url = self.p.permalink(r.name, m["sha"], "", kind="tree") if r.git else r.web
            self.add(f"repo:{r.name}", "Repo", r.display, role=r.role, repo=r.name, sha=m["sha"], files=m.get("files"), url=url,
                     commits=(g.meta.get("history", {}).get(r.name) or {}).get("commits"))
        files = [n for n in g.nodes.values() if n["kind"] == "file" and n.get("repo") in self.role]
        coded = {n["id"] for n in files if n.get("lang") in CODE_LANG}
        for e in g.edges:  # a build or config file that carries a fact is part of the picture too
            if e["layer"] in ("build", "config", "output") and e["src"].startswith("file:"):
                coded.add(e["src"])
        for n in sorted(files, key=lambda n: n["id"]):
            repo, path = n["repo"], n["path"]
            if n["id"] not in coded:
                continue
            if self.role[repo] in FILE_ROLES:
                self.add(n["id"], "File", posixpath.basename(path), self.folder(repo, posixpath.dirname(path)), repo=repo, path=path,
                         lang=n.get("lang"), loc=n.get("loc"), commits=n.get("n_commits"), mrs=n.get("n_mrs"), authors=n.get("authors"),
                         last_change=n.get("last_change"), entry=n.get("entry"))
            else:
                parts = posixpath.dirname(path).split("/")[:NEIGHBOUR_DIR_DEPTH]
                self.folder(repo, "/".join(p for p in parts if p))
        for n in sorted((n for n in g.nodes.values() if n["kind"] in ("class", "struct")), key=lambda n: n["id"]):
            f = f"file:{n.get('repo')}:{n.get('path')}"
            if f in self.nodes:
                self.add(n["id"], "Class", n["name"].replace("::", ".").split(".")[-1], f, full=n["name"], repo=n["repo"], path=n["path"],
                         line=n.get("line"), methods=n.get("n_methods"), doc=(n.get("doc") or "")[:200])
                self.span(n["id"])
        focus = {r.name for r in self.p.focus}
        for n in sorted((n for n in g.nodes.values() if n["kind"] in ("method", "function")), key=lambda n: n["id"]):
            if n.get("repo") not in focus or not n.get("defined"):
                continue
            parent = f"class:{n['cls']}" if n.get("cls") and f"class:{n['cls']}" in self.nodes else f"file:{n['repo']}:{n['path']}"
            if parent in self.nodes:
                self.add(n["id"], "Function", re.split(r"::|\.", n["name"])[-1], parent, full=n["name"], repo=n["repo"], path=n["path"],
                         line=n.get("line"), doc=(n.get("doc") or "")[:200])
                self.span(n["id"])
        for n in sorted((n for n in g.nodes.values() if n["kind"] in ("flag", "env-var")), key=lambda n: n["id"]):
            parent = self.at(n["repo"], n["path"]) if n.get("repo") and n.get("path") else None
            self.add(n["id"], "Option", n["name"], parent, option={"flag": "flag", "env-var": "environment"}[n["kind"]],
                     repo=n.get("repo"), path=n.get("path"), line=n.get("line"), doc=(n.get("doc") or "")[:200])
        for e in g.edges:
            layer, kind = e["layer"], e["kind"]
            if layer == "include" and kind == "includes":
                if g.nodes.get(e["dst"], {}).get("kind") == "file":
                    self.link(e["src"], e["dst"], "imports", e)
            elif layer == "symbol" and kind == "inherits":
                self.link(e["src"], e["dst"], "inherits", e)
            elif layer == "call" and kind in ("calls", "runs"):
                self.link(e["src"], e["dst"], kind, e)
            elif layer == "history" and kind == "cochange":
                self.link(e["src"], e["dst"], "co-changes", e, weight=e.get("n", 1), jaccard=e.get("jaccard"))
            elif layer == "config" and kind in CONFIG_KINDS and e["dst"] in self.nodes:
                self.link(e["src"], e["dst"], CONFIG_KINDS[kind], e)

    def adopt(self) -> None:
        """Give every node a place in the containment tree. A node the code does not place (an environment variable read
        in several files, a symbol nobody produces) goes under the repository of the first link that touches it; one
        with no link at all says nothing and is left out."""
        orphans = sorted(i for i, n in self.nodes.items() if n["type"] != "Repo" and n.get("parent") not in self.nodes)
        if not orphans:
            return
        home: dict[str, str] = {}
        for (a, b, _kind) in sorted(self.links):
            for me, other in ((a, b), (b, a)):
                repo = self.nodes[other].get("repo")
                if me not in home and repo and f"repo:{repo}" in self.nodes:
                    home[me] = f"repo:{repo}"
        for i in orphans:
            if i in home and self.nodes[i].get("name"):
                self.nodes[i]["parent"] = home[i]
                self.nodes[i].setdefault("repo", home[i][5:])
            else:
                del self.nodes[i]
        self.links = {k: v for k, v in self.links.items() if k[0] in self.nodes and k[1] in self.nodes}

    # ---- cards: which nodes a fact is about
    def cards(self, index: list[dict]) -> dict:
        prefixes = []
        for r in self.p.repos:
            sha = self.g.meta["repos"][r.name]["sha"]
            base = self.p.permalink(r.name, sha, "")
            if base:
                prefixes.append((base, r.name))
        for spans in self.spans.values():
            spans.sort(key=lambda s: (s[1] - s[0], s[0]))  # the innermost span first
        self.exact, whole = {}, defaultdict(list)  # a node declared on exactly that line; a node that is a whole file
        for n in self.nodes.values():
            if n["type"] in ("Class", "Function", "File", "Folder", "Repo") or not n.get("repo") or not n.get("path"):
                continue
            if n.get("line"):
                self.exact.setdefault((n["repo"], n["path"], n["line"]), n["id"])
            else:
                whole[(n["repo"], n["path"])].append(n["id"])
        self.whole = {k: v[0] for k, v in whole.items() if len(v) == 1}
        out = {}
        for c in index:
            facts, union = {}, []
            for f in c.get("fact_list", []):
                ids = []
                for url in f.get("anchors", []):
                    hit = self.anchor(url, prefixes)
                    if hit and hit not in ids:
                        ids.append(hit)
                if not ids and c.get("repo") and f"repo:{c['repo']}" in self.nodes and not f.get("anchors"):
                    ids = [f"repo:{c['repo']}"]
                if ids:
                    facts[f["id"]] = ids
                    union += [i for i in ids if i not in union]
            out[c["slug"]] = {"title": c["title"].removeprefix("IR: "), "repo": c.get("repo") or None, "nodes": sorted(union), "facts": facts}
        return out

    def anchor(self, url: str, prefixes: list[tuple[str, str]]) -> str | None:
        for base, repo in prefixes:
            if url.startswith(base):
                rest = url[len(base):].lstrip("/")
                path, _, frag = rest.partition("#")
                m = re.match(r"L(\d+)", frag)
                if m:
                    line = int(m.group(1))
                    if (repo, path, line) in self.exact:
                        return self.exact[(repo, path, line)]
                    for lo, hi, ir_id in self.spans.get((repo, path), []):
                        if lo <= line <= hi:
                            return self.resolve(ir_id)
                return self.whole.get((repo, path)) or self.at(repo, path)
        return None

    # ---- output
    def data(self, index: list[dict]) -> dict:
        """Types and relations are named, not described: a viewer that wants labels and colours brings its own."""
        return {
            "version": VERSION, "generator": self.g.meta.get("generator"), "project": self.p.name,
            "repos": {r: {"sha": m["sha"], "web": self.web.get(r, "")} for r, m in sorted(self.g.meta["repos"].items())},
            "types": {t: {} for t in sorted({n["type"] for n in self.nodes.values()})},
            "relations": {k: {} for k in sorted({l["kind"] for l in self.links.values()})},
            "views": [],
            "nodes": sorted(self.nodes.values(), key=lambda n: n["id"]),
            "links": sorted(self.links.values(), key=lambda l: (l["kind"], l["source"], l["target"])),
            "cards": self.cards(index),
        }


def dumps(data: dict) -> str:
    """Compact, but one node / link / card per line, so a rebuild at a new commit gives a readable diff."""
    def one(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    out = ["{"]
    keys = sorted(data)
    for i, k in enumerate(keys):
        v, end = data[k], "" if i == len(keys) - 1 else ","
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out.append(f'"{k}":[')
            out += [one(x) + ("," if j < len(v) - 1 else "") for j, x in enumerate(v)]
            out.append("]" + end)
        elif isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            out.append(f'"{k}":{{')
            out += [f"{json.dumps(kk)}:{one(x)}" + ("," if j < len(v) - 1 else "") for j, (kk, x) in enumerate(sorted(v.items()))]
            out.append("}" + end)
        else:
            out.append(f'"{k}":{one(v)}{end}')
    out.append("}")
    return "\n".join(out) + "\n"


def build(g: Graph, p: Project) -> Artifacts:
    a = Artifacts(g, p)
    a.generic()
    a.adopt()
    return a


def export(p: Project, dest: Path) -> dict:
    """Write the artifact graph of the project's built IR and cards to `dest` (a `graph.json` path). Returns the counts."""
    out = p.out
    index_file = out / "cards" / "index.json"
    if not (out / "ir.json").is_file() or not index_file.is_file():
        raise SystemExit(f"{out} has no IR or cards yet: run `distill code build` and `distill code cards` first")
    a = build(Graph.load(out), p)
    data = a.data(json.loads(index_file.read_text()))
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = dumps(data)
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8")
    by_type: dict[str, int] = defaultdict(int)
    for n in data["nodes"]:
        by_type[n["type"]] += 1
    by_kind: dict[str, int] = defaultdict(int)
    for l in data["links"]:
        by_kind[l["kind"]] += 1
    return {"nodes": len(data["nodes"]), "links": len(data["links"]), "types": dict(sorted(by_type.items())),
            "relations": dict(sorted(by_kind.items())), "cards": len(data["cards"]), "bytes": dest.stat().st_size}

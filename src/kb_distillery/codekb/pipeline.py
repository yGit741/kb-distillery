"""Project -> IR -> cards: the deterministic core every command shares."""
from __future__ import annotations

import time

from kb_distillery.codekb.generic.cards import build_cards, write_cards
from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.history import emit_history
from kb_distillery.codekb.generic.index import RepoIndex, emit_files
from kb_distillery.codekb.generic.project import Project

GENERATOR = "kb-distillery codekb v1"
LAYERS_PER_FOCUS = ("include", "symbol", "history")   # layers a focus repo is expected to have facts in


def build(p: Project, quiet: bool = False) -> Graph:
    """Parse the repos and write <out>/ir.json and ir.db. C++ needs the optional tree-sitter; the Python tier does not."""
    t0 = time.time()
    ix = RepoIndex(p.repos)
    g = Graph()
    g.meta = {"generator": GENERATOR, "project": p.name, "tiers": list(p.tiers),
              "repos": {r.name: {"sha": ix.sha[r.name], "role": r.role, "files": len(ix.tracked[r.name])} for r in p.repos}}
    stats: dict[str, dict] = {"files": emit_files(ix, g)}
    if "cpp" in p.tiers:
        from kb_distillery.codekb.cpp.index import Index, emit_cpp
        stats["cpp"] = emit_cpp(Index(ix, verbose=not quiet), g, p.call_repos)
    if "python" in p.tiers:
        from kb_distillery.codekb.pylang.index import emit_python
        stats["python"] = emit_python(ix, g, p.call_repos, verbose=not quiet)
    stats["history"] = emit_history(p, ix, g)
    g.meta["layer_stats"] = stats
    g.meta["drift"] = drift(p, g)
    g.meta["seconds"] = round(time.time() - t0, 1)
    g.save(p.out)
    s = g.stats()
    print(f"IR: {s['nodes']} nodes, {s['edges']} edges in {g.meta['seconds']}s -> {p.out}/ir.json, ir.db")
    for k, v in s["edges_by_layer"].items():
        print(f"  {k:8} {v}")
    for w in g.meta.get("warnings", []) + g.meta["drift"]:
        print(f"  warning: {w}")
    return g


def drift(p: Project, g: Graph) -> list[str]:
    """A layer that finds nothing in a focus repo usually means a rule no longer matches, not that the code has none. Say so
    instead of shipping an empty layer silently."""
    per = {(e.get("repo"), e["layer"]) for e in g.edges}
    per |= {(repo, "history") for repo, h in g.meta.get("history", {}).items() if h.get("feature_mrs") or h.get("cochange_pairs")}
    out = []
    for r in p.focus:
        empty = [layer for layer in LAYERS_PER_FOCUS if (r.name, layer) not in per and not (layer == "history" and not r.git)]
        if empty:
            out.append(f"{r.name}: no facts in layer(s) {', '.join(empty)} (the repo has none, or its language is not in `tiers`)")
        h = g.meta.get("history", {}).get(r.name, {})
        if r.git and h.get("commits", 0) <= 1:
            out.append(f"{r.name}: {h.get('commits', 0)} commit(s) in history: the checkout is shallow; clone deeper for history and co-change")
    return out


def cards(p: Project) -> list[dict]:
    """Cut the built IR into <out>/cards/*.md and index.json."""
    index = write_cards(build_cards(Graph.load(p.out), p), p.out)
    for c in index:
        print(f"  {c['slug']:44s} {c['facts']:5d} facts")
    print(f"{len(index)} cards, {sum(c['facts'] for c in index)} facts -> {p.out}/cards")
    return index


__all__ = ["build", "cards", "drift"]

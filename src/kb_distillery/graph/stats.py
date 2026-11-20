"""The size of a knowledge base's graph, for the header menu: how many concept and source nodes it has and how
many edges join two concepts (one per pair, either direction, no self links). `/api/kb/stats` counts with it.

No imports: it reads a graph snapshot dict only."""


def graph_stats(snapshot: dict) -> dict:
    layer = {n.get("id"): n.get("layer") for n in snapshot.get("nodes") or []}
    pairs = set()
    for link in snapshot.get("links") or []:
        a, b = link.get("source"), link.get("target")
        if a != b and layer.get(a) == "concept" and layer.get(b) == "concept":
            pairs.add((a, b) if a < b else (b, a))
    return {"concepts": sum(v == "concept" for v in layer.values()),
            "sources": sum(v == "source" for v in layer.values()),
            "edges": len(pairs)}

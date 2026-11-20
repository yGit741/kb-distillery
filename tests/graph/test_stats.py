"""graph_stats: concepts, sources and concept-to-concept pairs of a graph snapshot."""
from kb_distillery.graph.stats import graph_stats


def test_counts_layers_and_concept_pairs_once():
    snap = {
        "nodes": [{"id": "a", "layer": "concept"}, {"id": "b", "layer": "concept"}, {"id": "c", "layer": "concept"},
                  {"id": "s", "layer": "source"}, {"id": "r", "layer": "relation"}],
        "links": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"},   # one pair, both directions
                  {"source": "a", "target": "a"},                                     # a self link is no edge
                  {"source": "a", "target": "s"},                                     # concept to source: no edge
                  {"source": "b", "target": "c"}],
    }
    assert graph_stats(snap) == {"concepts": 3, "sources": 1, "edges": 2}


def test_empty_snapshot():
    assert graph_stats({}) == {"concepts": 0, "sources": 0, "edges": 0}

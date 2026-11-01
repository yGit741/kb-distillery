"""Proposed relations are edges of the QUERY graph, filterable by confidence; never part of the snapshot."""
import json
import os

import networkx as nx
import pytest

from kb_distillery import paths
from kb_distillery.graph import propose, relations
from kb_distillery.services import cypher

CONFIG = {"labels": {}, "symmetric": {"CONTRADICTS"}, "types": ["addresses", "contradicts", "extends", "open-problem-in", "uses"],
          "note_required": {"contradicts"}}


def graph():
    g = nx.MultiDiGraph()
    for slug, typ in (("a", "idea"), ("b", "idea"), ("c", "paper"), ("q", "question"), ("p", "paper")):
        g.add_node(slug, slug=slug, title=slug.upper(), type=typ, layer="concept", depth="", status="", areas=[],
                   year=None, path="", __labels__={typ.capitalize()})
    return g


def write(root, rows):
    os.makedirs(os.path.join(root, ".cache"), exist_ok=True)
    with open(os.path.join(root, ".cache", relations.PROPOSALS_FILE), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def row(a, b, kind, conf, **kw):
    return {"from": a, "to": b, "kind": kind, "confidence": conf, "note": kw.get("note", ""), "run": "r1"}


def test_the_file_name_matches_what_propose_writes():
    assert relations.PROPOSALS_FILE == propose.OUT_FILE


def test_read_proposals_keeps_the_best_per_key_skips_junk_and_sorts(tmp_path):
    assert relations.read_proposals(str(tmp_path)) == []
    write(str(tmp_path), [row("a", "b", "uses", 0.4), row("a", "b", "Uses", 0.9), row("c", "a", "extends", 0.6)])
    with open(tmp_path / ".cache" / relations.PROPOSALS_FILE, "a") as f:
        f.write("not json\n" + json.dumps({"from": "x"}) + "\n")
    got = relations.read_proposals(str(tmp_path))
    assert [(r["from"], r["to"], r["kind"], r["confidence"]) for r in got] == [("a", "b", "uses", 0.9), ("c", "a", "extends", 0.6)]


def test_every_proposal_becomes_an_edge_with_its_confidence(tmp_path):
    write(str(tmp_path), [row("a", "b", "uses", 0.9), row("a", "c", "uses", 0.35), row("a", "b", "bogus", 0.9),
                          row("a", "nowhere", "uses", 0.9)])
    g = graph()
    assert cypher.add_proposed(g, CONFIG, str(tmp_path)) == 2                # undeclared kind and missing page skipped
    edges = {(a, b): d for a, b, d in g.edges(data=True)}
    assert edges[("a", "b")]["origin"] == "proposed" and edges[("a", "b")]["confidence"] == 0.9
    assert edges[("a", "c")]["confidence"] == 0.35                           # weak ones are in too


def test_a_query_filters_by_confidence_at_query_time(tmp_path):
    write(str(tmp_path), [row("a", "b", "uses", 0.9), row("a", "c", "uses", 0.35)])
    g = graph()
    cypher.add_proposed(g, CONFIG, str(tmp_path))
    strong = cypher.run("MATCH (x)-[r:USES]->(y) WHERE r.confidence >= 0.8 RETURN x.slug, y.slug, r.confidence", graph=g)
    assert strong["rows"] == [["a", "b", 0.9]]
    everything = cypher.run("MATCH (x)-[r:USES]->(y) RETURN x.slug, y.slug", graph=g)
    assert everything["row_count"] == 2
    weak = cypher.run('MATCH (x)-[r]->(y) WHERE r.origin = "proposed" AND r.confidence < 0.5 RETURN y.slug', graph=g)
    assert weak["rows"] == [["c"]]


def test_a_stored_relation_wins_over_a_proposal_and_counts_as_certain(tmp_path):
    g = graph()
    cypher.add_edge(g, "a", "b", "USES", origin="stored", note="mine", weight=1.0, confidence=1.0)
    write(str(tmp_path), [row("a", "b", "uses", 0.5)])
    cypher.add_proposed(g, CONFIG, str(tmp_path))
    kinds = [d for _, _, d in g.edges(data=True)]
    assert len(kinds) == 1 and kinds[0]["origin"] == "stored" and kinds[0]["confidence"] == 1.0


def test_a_symmetric_proposal_goes_both_ways(tmp_path):
    write(str(tmp_path), [row("a", "b", "contradicts", 0.7, note="x vs y")])
    g = graph()
    cypher.add_proposed(g, CONFIG, str(tmp_path))
    assert g.has_edge("a", "b") and g.has_edge("b", "a")


def test_named_queries_ignore_proposals_unless_asked(tmp_path):
    write(str(tmp_path), [row("p", "q", "addresses", 0.9), row("q", "a", "open-problem-in", 0.8)])
    g = graph()
    cypher.add_proposed(g, CONFIG, str(tmp_path))
    default = cypher.unaddressed_questions(g)
    assert [r[0]["slug"] for r in default["rows"]] == ["q"]                  # nothing addresses q as far as it is stored
    assert default["rows"][0][1] == []                                       # and no open_problem_in is claimed
    asked = cypher.unaddressed_questions(g, min_confidence="0.7")
    assert asked["rows"] == []                                               # a proposal at 0.9 addresses it
    higher = cypher.unaddressed_questions(g, min_confidence="0.95")
    assert [r[0]["slug"] for r in higher["rows"]] == ["q"]                   # below the bar it does not count


def test_paths_use_proposals_only_when_asked(tmp_path):
    write(str(tmp_path), [row("a", "b", "uses", 0.9)])
    g = graph()
    cypher.add_proposed(g, CONFIG, str(tmp_path))
    assert cypher.shortest_path(g, "a", "b")["rows"] == []
    assert cypher.shortest_path(g, "a", "b", min_confidence=0.8)["rows"][0][1] == 1
    assert [r[0]["slug"] for r in cypher.neighbourhood(g, "a")["rows"]] == []
    assert [r[0]["slug"] for r in cypher.neighbourhood(g, "a", min_confidence="0.5")["rows"]] == ["b"]


def test_a_bad_confidence_is_a_query_error(tmp_path):
    g = graph()
    with pytest.raises(cypher.QueryError):
        cypher.run_named("neighbourhood", {"slug": "a", "min_confidence": "high"}, graph=g, config=CONFIG)


@pytest.fixture
def served(tmp_path, monkeypatch):
    """current_graph() with a stubbed snapshot, the flag settable, and the kb root a temp folder."""
    snap = {"etag": "e1", "nodes": [{"id": s, "title": s, "type": "idea", "layer": "concept"} for s in "ab"], "links": []}
    import kb_distillery.services.graph as sg
    state = {"on": True}
    monkeypatch.setattr(sg, "build_graph_snapshot", lambda *a, **k: snap)
    monkeypatch.setattr(sg, "relations_on", lambda: state["on"])
    monkeypatch.setattr(paths, "ROOT", str(tmp_path))
    monkeypatch.setattr(cypher, "edge_config", lambda cfg=None: CONFIG)
    cypher._cache.update(etag=None, graph=None)
    return state, snap


def test_current_graph_carries_proposals_with_the_flag_and_follows_the_file(tmp_path, served):
    state, snap = served
    write(str(tmp_path), [row("a", "b", "uses", 0.9)])
    g = cypher.current_graph()
    assert any(d.get("origin") == "proposed" for _, _, d in g.edges(data=True))
    write(str(tmp_path), [row("a", "b", "uses", 0.9), row("b", "a", "extends", 0.5)])
    assert sum(1 for _, _, d in cypher.current_graph().edges(data=True) if d.get("origin") == "proposed") == 2


def test_with_the_flag_off_nothing_changes(tmp_path, served):
    state, snap = served
    state["on"] = False
    write(str(tmp_path), [row("a", "b", "uses", 0.9)])
    assert not any(d.get("origin") == "proposed" for _, _, d in cypher.current_graph().edges(data=True))
    assert "proposed" not in snap and "relations" not in snap               # the published snapshot never carries them

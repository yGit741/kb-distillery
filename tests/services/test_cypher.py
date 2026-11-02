"""kb_distillery.services.cypher: snapshot → graph, the supported-subset check, query runs and the named queries."""
import json

import pytest

from kb_distillery.services import cypher

SNAP = {
    "etag": "t",
    "nodes": [
        {"id": "noise-stability", "title": "Noise stability", "type": "idea", "layer": "concept"},
        {"id": "fourier-analysis", "title": "Fourier analysis", "type": "idea", "layer": "concept"},
        {"id": "influence", "title": "Influence", "type": "idea", "layer": "concept"},
        {"id": "kalai-2002", "title": "Kalai 2002", "type": "paper", "layer": "source", "depth": "full", "year": 2002},
        {"id": "blog-kkl", "title": "KKL post", "type": "blog-post", "layer": "source", "depth": "easy"},
        {"id": "q-sharp", "title": "Is KKL sharp?", "type": "question", "layer": "concept"},
        {"id": "q-open", "title": "Open one", "type": "question", "layer": "concept"},
    ],
    "links": [
        {"source": "kalai-2002", "target": "noise-stability", "kind": "wikilink"},
        {"source": "kalai-2002", "target": "fourier-analysis", "kind": "related"},
        {"source": "blog-kkl", "target": "influence", "kind": "wikilink"},
        {"source": "blog-kkl", "target": "fourier-analysis", "kind": "wikilink"},
        {"source": "noise-stability", "target": "fourier-analysis", "kind": "wikilink"},
        {"source": "influence", "target": "fourier-analysis", "kind": "wikilink"},
        {"source": "kalai-2002", "target": "missing-page", "kind": "wikilink"},
    ],
    "concept_links": [{"source": "fourier-analysis", "target": "influence", "shared": 1}],
}


@pytest.fixture
def g():
    graph = cypher.to_graph(SNAP)
    # typed relations arrive with the schema PR; add two by hand to exercise the named queries
    cypher.add_edge(graph, "q-sharp", "influence", "OPEN_PROBLEM_IN")
    cypher.add_edge(graph, "q-open", "noise-stability", "OPEN_PROBLEM_IN")
    cypher.add_edge(graph, "kalai-2002", "q-sharp", "ADDRESSES")
    return graph


@pytest.fixture(autouse=True)
def rejected_log(tmp_path, monkeypatch):
    path = tmp_path / "rejected.jsonl"
    monkeypatch.setattr(cypher, "REJECTED_LOG", str(path))
    return path


def test_to_graph_labels_and_kinds(g):
    assert g.nodes["blog-kkl"]["__labels__"] == {"BlogPost", "Source"}
    assert g.nodes["noise-stability"]["__labels__"] == {"Idea", "Concept"}
    assert cypher.kinds(g, "kalai-2002", "fourier-analysis") == {"MENTIONS"}       # related → MENTIONS
    assert [d["via"] for d in g["kalai-2002"]["fourier-analysis"].values()] == ["related"]
    assert "missing-page" not in g                                                # dangling links dropped
    assert "SHARES_SOURCE" in cypher.kinds(g, "fourier-analysis", "influence")    # symmetric: both ways
    assert "SHARES_SOURCE" in cypher.kinds(g, "influence", "fourier-analysis")
    cypher.add_edge(g, "kalai-2002", "fourier-analysis", "MENTIONS")              # one edge per (pair, kind)
    assert len(g["kalai-2002"]["fourier-analysis"]) == 1


def test_run_typed_match_and_labels(g):
    t = cypher.run('MATCH (s:Source)-[:MENTIONS]->(i:Idea) WHERE i.slug = "fourier-analysis" RETURN s.slug', graph=g)
    assert t["columns"] == ["s.slug"]
    assert sorted(r[0] for r in t["rows"]) == ["blog-kkl", "kalai-2002"]
    t = cypher.run("MATCH (b:BlogPost) RETURN b.slug", graph=g)
    assert t["rows"] == [["blog-kkl"]]


def test_run_two_kinds_on_one_pair(g):
    t = cypher.run('MATCH (a)-[r]->(b) WHERE a.slug = "fourier-analysis" AND b.slug = "influence" RETURN r.kind', graph=g)
    assert [r[0] for r in t["rows"]] == ["SHARES_SOURCE"]
    t = cypher.run('MATCH (a)-[r]->(b) WHERE a.slug = "influence" AND b.slug = "fourier-analysis" RETURN r.kind', graph=g)
    assert sorted(r[0] for r in t["rows"]) == ["MENTIONS", "SHARES_SOURCE"]


def test_run_normalizes_single_quotes_and_bang_equals(g):
    t = cypher.run("MATCH (a:Paper)-[:MENTIONS]->(b) WHERE b.slug != 'noise-stability' RETURN b.slug", graph=g)
    assert t["rows"] == [["fourier-analysis"]]


def test_run_returns_jsonable_nodes_and_truncates(g):
    t = cypher.run("MATCH (n:Idea) RETURN n", graph=g, limit=2)
    assert t["row_count"] == 2 and t["truncated"] is True
    node = t["rows"][0][0]
    assert isinstance(node["labels"], list) and "__labels__" not in node
    json.dumps(t)


@pytest.mark.parametrize("query, says", [
    ('CREATE (n:Idea {slug:"x"})', "read-only"),
    ("MATCH (n) DETACH DELETE n", "read-only"),
    ("MATCH (n) SET n.title = 1 RETURN n", "read-only"),
    ("MATCH (q:Question) OPTIONAL MATCH (p)-[:ADDRESSES]->(q) RETURN q", "OPTIONAL"),
    ("MATCH p = shortestPath((a)-[*]-(b)) RETURN p", "shortest-path"),
    ("MATCH (q:Question) WHERE NOT ()-[:ADDRESSES]->(q) RETURN q", "named query"),
    ("MATCH (m) WHERE COUNT { (m)-->() } = 1 RETURN m", "subqueries"),
    ('MATCH (a)-[r]-(b) WHERE a.slug = "x" RETURN b', "neighbourhood"),
    ("MATCH (a)--(b) RETURN b", "undirected"),
    ("RETURN 1", "MATCH"),
    ("", "empty"),
])
def test_check_rejects_with_hint(query, says, rejected_log, g):
    with pytest.raises(cypher.QueryError, match=says):
        cypher.run(query, graph=g)
    if query:
        logged = [json.loads(line) for line in rejected_log.read_text().splitlines()]
        assert logged[-1]["query"] == query


def test_check_ignores_keywords_inside_strings_and_allows_directed_arrows():
    assert cypher.check('MATCH (n) WHERE n.title CONTAINS "CREATE NOT (x) a--b" RETURN n')
    assert cypher.check("MATCH (a)-->(b) RETURN b") and cypher.check("MATCH (a)<--(b) RETURN b")


def test_parser_errors_become_query_errors(g, rejected_log):
    with pytest.raises(cypher.QueryError, match="could not run"):
        cypher.run("MATCH (a RETURN a", graph=g)
    assert json.loads(rejected_log.read_text().splitlines()[-1])["query"] == "MATCH (a RETURN a"


def test_gaps(g):
    t = cypher.gaps(g, min_shared=1)
    pairs = {(r[0]["slug"], r[1]["slug"]) for r in t["rows"]}
    assert ("influence", "noise-stability") in pairs          # share fourier-analysis, no link
    assert all(not g.has_edge(a, b) and not g.has_edge(b, a) for a, b in pairs)


def test_unaddressed_questions(g):
    t = cypher.unaddressed_questions(g)
    assert [(r[0]["slug"], r[1]) for r in t["rows"]] == [("q-open", ["noise-stability"])]


def test_shortest_path_and_neighbourhood(g):
    t = cypher.shortest_path(g, "blog-kkl", "noise-stability")
    path, length = t["rows"][0]
    assert path[0]["slug"] == "blog-kkl" and path[-1]["slug"] == "noise-stability" and length == 2
    hood = cypher.neighbourhood(g, "fourier-analysis", hops=1)
    assert {r[0]["slug"] for r in hood["rows"]} == {"kalai-2002", "blog-kkl", "noise-stability", "influence"}
    with pytest.raises(cypher.QueryError, match="no page"):
        cypher.neighbourhood(g, "nope")


def test_run_named_params(g):
    assert cypher.run_named("gaps", {"min_shared": "1"}, graph=g)["row_count"] >= 1
    with pytest.raises(cypher.QueryError, match="unknown named query"):
        cypher.run_named("bogus", graph=g)
    with pytest.raises(cypher.QueryError, match="takes"):
        cypher.run_named("gaps", {"bad": "1"}, graph=g)
    with pytest.raises(cypher.QueryError, match="bad parameter"):
        cypher.run_named("gaps", {"min_shared": "many"}, graph=g)
    assert {q["name"] for q in cypher.named_list()} == set(cypher.available())


def _cfg(edges):
    from kb_distillery import kbconfig
    return kbconfig.KbConfig("t", "T", "/x", "/x/kb.toml", (1, 6), None, {"edges": edges})


LINKED = {"nodes": [{"id": "a", "type": "idea", "layer": "concept"}, {"id": "b", "type": "idea", "layer": "concept"}],
          "links": [{"source": "a", "target": "b", "kind": "addresses"}], "concept_links": []}


def test_edge_config_defaults_are_what_the_graph_always_had():
    c = cypher.edge_config(_cfg({}))
    assert c["labels"] == {"wikilink": "MENTIONS", "related": "MENTIONS"}
    assert c["symmetric"] == {"SHARES_SOURCE", "COLLABORATES_WITH", "SIMILAR_TO"}   # the symmetric computed kinds
    assert c["types"] == [] and c["note_required"] == set()                        # no stored kind unless declared


def test_a_kb_extends_the_edge_kinds_in_its_edges_table():
    c = cypher.edge_config(_cfg({"labels": {"addresses": "addresses"}, "symmetric": ["pairs"]}))
    assert c["labels"] == {"wikilink": "MENTIONS", "related": "MENTIONS", "addresses": "ADDRESSES"}
    assert c["symmetric"] == {"SHARES_SOURCE", "COLLABORATES_WITH", "SIMILAR_TO", "PAIRS"}
    junk = cypher.edge_config(_cfg({"labels": "nope", "symmetric": "nope"}))      # malformed tables never break a query
    assert junk == cypher.edge_config(_cfg({}))


def test_snapshot_kinds_become_labels_and_symmetric_ones_go_both_ways():
    one_way = cypher.to_graph(LINKED, cypher.edge_config(_cfg({"labels": {"addresses": "ADDRESSES"}})))
    assert cypher.kinds(one_way, "a", "b") == {"ADDRESSES"} and cypher.kinds(one_way, "b", "a") == set()
    both = cypher.to_graph(LINKED, cypher.edge_config(_cfg({"labels": {"addresses": "PAIRS"}, "symmetric": ["pairs"]})))
    assert cypher.kinds(both, "b", "a") == {"PAIRS"}


def test_unaddressed_questions_is_offered_only_when_the_kb_has_its_edge_kinds(g):
    default = cypher.edge_config(_cfg({}))
    assert "unaddressed-questions" not in cypher.available(default)
    assert "unaddressed-questions" not in {q["name"] for q in cypher.named_list(default)}
    with pytest.raises(cypher.QueryError, match="needs the edge kinds ADDRESSES, OPEN_PROBLEM_IN"):
        cypher.run_named("unaddressed-questions", graph=g, config=default)
    declared = cypher.edge_config(_cfg({"labels": {"addresses": "ADDRESSES", "open-in": "OPEN_PROBLEM_IN"}}))
    assert "unaddressed-questions" in cypher.available(declared)
    assert cypher.run_named("unaddressed-questions", graph=g, config=declared)["row_count"] == 1


@pytest.mark.flag("graph-relations", False)
def test_flag_off_keeps_link_labels_and_ignores_declared_relation_types():
    c = cypher.edge_config(_cfg({"labels": {"open-in": "open-problem-in"}, "types": ["addresses", "open-problem-in"]}))
    assert c["labels"]["open-in"] == "OPEN-PROBLEM-IN"                             # spelled as it always was
    assert "unaddressed-questions" not in cypher.available(c)


@pytest.mark.flag("graph-relations", True)
def test_flag_on_declared_relation_types_offer_their_named_queries():
    c = cypher.edge_config(_cfg({"types": ["Addresses", "open_problem_in"], "symmetric": ["contradicts"],
                                 "note_required": ["contradicts", "addresses"]}))
    assert c["types"] == ["addresses", "open-problem-in"] and c["note_required"] == {"addresses"}
    assert "CONTRADICTS" in c["symmetric"]
    assert "unaddressed-questions" in cypher.available(c)

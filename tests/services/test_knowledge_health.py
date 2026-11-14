"""Knowledge health groups on a small hand-built graph."""
from kb_distillery.services import knowledge_health as kh


def node(i, layer, depth=""):
    return {"id": i, "title": i.upper(), "layer": layer, "type": "x", "depth": depth}


def link(a, b):
    return {"source": a, "target": b, "kind": "wikilink"}


def snap(nodes, links):
    return {"nodes": nodes, "links": links}


def test_undigested_and_orphans():
    s = snap([node("s1", "source", "listed"), node("s2", "source", "full"), node("c1", "concept")], [link("s2", "c1")])
    r = kh.compute(s)
    assert [p["id"] for p in r["undigested_sources"]["items"]] == ["s1"]
    assert [p["id"] for p in r["orphans"]["items"]] == ["s1"]
    assert r["orphans"]["count"] == 1


def test_single_source_concepts():
    s = snap([node("s1", "source"), node("s2", "source"), node("c1", "concept"), node("c2", "concept"), node("c3", "concept")],
             [link("s1", "c1"), link("c1", "s1"), link("s1", "c2"), link("s2", "c2")])
    r = kh.compute(s)
    items = r["single_source_concepts"]["items"]
    assert [p["id"] for p in items] == ["c1"] and items[0]["source"] == "s1"   # c3 has none, c2 has two


def base(extra_links=()):
    srcs = [node(f"s{i}", "source") for i in range(1, 5)]
    cons = [node("a", "concept"), node("b", "concept"), node("c", "concept")]
    links = [link(s, "a") for s in ("s1", "s2", "s3")] + [link(s, "b") for s in ("s1", "s2")] + [link("s3", "c"), link("s4", "c")]
    return snap(srcs + cons, links + list(extra_links))


def test_missing_links_jaccard_threshold():
    r = kh.compute(base(), min_jaccard=0.34)
    pairs = [(m["a"], m["b"], m["score"], m["shared"]) for m in r["missing_links"]["items"]]
    assert pairs == [("a", "b", 0.6667, ["s1", "s2"])]        # a,c share only s3: one shared, below MIN_SHARED
    assert kh.compute(base(), min_jaccard=0.67)["missing_links"]["count"] == 0
    assert kh.compute(base(), min_jaccard=2 / 3)["missing_links"]["count"] == 1   # at the threshold is kept


def test_missing_links_skips_direct_link_either_direction():
    assert kh.compute(base([link("b", "a")]))["missing_links"]["count"] == 0


def test_unsupported_links():
    s = snap([node("s1", "source"), node("s2", "source"), node("a", "concept"), node("b", "concept"), node("c", "concept")],
             [link("s1", "a"), link("s2", "b"), link("a", "b"), link("s1", "c"), link("a", "c")])
    r = kh.compute(s)
    assert [(p["a"], p["b"]) for p in r["unsupported_links"]["items"]] == [("a", "b")]   # a-c share s1


def test_hubs_rule():
    nodes = [node("h", "concept")] + [node(f"p{i}", "source") for i in range(30)]
    r = kh.compute(snap(nodes, [link(f"p{i}", "h") for i in range(30)]))
    assert [p["id"] for p in r["hubs"]["items"]] == ["h"] and r["hubs"]["items"][0]["degree"] == 30
    small = kh.compute(snap(nodes[:6], [link(f"p{i}", "h") for i in range(5)]))
    assert small["hubs"]["count"] == 0                           # above 3 sigma but under the minimum degree 10


def test_cap_keeps_full_count():
    nodes = [node(f"s{i}", "source", "listed") for i in range(5)]
    r = kh.compute(snap(nodes, []), limit=2)
    assert r["undigested_sources"]["count"] == 5 and len(r["undigested_sources"]["items"]) == 2
    assert kh.compute(snap(nodes, []), limit=0)["orphans"] == {"count": 5, "items": []}


def test_empty_graph():
    r = kh.compute(snap([], []))
    assert all(g == {"count": 0, "items": []} for g in r.values())

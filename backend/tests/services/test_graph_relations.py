"""Flag `graph-relations`: the snapshot's `relations` list, its edge types in the Cypher service, and both flag
states. Runs on a throwaway knowledge base (viewed read-only through kb.services.kbview), never a real vault."""
import pytest

from kb.core import schema
from kb.services import cypher
from kb.services.graph import build_graph_snapshot, merge_snapshots
from kb.services.kbview import KbView

KB_TOML = """[kb]
id = "rel"
name = "Relations test"
schema_version = "{v}"

[edges]
types = ["addresses", "open-problem-in", "contradicts", "extends"]
symmetric = ["contradicts"]
note_required = ["contradicts"]
"""

PAGES = {
    "margin": "---\ntype: idea\nrelations:\n  - to: sgd\n    kind: contradicts\n    note: different regime\n"
              "---\n# Margin\nSee [[sgd]].\n",
    "sgd": "---\ntype: idea\n---\n# SGD\n",
    "q-why": "---\ntype: question\nrelations:\n  - to: margin\n    kind: open-problem-in\n---\n# Why does SGD generalize?\n",
    "q-done": "---\ntype: question\n---\n# A settled one\n",
    "paper-x": "---\ntype: paper\nrelations:\n  - to: q-done\n    kind: addresses\n---\n# X\nUses [[margin]].\n",
}


@pytest.fixture
def view(tmp_path):
    root = tmp_path / "rel"
    (root / "wiki").mkdir(parents=True)
    (root / "kb.toml").write_text(KB_TOML.format(v=".".join(map(str, schema.SCHEMA_VERSION))))
    for slug, text in PAGES.items():
        (root / "wiki" / f"{slug}.md").write_text(text)
    return KbView(id="rel", name="Relations test", root=str(root), types=schema._T, active=False)


@pytest.mark.flag("graph-relations", False)
def test_flag_off_snapshot_is_what_it_always_was(view):
    snap = build_graph_snapshot(view=view)
    assert "relations" not in snap
    assert {(l["source"], l["target"], l["kind"]) for l in snap["links"]} == {
        ("margin", "sgd", "wikilink"), ("paper-x", "margin", "wikilink")}
    assert all(set(l) == {"source", "target", "kind"} for l in snap["links"])
    g = cypher.to_graph(snap)
    assert {d["kind"] for _, _, d in g.edges(data=True)} == {"MENTIONS"}


@pytest.mark.flag("graph-relations", True)
def test_flag_on_adds_relations_and_leaves_links_alone(view):
    snap = build_graph_snapshot(view=view)
    assert {(l["source"], l["target"], l["kind"]) for l in snap["links"]} == {
        ("margin", "sgd", "wikilink"), ("paper-x", "margin", "wikilink")}          # the canvas draws the same
    rel = {(r["source"], r["target"], r["kind"]): r for r in snap["relations"]}
    assert rel[("margin", "sgd", "contradicts")]["origin"] == "stored"
    assert rel[("margin", "sgd", "contradicts")]["note"] == "different regime"
    assert rel[("margin", "sgd", "mentions")]["origin"] == "computed"
    assert ("paper-x", "q-done", "addresses") in rel and ("q-why", "margin", "open-problem-in") in rel


@pytest.mark.flag("graph-relations", True)
def test_flag_on_cypher_sees_the_new_edge_types(view):
    from kb import kbconfig
    snap = build_graph_snapshot(view=view)
    config = cypher.edge_config(kbconfig.load_dir(view.root, "rel", strict=False))
    g = cypher.to_graph(snap, config)
    assert cypher.kinds(g, "sgd", "margin") == {"CONTRADICTS"}                      # declared symmetric
    assert cypher.kinds(g, "margin", "sgd") == {"MENTIONS", "CONTRADICTS"}
    rows = cypher.run('MATCH (p)-[r:ADDRESSES]->(q:Question) RETURN p.slug, q.slug', graph=g)["rows"]
    assert rows == [["paper-x", "q-done"]]
    assert "unaddressed-questions" in cypher.available(config)
    t = cypher.run_named("unaddressed-questions", graph=g, config=config)
    assert [(r[0]["slug"], r[1]) for r in t["rows"]] == [("q-why", ["margin"])]
    data = next(d for d in g["margin"]["sgd"].values() if d["kind"] == "CONTRADICTS")
    assert data["origin"] == "stored" and data["note"] == "different regime"


@pytest.mark.flag("graph-relations", True)
def test_merged_snapshots_namespace_relations(view):
    other = KbView(id="rel2", name="Other", root=view.root, types=schema._T, active=False)
    merged = merge_snapshots([(view, build_graph_snapshot(view=view)), (other, build_graph_snapshot(view=view))])
    ids = {n["id"] for n in merged["nodes"]}
    assert merged["relations"] and all(r["source"] in ids and r["target"] in ids for r in merged["relations"])


@pytest.mark.flag("graph-relations", False)
def test_merged_snapshots_without_the_flag_have_no_relations(view):
    assert "relations" not in merge_snapshots([(view, build_graph_snapshot(view=view))])


@pytest.mark.parametrize("on", [False, True])
def test_cypher_cache_follows_a_flag_flip(on, monkeypatch):
    """current_graph rebuilds when the flag flips even though the pages (and so the etag) did not change."""
    from kb.flags.registry import override

    monkeypatch.setattr(cypher, "_cache", {"etag": None, "graph": None})
    with override("graph-relations", not on):
        first = cypher.current_graph()
    with override("graph-relations", on):
        assert cypher.current_graph() is not first

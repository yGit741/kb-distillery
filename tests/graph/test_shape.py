"""The style grammar of a graph view: pure parsing, hints on rejection, round trip through the canonical text."""
import pytest

from kb_distillery.graph import shape
from kb_distillery.graph.shape import ShapeError, StyleSpec, Target, format_style, parse_style


def test_every_clause_kind():
    s = parse_style("group by type; colour by degree; size by year; layout radial; hide Paper; hide MENTIONS; label title")
    assert s == StyleSpec(group_by=Target(by="prop", name="type"), colour_by=Target(by="degree"),
                          size_by=Target(by="prop", name="year"), layout="radial", hide_labels=["Paper"],
                          hide_edge_kinds=["MENTIONS"], label="title")


def test_separators_case_and_spelling():
    s = parse_style("Color BY label\nGROUP by edge-kind\nsize by degree;")
    assert s.colour_by == Target(by="label") and s.group_by == Target(by="edge-kind")
    assert s.size_by == Target(by="degree")
    assert parse_style("colour by type.").colour_by.name == "type"
    assert parse_style("group by edge kind").group_by == Target(by="edge-kind")
    assert parse_style("group by area").group_by.name == "areas"


def test_empty_text_is_an_empty_spec():
    assert parse_style("").is_empty() and parse_style(" ; \n").is_empty()
    assert not parse_style("layout grid").is_empty()


def test_last_clause_wins_and_hide_accumulates():
    s = parse_style("layout grid; layout force; hide Paper; hide paper, Idea; hide edge shares source")
    assert s.layout == "force" and s.hide_labels == ["Paper", "Idea"] and s.hide_edge_kinds == ["SHARES_SOURCE"]


def test_hide_disambiguation():
    assert parse_style("hide label Open Problem").hide_labels == ["OpenProblem"]
    assert parse_style("hide edge mentions").hide_edge_kinds == ["MENTIONS"]
    assert parse_style("hide edge-kind similar-to").hide_edge_kinds == ["SIMILAR_TO"]
    assert parse_style("hide mentions").hide_labels == ["Mentions"]      # bare lower case is a node label


@pytest.mark.parametrize("text, hint", [
    ("spin the nodes", "unknown style clause `spin the nodes`"),
    ("group type", "unknown style clause"),
    ("group by", "name what to use"),
    ("group by degree", "`degree` is not allowed here"),
    ("colour by edge-kind", "`edge-kind` is not allowed here"),
    ("size by label", "`label` is not allowed here"),
    ("colour by flavour", "unknown property `flavour`"),
    ("layout spiral", "layout is one of force, radial, grid, timeline"),
    ("layout", "layout is one of"),
    ("hide", "name a node label"),
    ("hide label", "nothing to hide"),
    ("label title year", "label takes one node property"),
    ("label colour", "unknown property `colour`"),
])
def test_rejections_carry_a_hint(text, hint):
    with pytest.raises(ShapeError) as e:
        parse_style(text)
    assert hint in str(e.value)
    assert "Style clauses: group by" in str(e.value)       # every rejection shows the grammar
    assert e.value.status == 422


def test_format_round_trips():
    for text in ("group by label; colour by type; size by degree; layout timeline; hide label Paper; hide edge MENTIONS; label slug",
                 "group by edge-kind", "layout grid", ""):
        s = parse_style(text)
        assert parse_style(format_style(s)) == s
    assert format_style(parse_style("color by degree;hide Paper")) == "colour by degree; hide label Paper"


def test_spec_is_json():
    assert parse_style("layout grid; hide MENTIONS").model_dump() == {
        "group_by": None, "colour_by": None, "size_by": None, "layout": "grid", "hide_labels": [],
        "hide_edge_kinds": ["MENTIONS"], "label": None}


def test_split_cypher_style_marker():
    q = "MATCH (p:Paper) RETURN p.slug"
    assert shape.split_cypher(q) == (q, "")
    assert shape.split_cypher(q + "\n-- group by type; layout grid") == (q, "group by type; layout grid")
    assert shape.split_cypher(q + "\nSTYLE: colour by degree\nhide Idea") == (q, "colour by degree\nhide Idea")
    multi = "MATCH (p:Paper)\n  -[:MENTIONS]->(i:Idea)\nRETURN p.slug\n--layout grid"
    assert shape.split_cypher(multi)[1] == "layout grid"
    arrow = "MATCH (p:Paper)\n-->(i:Idea)\nRETURN p.slug"
    assert shape.split_cypher(arrow) == (arrow, "")           # `-->` at a line start is an arrow, not a marker


def test_is_cypher():
    assert shape.is_cypher("  match (n) return n.slug") and shape.is_cypher("MATCH(n)")
    assert not shape.is_cypher("matches of the year") and not shape.is_cypher("show papers")

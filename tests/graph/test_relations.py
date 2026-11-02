"""kb_distillery.graph.relations: the `relations:` block parser and every computed kind (pure, on in-memory pages)."""
import sqlite3

import numpy as np
import pytest

from kb_distillery.graph import relations as R
from kb_distillery.lint.lint import parse_frontmatter

PAGE = """---
type: idea
area: [learning-theory]
relations:
  - to: "[[implicit-bias]]"
    kind: extends
    note: "the margin argument: carries over # not a comment"
  - to: q-open
    kind: Open Problem In
  - kind: uses
related: [margin]
---
# Margin
body with [[implicit-bias]]
"""

CONFIG = {"types": ["addresses", "contradicts", "extends", "open-problem-in", "student-of", "uses"],
          "note_required": {"contradicts"}}


def _pages(spec):
    """{slug: (rel, fm, text)} from {slug: text}, frontmatter by the vault's own flat parser."""
    return {s: (f"wiki/{s}.md", parse_frontmatter(t), t) for s, t in spec.items()}


def _page(fm_lines, body=""):
    return "---\n" + "\n".join(fm_lines) + "\n---\n# T\n" + body + "\n"


def test_parse_reads_only_the_relations_block():
    rels = R.parse_relations(PAGE)
    assert rels == [
        {"to": "implicit-bias", "kind": "extends", "note": "the margin argument: carries over # not a comment"},
        {"to": "q-open", "kind": "open-problem-in", "note": ""},
    ]                                                   # an item without `to` is skipped
    assert R.relations_block(PAGE).splitlines()[-1] == "  - kind: uses"   # stops at the next key


def test_a_relation_target_may_be_a_page_path():
    text = _page(["type: idea", "relations:", "  - to: implicit-bias.md", "    kind: extends", "  - to: q-open", "    kind: uses"])
    assert [r["to"] for r in R.parse_relations(text)] == ["implicit-bias", "q-open"]


def test_flat_frontmatter_parser_is_unchanged_by_a_relations_block():
    fm = parse_frontmatter(PAGE)
    assert fm == {"type": "idea", "area": ["learning-theory"], "relations": "", "related": ["margin"]}


def test_round_trip():
    rels = [{"to": "a", "kind": "extends", "note": 'says "why": it matters'}, {"to": "b", "kind": "uses", "note": ""}]
    block = R.format_relations(rels)
    assert R.parse_relations("---\ntype: idea\n" + block + "\n---\n# x\n") == rels
    assert R.format_relations([]) == ""


@pytest.mark.parametrize("text", ["# no frontmatter", "---\ntype: idea\n---\n", "---\nrelations: [\n---\n",
                                  "---\nrelations: nope\n---\n", "---\nrelations:\n  - just a string\n---\n"])
def test_no_or_bad_block_degrades_to_nothing(text):
    assert R.parse_relations(text) == []


def test_labels_and_kind_names():
    assert R.edge_label("open-problem-in") == "OPEN_PROBLEM_IN"
    assert R.edge_label("shares-source") == "SHARES_SOURCE"
    assert R.kind_name("Open_Problem In") == "open-problem-in"


def test_stored_edges_keep_declared_kinds_and_report_the_rest():
    pages = _pages({
        "margin": _page(["type: idea", "relations:", "  - to: implicit-bias", "    kind: extends",
                         "  - to: implicit-bias", "    kind: contradicts",          # note required, missing
                         "  - to: ghost", "    kind: uses",                          # no such page
                         "  - to: implicit-bias", "    kind: rhymes-with"]),         # not declared
        "implicit-bias": _page(["type: idea"]),
    })
    assert R.stored_edges(pages, CONFIG) == [
        {"source": "margin", "target": "implicit-bias", "kind": "extends", "origin": "stored", "note": "", "weight": 1.0}]
    probs = R.problems(pages, CONFIG)
    assert len(probs) == 3 and any("needs a note" in p for p in probs) and any("rhymes-with" in p for p in probs)
    assert R.stored_edges(pages, {"types": [], "note_required": set()}) == []     # nothing declared, nothing kept


def _kinds(edges, kind):
    return {(e["source"], e["target"]) for e in edges if e["kind"] == kind}


def test_mentions_and_shares_source_come_from_the_snapshot():
    links = [{"source": "p", "target": "a", "kind": "wikilink"}, {"source": "p", "target": "b", "kind": "related"},
             {"source": "part", "target": "book", "kind": "book"}]
    out = R.build({}, [], links, [{"source": "a", "target": "b", "shared": 2}], CONFIG)
    assert _kinds(out, "mentions") == {("p", "a"), ("p", "b")}                 # the book link is not a mention
    (share,) = [e for e in out if e["kind"] == "shares-source"]
    assert share["weight"] == 2.0 and share["note"] == "2 shared sources" and share["origin"] == "computed"


def test_person_edges_only_when_the_data_exists():
    pages = _pages({"jane": _page(["type: person", "advisors: [bob]", "students: [[[carl]], ghost]"]),
                    "bob": _page(["type: person"]), "carl": _page(["type: person"])})
    out = R.person_edges(pages)
    assert _kinds(out, "student-of") == {("jane", "bob"), ("carl", "jane")}
    assert _kinds(out, "advisor-of") == {("bob", "jane"), ("jane", "carl")}
    assert R.person_edges(_pages({"bob": _page(["type: person"])})) == []


def _authored():
    pages = _pages({
        "jane-doe": _page(["type: person"]),
        "bob-roe": _page(["type: person"]),
        "paper-1": _page(["type: paper", "authors: [Jane Doe, B. Roe, Someone Else]"]),
        "paper-2": _page(["type: paper", "authors: [jane  doe, Bob Roe]"], "cites [[jane-doe]]"),
    })
    nodes = [{"id": s, "title": t, "type": fm["type"], "layer": "source" if fm["type"] == "paper" else "concept"}
             for s, t, fm in [(s, s, v[1]) for s, v in pages.items()]]
    return pages, nodes


def test_names_come_from_slugs_titles_and_aliases(tmp_path):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "aliases.tsv").write_text("# mention\tslug\nB. Roe\tbob-roe\nmargin\tsome-idea\n")
    pages, nodes = _authored()
    names = R.person_names(pages, {"jane-doe": "Jane Q. Doe"}, str(tmp_path))
    assert names["jane doe"] == "jane-doe" and names["jane q doe"] == "jane-doe" and names["b roe"] == "bob-roe"
    assert "margin" not in names                       # an alias to a non-person page is not a name


def test_name_match_never_doubles_a_mention_and_collaborators_count_shared_sources(tmp_path):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "aliases.tsv").write_text("B. Roe\tbob-roe\n")
    pages, nodes = _authored()
    links = [{"source": "paper-2", "target": "jane-doe", "kind": "wikilink"}]
    out = R.build(pages, nodes, links, [], CONFIG, root=str(tmp_path))
    pairs = {(e["source"], e["target"], e["kind"]) for e in out}
    assert ("paper-2", "jane-doe", "mentions") in pairs
    assert ("paper-2", "jane-doe", "name-match") not in pairs                  # exclusion rule
    assert _kinds(out, "name-match") == {("paper-1", "jane-doe"), ("paper-1", "bob-roe"), ("paper-2", "bob-roe")}
    (collab,) = [e for e in out if e["kind"] == "collaborates-with"]
    assert (collab["source"], collab["target"], collab["weight"]) == ("bob-roe", "jane-doe", 2.0)


def _store(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE vectors(slug TEXT PRIMARY KEY, hash TEXT, model TEXT, dim INT, vec BLOB, at TEXT)")
    for slug, vec in rows:
        con.execute("INSERT INTO vectors VALUES (?,?,?,?,?,?)",
                    (slug, "h", "m", len(vec), np.asarray(vec, dtype=np.float32).tobytes(), ""))
    con.commit()
    con.close()


def test_similar_to_needs_the_vector_store(tmp_path):
    pages = _pages({s: _page(["type: idea"]) for s in ("a", "b", "c", "d")})
    assert R.similar_edges(pages, str(tmp_path)) == []                          # no store: omitted, no error
    (tmp_path / ".cache").mkdir()
    _store(str(tmp_path / ".cache" / "vectors.sqlite"),
           [("a", [1, 0, 0]), ("b", [0.95, 0.05, 0]), ("c", [0, 1, 0]), ("d", [np.nan, 1, 0]), ("gone", [1, 0, 0])])
    out = R.similar_edges(pages, str(tmp_path))
    assert [(e["source"], e["target"]) for e in out] == [("a", "b")]           # once per pair; NaN row and
    assert out[0]["kind"] == "similar-to" and 0.99 < out[0]["weight"] <= 1.0    # pages not in the wiki skipped


def test_stored_wins_over_a_computed_edge_with_the_same_key():
    pages = _pages({"jane": _page(["type: person", "advisors: [bob]", "relations:", "  - to: bob",
                                   "    kind: student-of", "    note: PhD 2019"]),
                    "bob": _page(["type: person"])})
    out = R.build(pages, [], [], [], CONFIG)
    (e,) = [e for e in out if e["kind"] == "student-of"]
    assert e["origin"] == "stored" and e["note"] == "PhD 2019"


def test_a_symmetric_kind_stated_from_both_pages_is_one_edge():
    rel = lambda to: ["relations:", f"  - to: {to}", "    kind: contradicts", f"    note: vs {to}"]
    pages = _pages({"b": _page(rel("a")), "a": _page(rel("b"))})
    config = {**CONFIG, "symmetric": {"contradicts"}}
    out = [e for e in R.build(pages, [], [], [], config) if e["kind"] == "contradicts"]
    assert [(e["source"], e["target"], e["note"]) for e in out] == [("a", "b", "vs b")]

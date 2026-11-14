"""kb_distillery.vault.links: page links `[Title](slug.md)`, the legacy wikilink regexes, convert / to_disk / link."""
from kb_distillery.vault import graph, links

TEXT = r"See [[alpha]], [[beta|Beta]], [[gamma#Intro]], [[ delta ]] and a table [[eps\|E]]."
MD = "See [Alpha](alpha.md), [the *B*](beta.md), [Gamma](gamma.md#intro), [esc \\[x\\]](delta.md) and ![img](eps.md) and [web](https://x.org/a.md) and [dir](wiki/zeta.md)."


def test_targets_strip_and_drop_label_and_anchor():
    assert links.targets(TEXT) == ["alpha", "beta", "gamma", "delta", "eps"]


def test_targets_read_page_links_and_wikilinks_in_order():
    assert links.targets(MD) == ["alpha", "beta", "gamma", "delta"]      # not an image, a url or a path
    assert links.targets("[[a]] then [b](b.md) then [[c|C]]") == ["a", "b", "c"]
    assert links.wikilink_targets("[[a]] then [b](b.md)") == ["a"]


def test_targets_handles_none_and_no_links():
    assert links.targets("") == []
    assert links.targets(None) == []


def test_full_pattern_groups():
    m = [(a, b) for a, b in links.WIKILINK.findall(TEXT)]
    assert m == [("alpha", ""), ("beta", "Beta"), ("gamma", ""), (" delta ", ""), ("eps", "E")]


def test_page_link_groups_and_unescape():
    got = [links.link_parts(m) for m in links.PAGE_LINK.finditer(MD)]
    assert got == [("Alpha", "alpha", ""), ("the *B*", "beta", ""), ("Gamma", "gamma", "intro"), ("esc [x]", "delta", "")]


def test_link_builder_uses_page_path_and_escapes():
    assert links.link("tensor-rank", "Tensor rank") == "[Tensor rank](tensor-rank.md)"
    assert links.link("tensor-rank") == "[tensor-rank](tensor-rank.md)"
    assert links.link("a", "Why [x] \\ y") == "[Why \\[x\\] \\ y](a.md)"     # a lone backslash is no escape
    assert links.link("a", "T", "Why it works") == "[T](a.md#why-it-works)"
    assert links.link("a", "two\n lines") == "[two lines](a.md)"
    m = links.PAGE_LINK.fullmatch(links.link("a", "Why [x] \\ y"))
    assert links.link_parts(m)[0] == "Why [x] \\ y"


def test_a_tex_label_keeps_one_backslash_and_every_label_round_trips():
    assert links.link("noise-operator", "Noise operator ($T_\\rho$)") == "[Noise operator ($T_\\rho$)](noise-operator.md)"
    for label in ["$T_\\rho$", "a\\\\b", "x\\", "c\\]", "\\[x", "[a] b"]:
        assert links.link_parts(links.PAGE_LINK.fullmatch(links.link("a", label)))[0] == label
    assert links.link_parts(links.PAGE_LINK.fullmatch("[$T_\\\\rho$](a.md)"))[0] == "$T_\\rho$"    # pages written before


def test_page_link_takes_the_title_from_titles():
    assert links.page_link("a", {"a": "A [1] title"}) == "[A 1 title](a.md)"
    assert links.page_link("a", {}) == "[a](a.md)"
    assert links.page_link("a", {"a": "T"}, label="L") == "[L](a.md)"
    assert links.page_link("a", {"a"}) == "[a](a.md)"                     # a plain set of slugs has no titles


def test_title_is_what_the_app_shows():
    assert links.title_of("---\ntype: x\n---\n\n# The *Title*\n", "s") == "The *Title*"
    assert links.title_of("no heading", "a-b") == "a b"
    assert links.shown_title("A [1] | b") == "A 1 b"


def test_convert_and_to_disk():
    titles = {"alpha": "Alpha", "beta": "Beta"}
    out = links.to_disk("x [[alpha]] y [[beta|b]] z [[gamma]] `[[alpha]]` w", titles)
    assert out == "x [Alpha](alpha.md) y [b](beta.md) z [[gamma]] `[[alpha]]` w"
    assert links.to_disk(links.to_disk("[[alpha]]", titles), titles) == "[Alpha](alpha.md)"      # idempotent


def test_to_llm_is_the_markdown_a_reader_sees():
    assert links.to_llm(MD) == MD


def test_protected_regions_are_not_prose():
    body = "a\n```\n[[x]]\n```\n`[[y]]` $[[z]]$ <!-- [[c]] -->\n[[ok]]\n## My notes\n[[mine]]\n"
    assert links.leftover_wikilinks(body) == ["[[ok]]"]


def test_a_wikilink_inside_a_markdown_links_text_is_left_alone():
    rs = links.Resolver({"a"}, {"a": "A"})
    text = "see [about [[a]] here](https://example.org/x) and [[a]]"
    assert links.convert(text, rs) == "see [about [[a]] here](https://example.org/x) and [A](a.md)"


def test_every_reader_follows_both_forms():
    """The one shared reading of links (links.targets): graph, health, lint, hubs, scopes and the relations block all see
    a wikilink (My notes) and a page link alike, so no edge is lost across the switch."""
    from kb_distillery.vault import health, hubs, scopes
    both = "see [[a]] and [B](b.md#h)"
    assert graph.outbound_links(both) == {"a", "b"}
    pages = {"a": ("wiki/a.md", {}, ""), "b": ("wiki/b.md", {}, ""), "c": ("wiki/c.md", {}, both)}
    assert health.compute_in_degree(pages) == {"a": 1, "b": 1, "c": 0}
    from kb_distillery.lint import lint
    assert lint.page_links.targets("## Papers\n- [[a]]\n- [B](b.md)") == ["a", "b"]
    row = "| 1 | T | `raw/x.pdf` | full | {} |"
    assert hubs.parse_contents("## Contents\n\n| # | Item | Raw | Status | Note |\n|--|--|--|--|--|\n" + row.format("[[a]]"))[0]["slug"] == "a"
    assert hubs.parse_contents("## Contents\n\n| # | Item | Raw | Status | Note |\n|--|--|--|--|--|\n" + row.format("[B](b.md)"))[0]["slug"] == "b"
    assert scopes.why_links("## Why\n\nBecause [[a]] and [B](b.md).\n\n## Members\n") == ["a", "b"]
    from kb_distillery.graph import relations
    assert [r["to"] for r in relations.parse_relations("---\nrelations:\n  - to: \"[[a]]\"\n    kind: uses\n  - to: b.md\n    kind: uses\n---\n")] == ["a", "b"]

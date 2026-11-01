"""kb_distillery.core.links: the single wikilink regex and the to_llm / to_disk seam."""
from kb_distillery.core import links

TEXT = r"See [[alpha]], [[beta|Beta]], [[gamma#Intro]], [[ delta ]] and a table [[eps\|E]]."


def test_targets_strip_and_drop_label_and_anchor():
    assert links.targets(TEXT) == ["alpha", "beta", "gamma", "delta", "eps"]


def test_targets_handles_none_and_no_links():
    assert links.targets("") == []
    assert links.targets(None) == []


def test_full_pattern_groups():
    m = [(a, b) for a, b in links.WIKILINK.findall(TEXT)]
    assert m == [("alpha", ""), ("beta", "Beta"), ("gamma", ""), (" delta ", ""), ("eps", "E")]


def test_round_trip_is_identity_for_now():
    assert links.to_disk(links.to_llm(TEXT)) == TEXT
    assert links.to_llm(links.to_disk(TEXT)) == TEXT


def test_old_module_names_still_resolve_to_the_shared_pattern():
    from kb_distillery.core import graph, health, hubs, scopes
    from kb_distillery.lint import lint
    assert graph.LINK is health.LINK is lint.LINK is links.WIKILINK_TARGET
    assert hubs._LINK is scopes._WIKILINK is links.WIKILINK_TARGET

"""A page link whose text is its slug chose no text: readers show the page title, as they did for a bare wikilink."""
from kb_distillery.services import pages

TITLES = {"book-x": "Tiny Book (2020)", "a": "Alpha"}


def test_slug_text_shows_the_title():
    assert pages._plain("Part of [book-x](book-x.md) here", TITLES) == "Part of Tiny Book (2020) here"
    assert pages._plain("[[book-x]]", TITLES) == "Tiny Book (2020)"          # same as the old bare wikilink


def test_chosen_text_is_kept_and_unknown_slug_falls_back():
    assert pages._plain("[my label](a.md) [ghost](ghost.md)", TITLES) == "my label ghost"

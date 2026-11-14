"""The pure text logic behind formula marks: which formula a mark link follows, and how resolve/apply rewrite the page."""
import pytest

from kb_distillery.services import marks

SHA = "0123456789ab"
LINK = "[!](mark:%s/p0188/3)" % SHA
LINK2 = "[!!](mark:%s/p0188/3)" % SHA


def at(text, mid=3):
    return marks.locate(text, SHA, 188, mid)


def test_inline_with_and_without_space():
    for text in (f"Then $x^2 + y$ {LINK} holds.", f"Then $x^2 + y${LINK} holds."):
        a = at(text)
        assert text[slice(*a["formula"])] == "$x^2 + y$" and a["form"] == "inline"
        assert marks.without_link(text, a) == "Then $x^2 + y$ holds."
        assert marks.with_replacement(text, a, "$x^2 - y$") == "Then $x^2 - y$ holds."


def test_level_does_not_matter_and_other_marks_are_left():
    text = f"$a$ {LINK2} and $b$ [!](mark:{SHA}/p0188/4)"
    a = at(text)
    assert text[slice(*a["formula"])] == "$a$"
    assert marks.without_link(text, a) == f"$a$ and $b$ [!](mark:{SHA}/p0188/4)"
    assert at(text, 9) is None


def test_block_with_link_on_its_own_line():
    text = f"Before.\n\n$$\n\\sum_i a_i\n$$\n{LINK}\n\nAfter.\n"
    a = at(text)
    assert a["form"] == "block" and text[slice(*a["formula"])] == "$$\n\\sum_i a_i\n$$"
    assert marks.without_link(text, a) == "Before.\n\n$$\n\\sum_i a_i\n$$\n\nAfter.\n"
    assert marks.with_replacement(text, a, "$$\n\\sum_j a_j\n$$") == "Before.\n\n$$\n\\sum_j a_j\n$$\n\nAfter.\n"


def test_escaped_dollar_inside_inline():
    text = f"Cost $\\$5 + x$ {LINK}."
    a = at(text)
    assert text[slice(*a["formula"])] == "$\\$5 + x$"


def test_no_formula_before_the_link():
    text = f"Plain words {LINK} here."
    a = at(text)
    assert a["formula"] is None
    assert marks.without_link(text, a) == "Plain words here."
    with pytest.raises(marks.MarkError):
        marks.with_replacement(text, a, "$x$")


def test_replacement_checks():
    assert marks.dollars_even("$a$ and \\$") and not marks.dollars_even("$a$ $")
    assert marks.check_replacement(" $y$ ", "inline") == "$y$"
    for bad, form in (("$y", "inline"), ("$$y$$", "inline"), ("$y$", "block"), ("", "inline")):
        with pytest.raises(marks.MarkError) as e:
            marks.check_replacement(bad, form)
        assert e.value.status == 422

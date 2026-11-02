"""Verifier checks that came out of reviewing 100 real MinerU pages (stray bars, accents the font draws on the base's
own line, spaced letters inside math, tags that are really inequalities, ...). Each test builds a small PDF with tests.pdfkit."""
from tests import pdfkit
import pytest

from kb_distillery.parse import layer, reconcile

from . import pdfs


def one_page(draw):
    doc = pdfkit.Doc()
    pg = doc.new_page()
    pdfs.frame(pg, 1)
    draw(pg)
    data = doc.tobytes()
    doc.close()
    return layer.read_pdf(data)[0]


def kinds(flags):
    return sorted(f.kind for f in flags)


# ---------------------------------------------------------------- vertical bars
def _bars(pg):
    pdfs.line(pg, 72, 120, [("t", "Then "), ("t", "|"), ("m", "x"), ("t", "| is small and "), ("m", "y"), ("t", " too.")])


def test_vertical_bar_is_counted_against_bar_glyphs():
    lay = one_page(_bars)
    assert reconcile.reconcile_page("Then $|x|$ is small and $y$ too.", lay) == []
    assert reconcile.reconcile_page("Then $\\left| x \\right|$ is small and $y$ too.", lay) == []
    assert reconcile.reconcile_page("Then $\\lvert x \\rvert$ is small and $y$ too.", lay) == []
    stray = reconcile.reconcile_page("Then $\\left| |x|$ is small and $y$ too.", lay)           # one bar too many
    assert kinds(stray) == ["invented-glyphs"] and "|" in stray[0].detail
    lost = reconcile.reconcile_page("Then $x$ is small and $y$ too.", lay)
    assert kinds(lost) == ["lost-glyphs"] and "|" in lost[0].detail


def test_bars_in_math_source_become_keys():
    assert [k for k in reconcile.scan_math("\\left| x \\right|") if k and k.strip()] == ["|", "x", "|"]
    assert [k for k in reconcile.scan_math("\\| x \\|") if k and k.strip()] == ["‖", "x", "‖"]
    assert [k for k in reconcile.scan_math("||x||") if k and k.strip()] == ["‖", "x", "‖"]       # a norm written with bars
    assert [k for k in reconcile.scan_math("a \\mid b \\parallel c") if k and k.strip()] == ["a", "|", "b", "‖", "c"]
    assert layer.Glyph("∥", "f", 10, (0, 0, 1, 1)).key == "‖" and layer.Glyph("|", "f", 10, (0, 0, 1, 1)).key == "|"


def test_a_drawn_tall_bar_is_not_an_invented_glyph():
    def draw(pg):
        pdfs.line(pg, 72, 120, [("t", "Then "), ("m", "x"), ("t", " is small.")])
        pg.draw_line((68, 108), (68, 140), width=0.5)             # a big \left| drawn as a stroke
    lay = one_page(draw)
    assert reconcile.reconcile_page("Then $\\left| x$ is small.", lay) == []


# ---------------------------------------------------------------- accents
def test_macron_drawn_on_the_base_line_box_is_an_accent():
    def draw(pg):
        pdfs.put(pg, 72, 120, "Let ")
        x = pdfs.put(pg, 100, 120, "x", font=pdfs.M)
        pdfs.put(pg, 100.5, 120, "¯", font=pdfs.M)               # same baseline, same box: no raise to measure
        pdfs.put(pg, x + 4, 120, "be real.")
    lay = layer.read_pdf  # noqa: F841
    pg_layer = one_page(draw)
    assert reconcile.reconcile_page("Let $\\bar{x}$ be real.", pg_layer) == []
    assert kinds(reconcile.reconcile_page("Let $x$ be real.", pg_layer)) == ["accent-lost"]


def test_precomposed_and_combining_accents_are_accents():
    md, lay = pdfs.PAGES_MD[1], layer.read_pdf(pdfs.build())[1]
    assert reconcile.reconcile_page(md.replace("$\\hat{w}$", "$ŵ$"), lay) == []              # w with circumflex
    assert reconcile.reconcile_page(md.replace("$\\hat{w}$", "$ŵ$"), lay) == []
    assert reconcile.reconcile_page(md.replace("$\\hat{w}$", "ŵ"), lay) == []                # in prose too
    assert kinds(reconcile.reconcile_page(md.replace("$\\hat{w}$", "$w$"), lay)) == ["accent-lost"]


def test_arrow_accents_are_known_to_both_sides():
    acc: list = []
    reconcile.scan_math("\\overleftarrow{S} \\overrightarrow{v} \\vec{u}", acc)
    assert [a[0] for a in acc] == ["vecl", "vec", "vec"]
    assert layer.ACCENTS["→"] == "vec" and layer.ACCENTS["←"] == "vecl"


def test_a_long_rule_over_a_phrase_is_not_a_bar_accent():
    def draw(pg):
        pdfs.put(pg, 72, 120, "the framework developed in this subsection is used throughout")
        pg.draw_line((72, 110.5), (420, 110.5), width=0.6)
    lay = one_page(draw)
    assert reconcile.reconcile_page("the framework developed in this subsection is used throughout", lay) == []


# ---------------------------------------------------------------- words
def test_letters_spelled_one_by_one_inside_math_are_still_the_word():
    def draw(pg):
        pdfs.put(pg, 72, 120, "A map is stable iff it is bounded.")
    lay = one_page(draw)
    assert reconcile.reconcile_page("A map is stable $\\mathrm { i f f }$ it is bounded.", lay) == []
    assert kinds(reconcile.reconcile_page("A map is stable $\\mathrm { i f }$ it is bounded.", lay)) != []


def test_inequality_signs_are_not_html_tags():
    out = reconcile.parse_markdown("so $a < b$ and then $c > d$ holds, <b>bold</b> too")
    assert {"and", "then", "holds", "bold", "too"} <= set(out.prose_tokens)


def test_prose_glued_to_math_by_a_missing_space():
    def glyphs(text, cls, x):
        return [layer.Glyph(c, "f", 10.0, (x + k * 5, 100, x + k * 5 + 5, 110), cls) for k, c in enumerate(text)]
    gl = glyphs("x", "mathit", 72) + glyphs("measures", "text", 77)           # the layer has one word `xmeasures`
    w = layer.Word("xmeasures", (72, 100, 117, 110), gl)
    assert not w.uniform
    lay = layer.PageLayer(1, 600, 800, glyphs=gl, words=[w])
    assert reconcile.reconcile_page("$x$ measures", lay) == []
    assert kinds(reconcile.reconcile_page("$x$", lay)) == ["lost"]


def test_compound_split_at_a_line_end():
    def draw(pg):
        pdfs.put(pg, 72, 120, "the strict non-")
        pdfs.put(pg, 72, 134, "saturation regime holds.")
    lay = one_page(draw)
    assert reconcile.reconcile_page("the strict non-saturation regime holds.", lay) == []


# ---------------------------------------------------------------- glyph names
def test_extension_font_operators_and_letter_macros():
    assert layer.font_class("ABCDEF+LMMathExtension10-Regular") == "bigop"
    g = layer.Glyph("P", "LMMathExtension10-Regular", 10, (0, 0, 1, 1), "bigop")
    assert g.key == "∑"
    assert layer.Glyph("", "LMMathExtension10-Regular", 10, (0, 0, 1, 1), "bigop").key == ""   # a parenthesis piece
    assert layer.Glyph("j", "LMMathExtension10-Regular", 10, (0, 0, 1, 1), "bigop").key == ""
    assert layer.Glyph("∆", "f", 10, (0, 0, 1, 1)).key == reconcile.norm("Δ")             # INCREMENT is Delta
    assert [k for k in reconcile.scan_math("\\ell + \\Delta") if k and k.strip()] == ["l", reconcile.norm("Δ")]


# ---------------------------------------------------------------- primes, limsup rules, broken text layers
def _hand(chars, cls="mathit", y=100.0, rules=()):
    gl = [layer.Glyph(c, "LMMathItalic10", 10.0, (72 + k * 6, y, 78 + k * 6, y + 10), cls) for k, c in enumerate(chars)]
    return layer.PageLayer(1, 600, 800, glyphs=gl, words=layer._words_of_line(gl, 0), rules=list(rules))


def test_prime_marks_are_counted():
    lay = _hand("J′")
    assert reconcile.reconcile_page("$J ^ { \\prime }$", lay) == []
    assert reconcile.reconcile_page("$J'$", lay) == []
    assert kinds(reconcile.reconcile_page("$J$", lay)) == ["lost-marks"]
    assert kinds(reconcile.reconcile_page("$J ^ { \\prime \\prime }$", lay)) == ["invented-marks"]
    assert kinds(reconcile.reconcile_page("$J ^ { - }$", _hand("J−"))) == []          # minus signs are not marks


def test_limsup_rule_must_match_the_page():
    plain, over = _hand("lim"), _hand("lim", rules=[layer.Rule((72, 95.0, 90, 95.5), "overline")])
    assert reconcile.reconcile_page("$\\lim$", plain) == []
    assert reconcile.reconcile_page("$\\varlimsup$", over) == []
    assert reconcile.reconcile_page("$\\overline{\\lim}$", over) == []
    assert kinds(reconcile.reconcile_page("$\\varlimsup$", plain)) == ["operator-decor"]
    assert kinds(reconcile.reconcile_page("$\\lim$", over)) == ["operator-decor"]


def test_broken_math_font_decoding_is_reported_not_trusted():
    lay = _hand("x““řď")
    assert "layer-unreliable" in kinds(reconcile.reconcile_page("$x$", lay))
    assert "layer-unreliable" not in kinds(reconcile.reconcile_page("$x$", _hand("xyz")))


def test_limsup_and_mod_operator_names_and_wide_accents():
    letters = lambda src: "".join(k for k in reconcile.scan_math(src) if k and k.strip())    # noqa: E731
    assert letters("\\limsup \\bmod") == "limsupmod"
    out = reconcile.parse_markdown("$\\limsup x \\pmod p$")
    assert out.math_bag["sup"] == 1 and out.math_bag["mod"] == 1
    gl = [layer.Glyph("b", "LMMathExtension10", 10.0, (72, 100, 80, 108), "bigop"),     # \widehat: CMEX code 0x62
          layer.Glyph("G", "LMMathItalic10", 10.0, (72, 108, 80, 118), "mathit")]
    lay = layer.PageLayer(1, 600, 800, glyphs=gl, words=layer._words_of_line(gl, 0))
    assert reconcile.reconcile_page("$\\widehat{G}$", lay) == []
    assert kinds(reconcile.reconcile_page("$G$", lay)) == ["accent-lost"]


def test_a_broken_layer_voids_the_glyph_checks_but_keeps_word_checks():
    lay = _hand("x““řď")
    got = kinds(reconcile.reconcile_page("$y \\hat{z}$", lay))
    assert got == ["layer-unreliable"]

import fitz

from kb.parse import layer
from kb.parse.layer import Glyph, font_class, glyph_latex

from . import pdfs


def test_font_classes():
    assert font_class("ABCDEF+MSBM10") == "mathbb"
    assert font_class("EUFM10") == "mathfrak"
    assert font_class("CMEX10") == "bigop"
    assert font_class("CMMI12") == "mathit"
    assert font_class("CMSY10") == "symbol"
    assert font_class("CMR10") == "roman"
    assert font_class("Helvetica") == "text" and font_class("Times-Roman") == "text" and font_class("") == "text"


def test_glyph_latex_maps_classes():
    assert glyph_latex("R", "mathbb") == "\\mathbb{R}"
    assert glyph_latex("g", "mathfrak") == "\\mathfrak{g}"
    assert glyph_latex("X", "bigop") == "\\sum" and glyph_latex("Y", "bigop") == "\\prod" and glyph_latex("Z", "bigop") == "\\int"
    assert glyph_latex("x", "text") == "x"
    assert Glyph("R", "MSBM10", 10, (0, 0, 5, 10), "mathbb").key == "r|bb"
    assert Glyph("X", "CMEX10", 10, (0, 0, 5, 10), "bigop").key == "∑"


def test_clean_strips_nul_and_control_codes():
    assert layer.clean("a\x00b\x07c\x1fd­e") == "abcd­e"
    assert layer.clean("tab\tkept\nnewline") == "tab\tkept\nnewline"


def test_page_layer_words_margin_figures_rules():
    layers = layer.read_pdf(pdfs.build())
    assert [l.page for l in layers] == [1, 2, 3]
    p1, p2, p3 = layers
    words = {w.text for w in p1.words}
    assert {"Let", "stable", "iff", "12", "(2.1)"} <= words
    head = next(w for w in p1.words if w.text == "Notes")
    assert p1.is_margin(head.bbox) and not p1.is_margin(next(w for w in p1.words if w.text == "Let").bbox)
    assert p1.is_margin(next(w for w in p1.words if w.text == "1" and w.bbox[1] > 700).bbox)       # page number
    assert len(p2.figures) == 1 and p2.in_figure((150, 200, 160, 210))
    assert any(r.kind == "overline" for r in p1.rules)
    assert "decomposition" in {w.text for w in p3.words}                      # hyphen-broken word joined
    assert all(not w.uniform for w in p1.words if w.text in ("xi", "y2"))      # a base with a script is not prose


def test_nul_in_pdf_text_never_reaches_the_layer():
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((72, 100), "clean text", fontsize=10)
    layers = layer.read_pdf(doc.tobytes())
    assert "\x00" not in layers[0].text() and layers[0].text() == "clean text"

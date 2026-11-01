import pytest

from kb_distillery.parse import layer, mutate, reconcile

from . import pdfs

LAYERS = layer.read_pdf(pdfs.build())
PAGES = list(zip(pdfs.PAGES_MD, LAYERS))
PER_TYPE_FLOOR = 0.99


def kinds(flags):
    return [f.kind for f in flags]


@pytest.mark.parametrize("i", range(len(PAGES)))
def test_clean_page_has_zero_flags(i):
    md, lay = PAGES[i]
    assert reconcile.reconcile_page(md, lay) == []


def test_benign_output_differences_stay_quiet():
    md, lay = PAGES[0]
    with_head = "Notes on stable maps\n\n" + md + "\n\n1\n"                 # running head and page number kept
    assert reconcile.reconcile_page(with_head, lay) == []
    assert reconcile.reconcile_page(md.replace("**Theorem 2.1.**", "__Theorem 2.1.__").replace("## ", "# "), lay) == []
    assert reconcile.reconcile_page(md.replace("Let $x$", "Let  *$x$*"), lay) == []
    md2, lay2 = PAGES[1]
    assert reconcile.reconcile_page(md2.replace("![](fig1.png)", "![a red square](fig1.png)"), lay2) == []
    md3, lay3 = PAGES[2]
    assert reconcile.reconcile_page(md3.replace("decomposition", "decompo-\nsition").replace("well-known", "well known"),
                                    lay3) == []


def test_lost_word_and_invented_word():
    md, lay = PAGES[0]
    f = reconcile.reconcile_page(md.replace(" unit", ""), lay)
    assert kinds(f) == ["lost"] and "unit" in f[0].detail
    f = reconcile.reconcile_page(md.replace("unit", "unit quark"), lay)
    assert kinds(f) == ["invented"] and "quark" in f[0].detail


def test_iff_to_if_is_a_replaced_word():
    md, lay = PAGES[0]
    f = reconcile.reconcile_page(md.replace("stable iff it", "stable if it"), lay)
    assert kinds(f) == ["replaced"] and "'if'" in f[0].detail and "'iff'" in f[0].detail


def test_accents_added_moved_lost():
    md, lay = PAGES[0]
    assert kinds(reconcile.reconcile_page(md.replace("$x$", "$\\tilde{x}$"), lay)) == ["accent-added"]
    moved = md.replace("$x$", "$\\tilde{x}$").replace("\\tilde{y}", "y")
    assert kinds(reconcile.reconcile_page(moved, lay)) == ["accent-moved"]
    assert kinds(reconcile.reconcile_page(md.replace("\\tilde{y}", "y"), lay)) == ["accent-lost"]
    assert kinds(reconcile.reconcile_page(md.replace("\\overline{A}", "A"), lay)) == ["accent-lost"]
    assert kinds(reconcile.reconcile_page(md.replace("\\tilde{y}", "\\hat{y}"), lay)) == ["accent-added", "accent-lost"]


def test_table_row_and_math_glyphs():
    md, lay = PAGES[0]
    assert "invented" in kinds(reconcile.reconcile_page(md + "| huge | 99 |\n", lay))
    assert kinds(reconcile.reconcile_page(md.replace("x_i", "x_j"), lay)) == ["lost-glyphs", "invented-glyphs"]
    assert "lost" in kinds(reconcile.reconcile_page(md.replace("| large | 58 |\n", ""), lay))


def test_numbers_out_of_order():
    md, lay = PAGES[0]
    swapped = md.replace("| small | 31 |", "| small | 58 |").replace("| large | 58 |", "| large | 31 |")
    assert kinds(reconcile.reconcile_page(swapped, lay)) == ["number-order"]


def test_blackboard_class_is_part_of_the_glyph():
    from kb_distillery.parse.layer import Glyph, PageLayer, Word
    g = Glyph("R", "MSBM10", 10, (100, 100, 108, 110), "mathbb")
    lay = PageLayer(1, 600, 800, [g], [Word("R", g.bbox, [g])])
    assert reconcile.reconcile_page("$\\mathbb{R}$", lay) == []
    assert reconcile.reconcile_page("$\\R$", lay) == []
    assert kinds(reconcile.reconcile_page("$R$", lay)) == ["lost-glyphs", "invented-glyphs"]


def test_few_flags_per_page_even_when_badly_wrong():
    md, lay = PAGES[0]
    bad = md.replace("iff", "if").replace("\\tilde{y}", "y").replace("12", "13").replace("unit", "")
    assert 0 < len(reconcile.reconcile_page(bad, lay)) < 8


def test_mutation_catch_rate_per_type():
    res = mutate.measure(PAGES, reconcile.reconcile_page)
    report = {k: "%d/%d" % v for k, v in res.items()}
    print("catch rate per mutation type:", report)
    for kind, (caught, total) in res.items():
        assert total >= 2, "%s: fixtures give too few sites (%d)" % (kind, total)
        assert caught / total >= PER_TYPE_FLOOR, "%s caught %d of %d" % (kind, caught, total)


def test_mutations_change_the_text():
    for md, _ in PAGES:
        for kind in mutate.KINDS:
            for m in mutate.variants(md, kind, limit=5):
                assert m.md != md and m.kind == kind

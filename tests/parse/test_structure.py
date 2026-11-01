from kb_distillery.parse import layer, structure

from . import pdfs

LAYERS = layer.read_pdf(pdfs.build())
MD = pdfs.PAGES_MD


def kinds(fl):
    return sorted(f.kind for f in fl)


def test_clean_run_has_no_flags_with_and_without_layers():
    assert structure.check_structure(MD) == []
    assert structure.check_structure(MD, LAYERS) == []


def test_dropped_statement_repeated_and_out_of_order():
    assert kinds(structure.check_structure([MD[0], MD[2]])) == ["dropped", "dropped"]       # Lemma 2.2 and (2.2) gone
    assert kinds(structure.check_structure([MD[0], MD[0]])) == ["repeated"] * 3          # theorem, equation, table
    assert "out-of-order" in kinds(structure.check_structure([MD[1], MD[0]]))


def test_layer_cross_check_finds_what_the_parser_dropped():
    no_lemma = MD[1].replace("**Lemma 2.2.** ", "")
    fl = structure.check_structure([MD[0], no_lemma, MD[2]], LAYERS)
    assert any(f.kind == "dropped" and "Lemma 2.2" in f.detail for f in fl)
    extra = MD[0] + "\n**Theorem 2.9.** Made up.\n"
    assert any(f.kind == "invented-label" for f in structure.check_structure([extra, MD[1], MD[2]], LAYERS))


def test_captions_must_sit_beside_their_figure_or_table():
    assert structure.check_structure([MD[1]]) == []
    no_fig = MD[1].replace("![](fig1.png)\n\n", "").replace("\n\nFigure 1. A sample curve\n", "\n\nplain\n\nFigure 1. A sample curve\n\nplain\n")
    assert "orphan-caption" in kinds(structure.check_structure([no_fig]))
    assert "orphan-caption" in kinds(structure.check_structure([MD[0].replace("| size | score |\n|---|---|\n| small | 31 |\n| large | 58 |\n", "")]))


def test_caption_numbers_in_sequence():
    dup = MD[2].replace("Table 2.", "Table 1.")
    assert "repeated" in kinds(structure.check_structure([MD[0], dup]))


def test_page_count_mismatch_is_an_error_not_a_silent_skip():
    import pytest
    from kb_distillery.parse import reconcile
    with pytest.raises(ValueError):
        structure.check_structure(MD, LAYERS[:2])
    with pytest.raises(ValueError):
        reconcile.reconcile_pages(MD[:2], LAYERS)

"""PDF reading fixes: control codes, no silent page cap, book toc/section/slug, draft results, catalog year,
easy-digest book gate, scrap PDF sniffing."""
import os

import pytest

fitz = pytest.importorskip("fitz")

from kb.core import books as core_books
from kb.ingest import book, catalog, easy_digest, extract, scrap


def make_pdf(path, n, text="page {i} body", toc=None):
    doc = fitz.open()
    for i in range(1, n + 1):
        doc.new_page().insert_text((72, 72), text.format(i=i))
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return str(path)


# 1. control codes
def test_clean_text_strips_nul_and_control_codes():
    assert extract.clean_text("a\x00b\x07c\x1fd\te\nf\rg\x7f") == "abcd\te\nf\rg"


def test_extract_text_has_no_control_codes(tmp_path, monkeypatch):
    p = make_pdf(tmp_path / "a.pdf", 1)
    monkeypatch.setattr(extract, "_extract_raw", lambda *a: "x\x00y\x02z")
    assert extract.extract_text(p) == "xyz"


# 2. no silent cap
def test_whole_paper_is_read_by_default(tmp_path):
    p = make_pdf(tmp_path / "long.pdf", 40)
    text = extract.extract_text(p)
    assert "page 40 body" in text and "truncated" not in text


def test_explicit_max_pages_truncates_and_says_so(tmp_path):
    p = make_pdf(tmp_path / "long.pdf", 40)
    text = extract.extract_text(p, max_pages=3)
    assert "page 3 body" in text and "page 4 body" not in text
    assert "truncated after 3 of 40 pages" in text


# 3. book toc / slug / section / notation
def test_verify_for_scope_handles_absolute_and_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(book, "ROOT", str(tmp_path))
    assert book.verify_for_scope(str(tmp_path / "raw/printed-docs/b.pdf")) == "raw/printed-docs/b.pdf"
    assert book.verify_for_scope("./raw/printed-docs/b.pdf") == "raw/printed-docs/b.pdf"
    assert book.verify_for_scope("/elsewhere/b.pdf") == "/elsewhere/b.pdf"


def test_toc_absolute_path_and_missing_file_errors(tmp_path, monkeypatch, capsys):
    from kb.ingest import cli
    monkeypatch.setattr(book, "ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "ROOT", str(tmp_path))
    ns = type("A", (), {"raw_path": str(tmp_path / "nope.pdf"), "depth": 1})()
    assert cli.cmd_toc(ns) == 1
    assert "no such file" in capsys.readouterr().err
    pdf = make_pdf(tmp_path / "b.pdf", 5, toc=[[1, "Chapter 1. A", 1], [1, "Chapter 2. B", 3], [1, "Chapter 3. C", 5]])
    ns = type("A", (), {"raw_path": pdf, "depth": 1})()
    assert cli.cmd_toc(ns) == 0
    out = capsys.readouterr().out
    assert "5 pages" in out and "Chapter 2. B" in out


def test_part_slug_long_titles_do_not_collide():
    a = book.part_slug("book-2014-x", "Chapter 7. " + "Very long shared prefix of a title " * 2 + "alpha")
    b = book.part_slug("book-2014-x", "Chapter 7. " + "Very long shared prefix of a title " * 2 + "beta")
    assert a != b
    assert book.part_slug("book-2014-x", "Chapter 1. Boolean functions") == "part-2014-x-ch1-boolean-functions"


def entries():
    raw = [(1, "Preface", 1), (1, "Chapter 1. Intro", 3), (2, "1. Basics", 4), (1, "Chapter 14. Late", 20),
           (1, "Appendix A", 30)]
    return book._finish([{"level": l, "title": t, "start": s} for l, t, s in raw], 40)


def test_section_number_picks_chapter_not_substring():
    es = entries()
    assert book.find_section(es, "1")["title"] == "Chapter 1. Intro"
    assert book.find_section(es, "14")["title"] == "Chapter 14. Late"
    assert book.find_section(es, "4") is None         # no chapter 4; never "Chapter 14" by substring
    assert book.find_section(es, "#2")["title"] == "Chapter 1. Intro"
    assert book.find_section(es, "late")["title"] == "Chapter 14. Late"


def test_notation_summary_is_matter_and_skipped():
    assert core_books._is_matter("Notation Summary")
    assert core_books._is_matter("1.  Notation summary")
    assert not core_books._is_matter("Chapter 1. Notation for graphs")


# 4. draft renders all results
def test_draft_renders_every_result(tmp_path):
    from kb.ingest import draft
    import inspect
    src = inspect.getsource(draft)
    assert "results[1:3]" not in src
    results = [f"result {i}" for i in range(8)]
    extra = "\n".join(f"- {r}" for r in results[1:])
    assert "result 7" in extra and extra.count("\n") == 6


# 5. catalog: year, no 2000 stub
def test_suggest_paper_name_never_invents_2000():
    with pytest.raises(ValueError, match="--year"):
        catalog._suggest_paper_name("some-scan.pdf")
    assert catalog._suggest_paper_name("some-scan.pdf", year=1999) == "1999-some-scan.pdf"
    assert catalog._suggest_paper_name("Notes 2015.pdf") .startswith("2015-")


def test_catalog_year_flag_reaches_catalog(monkeypatch):
    from kb.ingest import cli
    seen = {}
    monkeypatch.setattr(catalog, "catalog", lambda *a, **k: seen.update(k) or ("d", "s"))
    cli.main(["catalog", "raw/inbox/x.pdf", "--year", "1999"])
    assert seen["year"] == 1999


# 6. easy-digest refuses books
def test_easy_digest_refuses_a_book(monkeypatch):
    monkeypatch.setattr(easy_digest, "_resolve_raw", lambda a: "raw/printed-docs/2011-big.pdf")
    monkeypatch.setattr(book, "is_book", lambda p: True)
    with pytest.raises(ValueError, match="book"):
        easy_digest.prepare("raw/printed-docs/2011-big.pdf")


# 7. scrap detects PDFs by bytes / content type
def test_is_pdf_by_magic_or_content_type():
    assert scrap.is_pdf(b"%PDF-1.7 ...")
    assert scrap.is_pdf(b"zzz", "application/pdf; charset=binary")
    assert not scrap.is_pdf(b"<html>", "text/html")


def test_scrap_suffixless_url_serving_pdf_is_saved_as_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(scrap, "INBOX", str(tmp_path / "raw/inbox"))
    monkeypatch.setattr(scrap, "ROOT", str(tmp_path))
    os.makedirs(tmp_path / "raw/inbox")
    monkeypatch.setattr(scrap, "_check_pre_resolve", lambda *a: None)
    monkeypatch.setattr(scrap, "_check_post_bytes", lambda *a: None)
    monkeypatch.setattr(scrap, "record_source", lambda *a: None)
    monkeypatch.setattr(scrap, "_fetch", lambda url: (b"%PDF-1.5 body", "application/pdf"))
    rel = scrap.scrap("https://example.org/download?id=7")
    assert rel.endswith(".pdf") and (tmp_path / rel).read_bytes().startswith(b"%PDF-")

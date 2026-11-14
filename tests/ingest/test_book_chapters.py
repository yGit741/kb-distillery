"""Books are built at ingest: outline (or page headings, or a chapters file) -> book page with ## Chapters;
no chapters -> a clear stop that leaves the PDF in place; digest works by chapter and refuses before ingest."""
import os

import pytest

from tests import pdfkit

from kb_distillery.ingest import catalog, cli, session
from kb_distillery.ingest.sources.books import book
from kb_distillery.vault import books

KIT_TEMPLATES = os.path.join(os.path.dirname(book.__file__), "..", "..", "..", "kits", "base", "defaults", "templates")
OUTLINE = [[1, "Preface", 2], [1, "Chapter 1. Groups", 4], [2, "1.1 Basics", 4], [1, "Chapter 2. Rings", 30],
           [1, "Exercises", 55], [1, "Appendix A. Tables", 60], [1, "Index", 68]]


def make_pdf(path, n, toc=None, heads=None):
    doc = pdfkit.Doc()
    doc.set_metadata({"title": " "})
    for i in range(1, n + 1):
        page = doc.new_page()
        text = (heads or {}).get(i, f"body text of page {i}")
        page.insert_textbox((72, 72, 540, 760), text, fontsize=10)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def kb(tmp_path, monkeypatch):
    for d in ("wiki", "raw/inbox", "raw/printed-docs", "meta/.ingest"):
        os.makedirs(tmp_path / d, exist_ok=True)
    root = str(tmp_path)
    for mod in (book, cli, catalog):
        monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(book, "template_for", lambda t: os.path.join(KIT_TEMPLATES, f"{t}.md"))
    monkeypatch.setattr(catalog, "_run_lint", lambda: None)
    monkeypatch.setattr(catalog, "set_collection", lambda *a: None, raising=False)
    monkeypatch.setattr(catalog, "fetch_citations", lambda *a: None)
    return tmp_path


def test_outline_gives_chapters_with_fixed_ids(tmp_path):
    p = make_pdf(tmp_path / "b.pdf", 70, toc=OUTLINE)
    rows, total, source = book.chapter_rows(p)
    assert (total, source) == (70, "outline")
    assert [(r["id"], r["start"], r["end"]) for r in rows] == [
        ("front", 1, 3), ("ch1", 4, 29), ("ch2", 30, 59), ("appA", 60, 67), ("back", 68, 70)]


def test_page_headings_are_the_fallback(tmp_path):
    p = make_pdf(tmp_path / "b.pdf", 70, heads={5: "Chapter 1\nGroups\ntext", 31: "Chapter 2\nRings\ntext"})
    rows, _total, source = book.chapter_rows(p)
    assert source == "headings"
    assert [(r["id"], r["start"], r["end"]) for r in rows] == [("front", 1, 4), ("ch1", 5, 30), ("ch2", 31, 70)]
    assert rows[1]["title"] == "Chapter 1. Groups"


def test_catalog_builds_the_whole_book_page(kb):
    make_pdf(kb / "raw/inbox/2011-tiny-rings.pdf", 70, toc=OUTLINE)
    dest, slug = catalog.catalog("raw/inbox/2011-tiny-rings.pdf", fmt="printed-docs")
    assert dest == "raw/printed-docs/2011-tiny-rings.pdf" and slug == "book-2011-tiny-rings"
    assert not (kb / "wiki/paper-2011-tiny-rings.md").exists()
    text = (kb / "wiki/book-2011-tiny-rings.md").read_text(encoding="utf-8")
    assert "outline_chapters: 3" in text and "Coverage: **0 / 3 chapters**" in text
    assert [c.id for c in books.chapters(str(kb), dest)] == ["front", "ch1", "ch2", "appA", "back"]


def test_no_chapters_stops_and_leaves_the_pdf(kb):
    make_pdf(kb / "raw/inbox/2011-plain.pdf", 70)
    with pytest.raises(ValueError, match="--chapters-file"):
        catalog.catalog("raw/inbox/2011-plain.pdf", fmt="printed-docs")
    assert (kb / "raw/inbox/2011-plain.pdf").exists()
    assert not list((kb / "wiki").iterdir())


def test_chapters_file_supplies_the_breaks(kb):
    make_pdf(kb / "raw/inbox/2011-plain.pdf", 70)
    f = kb / "chapters.tsv"
    f.write_text("front\tFront\t1-2\nch1\tOne\t3-40\nch2\tTwo\t41-70\n", encoding="utf-8")
    catalog.catalog("raw/inbox/2011-plain.pdf", fmt="printed-docs", chapters_file=str(f))
    rows = books.chapters(str(kb), "raw/printed-docs/2011-plain.pdf")
    assert [(c.id, c.first_page, c.last_page) for c in rows] == [("front", 1, 2), ("ch1", 3, 40), ("ch2", 41, 70)]


def test_digest_is_refused_before_ingest(kb, capsys):
    make_pdf(kb / "raw/printed-docs/2011-tiny-rings.pdf", 70, toc=OUTLINE)
    assert cli.main(["full-digest", "raw/printed-docs/2011-tiny-rings.pdf", "--chapter", "1"]) == 2
    err = capsys.readouterr().err
    assert "no book page yet" in err and "ingest book raw/printed-docs/2011-tiny-rings.pdf" in err


def test_digest_by_chapter_opens_one_session_per_chapter(kb, monkeypatch, capsys):
    make_pdf(kb / "raw/printed-docs/2011-tiny-rings.pdf", 70, toc=OUTLINE)
    assert cli.main(["book", "raw/printed-docs/2011-tiny-rings.pdf"]) == 0
    opened = []
    monkeypatch.setattr(session, "begin", lambda raw, depth="full", scope=None: opened.append(scope) or f"s{len(opened)}")
    assert cli.main(["full-digest", "raw/printed-docs/2011-tiny-rings.pdf", "--all"]) == 0
    assert [(s["chapter"], s["pages"]) for s in opened] == [("ch1", [4, 29]), ("ch2", [30, 59]), ("appA", [60, 67])]
    assert all(s["book"] == "book-2011-tiny-rings" for s in opened)
    opened.clear()
    assert cli.main(["full-digest", "raw/printed-docs/2011-tiny-rings.pdf", "--chapters", "1-2"]) == 0
    assert [s["chapter"] for s in opened] == ["ch1", "ch2"]
    opened.clear()
    assert cli.main(["full-digest", "raw/printed-docs/2011-tiny-rings.pdf", "--chapter", "front"]) == 2
    assert "marked skip" in capsys.readouterr().err
    assert cli.main(["full-digest", "raw/printed-docs/2011-tiny-rings.pdf"]) == 2
    assert "digest it by chapter" in capsys.readouterr().err


def test_record_part_ticks_the_row_by_id(kb):
    make_pdf(kb / "raw/printed-docs/2011-tiny-rings.pdf", 70, toc=OUTLINE)
    book.build_book("raw/printed-docs/2011-tiny-rings.pdf")
    book.record_part("raw/printed-docs/2011-tiny-rings.pdf", "ch2", "part-2011-tiny-rings-ch2-rings", "full",
                     {"authors": ["Octo Cat"]})
    text = (kb / "wiki/book-2011-tiny-rings.md").read_text(encoding="utf-8")
    row = books.find_chapter(books.parse_chapters(text), "ch2")
    assert (row["status"], row["slug"]) == ("full", "part-2011-tiny-rings-ch2-rings")
    assert "authors: [Octo Cat]" in text and "maturity: reading" in text
    with pytest.raises(ValueError, match="no chapter 'ch9'"):
        book.record_part("raw/printed-docs/2011-tiny-rings.pdf", "ch9", "x", "full")


def test_aborting_one_chapter_keeps_another_chapters_tick(kb, monkeypatch):
    from kb_distillery.ingest import paths
    raw = "raw/printed-docs/2011-tiny-rings.pdf"
    make_pdf(kb / raw, 70, toc=OUTLINE)
    book.build_book(raw)
    monkeypatch.setattr(session, "ROOT", str(kb))
    monkeypatch.setattr(paths, "INGEST_ROOT", str(kb / "meta/.ingest"))
    monkeypatch.setattr(session, "verify_raw", lambda r: r)
    monkeypatch.setattr(session, "sha1_file", lambda r: "abc")
    monkeypatch.setattr(session, "existing_digest_for_raw", lambda *a: None)
    scope = {"book": "book-2011-tiny-rings", "label": "x"}
    s1 = session.begin(raw, scope={**scope, "chapter": "ch1", "pages": [4, 29]})
    s2 = session.begin(raw, scope={**scope, "chapter": "ch2", "pages": [30, 59]})
    assert (s1, s2) == ("abc-ch1", "abc-ch2")
    session._record_book_part(s1, session.load_session(s1), {"type": "part", "wiki_slug": "part-2011-tiny-rings-ch1-groups"})
    assert session.abort(s2) == 0
    text = (kb / "wiki/book-2011-tiny-rings.md").read_text(encoding="utf-8")
    assert books.find_chapter(books.parse_chapters(text), "ch1")["status"] == "full"
    assert "wiki/book-2011-tiny-rings.md" in session.load_session(s1)["modified_files"]


def test_handwritten_notebook_without_chapters_gets_page_sections(kb, capsys):
    os.makedirs(kb / "raw/handwritten", exist_ok=True)
    raw = "raw/handwritten/2011-lab-notes.pdf"
    make_pdf(kb / raw, 70)
    assert cli.main(["book", raw]) == 0
    assert "sections of 20 pages" in capsys.readouterr().out
    got = [(c.id, c.first_page, c.last_page) for c in books.chapters(str(kb), raw)]
    assert got == [("sec1", 1, 20), ("sec2", 21, 40), ("sec3", 41, 60), ("sec4", 61, 70)]
    assert (kb / "wiki/notebook-2011-lab-notes.md").exists()

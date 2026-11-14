import os
import tempfile
import unittest

from kb_distillery.vault import books
from kb_distillery.lint import lint


def row(cid, a, b, status="—", slug="", title="x"):
    return {"id": cid, "title": title, "start": a, "end": b, "status": status, "slug": slug}


HUB = """---
type: book
raw: raw/printed-docs/2000-a-book.pdf
book_pages: 100
outline_chapters: {outline}
maturity: reading
---

# A Book (2000)

## Overview

{overview}

## Chapters

Coverage: **1 / 2 chapters** · skip rows excluded

| Id | Chapter | Pages | Status | Note |
|----|---------|-------|--------|------|
| front | Front matter | 1–10 | skip | |
| {id1} | Chapter 1. Start | 11–40 | {st1} | {link1} |
| ch2 | Chapter 2. More | 41–100 | — | |

## Threads
"""
LINK = "[Ch. 1](part-2000-a-book-ch1-start.md)"
PART = """---
type: part
book: book-2000-a-book
chapter: {chapter}
year: 2000
maturity: digested
depth: {ds}
raw: raw/printed-docs/2000-a-book.pdf
section_pages: {pages}
---

# Ch. 1
"""
PROSE = ("A long enough paragraph about what this book is, how it is organised, and why "
         "it matters for the knowledge base, so the overview check passes.")


def hub_text(overview=PROSE, outline=2, id1="ch1", st1="full", link1=LINK):
    return HUB.format(overview=overview, outline=outline, id1=id1, st1=st1, link1=link1)


class ChaptersTableTest(unittest.TestCase):
    def test_parse(self):
        rows = books.parse_chapters(hub_text())
        self.assertEqual([(r["id"], r["start"], r["end"], r["status"]) for r in rows],
                         [("front", 1, 10, "skip"), ("ch1", 11, 40, "full"), ("ch2", 41, 100, "—")])
        self.assertEqual(rows[1]["slug"], "part-2000-a-book-ch1-start")

    def test_valid(self):
        self.assertEqual(books.validate(books.parse_chapters(hub_text()), 100, 2), ([], []))

    def test_gap_overlap_and_tail(self):
        errs, _ = books.validate([row("ch1", 1, 10), row("ch2", 12, 20)], 25)
        self.assertTrue(any("pages 11–11" in e for e in errs))
        self.assertTrue(any("pages 21–25" in e for e in errs))
        errs, _ = books.validate([row("ch1", 1, 10), row("ch2", 9, 20)], 20)
        self.assertTrue(any("overlap" in e for e in errs))

    def test_missing_bad_and_duplicate_ids(self):
        errs, _ = books.validate([row("", 1, 10), row("ch2", 11, 20)], 20)
        self.assertTrue(any("missing id" in e for e in errs))
        errs, _ = books.validate([row("chapter2", 1, 10), row("ch2", 11, 20)], 20)
        self.assertTrue(any("is not ch<N>" in e for e in errs))
        errs, _ = books.validate([row("ch2", 1, 10), row("ch2", 11, 20)], 20)
        self.assertTrue(any("duplicate chapter id 'ch2'" in e for e in errs))

    def test_count_must_match_the_outline_and_splits_count_once(self):
        rows = [row("ch1", 1, 10), row("ch2a", 11, 15), row("ch2b", 16, 20)]
        self.assertEqual(books.validate(rows, 20, 2)[0], [])
        errs, _ = books.validate(rows, 20, 3)
        self.assertTrue(any("outline has 3" in e for e in errs))

    def test_long_chapter_is_only_a_warning(self):
        errs, warns = books.validate([row("ch1", 1, 90)], 90)
        self.assertEqual(errs, [])
        self.assertTrue(any("kept whole" in w for w in warns))

    def test_digested_row_needs_link(self):
        errs, _ = books.validate([row("ch1", 1, 10, "full")], 10)
        self.assertTrue(any("needs a link" in e for e in errs))

    def test_coverage_counts_chapters(self):
        rows = [row("front", 1, 5, "skip"), row("ch1", 6, 10, "full", "p"), row("ch2a", 11, 15, "full", "q"),
                row("ch2b", 16, 20), row("back", 21, 22, "skip")]
        self.assertEqual(books.chapter_coverage(rows), (1, 2))
        self.assertEqual(books.coverage_line(rows), "Coverage: **1 / 2 chapters** · skip rows excluded")
        self.assertEqual(books.book_status(rows), "reading")

    def test_replace_round_trip_rewrites_a_partition_heading(self):
        old = hub_text().replace("## Chapters", "## Partition")
        rows = books.set_chapter(books.parse_chapters(hub_text()), "ch2", "easy", "part-2000-a-book-ch2-more")
        out = books.replace_chapters(old, rows)
        self.assertNotIn("## Partition", out)
        self.assertEqual(books.parse_chapters(out)[2]["slug"], "part-2000-a-book-ch2-more")
        self.assertIn("## Threads", out)

    def test_overview(self):
        self.assertTrue(books.overview_ok(hub_text()))
        self.assertFalse(books.overview_ok(hub_text(overview="<!-- todo -->")))


class OutlineTest(unittest.TestCase):
    def e(self, level, title, start):
        return {"level": level, "title": title, "start": start}

    def test_outline_to_chapters_with_front_back_and_folded_exercises(self):
        es = [self.e(1, "Preface", 3), self.e(1, "Chapter 1. Basics", 9), self.e(2, "1.1 Sets", 9),
              self.e(1, "Chapter 2. Limits", 30), self.e(1, "Exercises", 50),
              self.e(1, "Appendix A Tables", 60), self.e(1, "Bibliography", 70), self.e(1, "Index", 75)]
        rows = books.propose(es, 80)
        self.assertEqual([(r["id"], r["start"], r["end"], r["status"]) for r in rows],
                         [("front", 1, 8, "skip"), ("ch1", 9, 29, "—"), ("ch2", 30, 59, "—"),
                          ("appA", 60, 69, "—"), ("back", 70, 80, "skip")])
        self.assertEqual(books.validate(rows, 80, len(books.content_ids(rows)))[0], [])

    def test_part_wrappers_are_skipped_for_the_numbered_level(self):
        es = [self.e(1, "Part I Foundations", 5), self.e(2, "Chapter 1. One", 6), self.e(2, "Chapter 2. Two", 20),
              self.e(1, "Part II Uses", 40), self.e(2, "Chapter 3. Three", 41)]
        rows = books.propose(es, 60)
        self.assertEqual([(r["id"], r["start"], r["end"]) for r in rows],
                         [("front", 1, 5), ("ch1", 6, 19), ("ch2", 20, 40), ("ch3", 41, 60)])

    def test_numbered_titles_and_roman_chapters(self):
        self.assertEqual(books.chapter_id("3. Influences"), "ch3")
        self.assertEqual(books.chapter_id("Chapter IV Noise"), "ch4")
        self.assertEqual(books.chapter_id("Appendix B: Proofs"), "appB")
        self.assertEqual(books.chapter_id("2.3 Total influence"), "")
        self.assertEqual(books.chapter_id("Some tips"), "")

    def test_no_numbered_chapters_means_no_guess(self):
        self.assertEqual(books.propose([], 50), [])
        self.assertEqual(books.propose([self.e(1, "Intro", 1), self.e(1, "Middle", 20)], 50), [])

    def test_chapters_file(self):
        rows = books.parse_chapters_file("# hand-made\nfront\tFront\t1-4\nch1\tOne\t5-20\nch2\tTwo\t21-30\n", 30)
        self.assertEqual([(r["id"], r["status"]) for r in rows], [("front", "skip"), ("ch1", "—"), ("ch2", "—")])
        with self.assertRaisesRegex(ValueError, "line 1"):
            books.parse_chapters_file("ch1 One 1-30\n", 30)
        with self.assertRaisesRegex(ValueError, "gap"):
            books.parse_chapters_file("ch1\tOne\t1-10\n", 30)


class SelectorTest(unittest.TestCase):
    ROWS = [row("front", 1, 4, "skip"), row("ch1", 5, 10), row("ch2", 11, 20), row("ch11a", 21, 30),
            row("ch11b", 31, 40), row("appA", 41, 50), row("back", 51, 52, "skip")]

    def ids(self, sel):
        return [r["id"] for r in books.select(self.ROWS, sel)]

    def test_selectors(self):
        self.assertEqual(self.ids("2"), ["ch2"])
        self.assertEqual(self.ids("ch2"), ["ch2"])
        self.assertEqual(self.ids("11"), ["ch11a", "ch11b"])          # a split chapter: both rows
        self.assertEqual(self.ids("ch11b"), ["ch11b"])
        self.assertEqual(self.ids("1-2"), ["ch1", "ch2"])
        self.assertEqual(self.ids("ch1-ch11"), ["ch1", "ch2", "ch11a", "ch11b"])
        self.assertEqual(self.ids("appA"), ["appA"])
        self.assertEqual(self.ids("2,appA"), ["ch2", "appA"])
        self.assertEqual(self.ids("all"), ["ch1", "ch2", "ch11a", "ch11b", "appA"])
        with self.assertRaisesRegex(ValueError, "this book has: ch1, ch2"):
            self.ids("7")

    def test_ids_are_fixed_through_a_split(self):
        before = [row("ch1", 1, 10), row("ch2", 11, 40), row("ch3", 41, 50)]
        after = [row("ch1", 1, 10), row("ch2a", 11, 25), row("ch2b", 26, 40), row("ch3", 41, 50)]
        self.assertEqual(books.validate(after, 50, 3)[0], [])
        for sel in ("1", "3"):
            self.assertEqual([r["id"] for r in books.select(before, sel)], [r["id"] for r in books.select(after, sel)])
        self.assertEqual([r["id"] for r in books.select(after, "2")], ["ch2a", "ch2b"])

    def test_chapters_helper_reads_the_book_page(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "wiki"))
            with open(os.path.join(root, "wiki", "book-2000-a-book.md"), "w", encoding="utf-8") as f:
                f.write(hub_text())
            got = books.chapters(root, "raw/printed-docs/2000-a-book.pdf")
            self.assertEqual(got[1], books.Chapter("ch1", "Chapter 1. Start", 11, 40, "full",
                                                   "part-2000-a-book-ch1-start"))
            self.assertEqual([c.id for c in books.select(got, "all")], ["ch1", "ch2"])
            with self.assertRaisesRegex(LookupError, "ingest it first"):
                books.chapters(root, "raw/printed-docs/other.pdf")


class LintBooksTest(unittest.TestCase):
    def run_check(self, pages):
        lint.errors, lint.warnings = [], []
        hubs = lint.check_books(pages)
        return hubs, list(lint.errors), list(lint.warnings)

    def pages(self, ds="full", pagerange="11-40", chapter="ch1", part=True, **hub):
        h = hub_text(**hub)
        out = {"book-2000-a-book": ("wiki/book-2000-a-book.md", lint.parse_frontmatter(h), h)}
        if part:
            p = PART.format(ds=ds, pages=pagerange, chapter=chapter)
            out["part-2000-a-book-ch1-start"] = ("wiki/part-2000-a-book-ch1-start.md", lint.parse_frontmatter(p), p)
        return out

    def errs(self, **kw):
        return self.run_check(self.pages(**kw))[1]

    def test_consistent_book_passes(self):
        hubs, errs, warns = self.run_check(self.pages())
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        cov = lint.book_coverage(self.pages(), hubs)["raw/printed-docs/2000-a-book.pdf"]
        self.assertEqual((cov["chapters_done"], cov["chapters"]), (1, 2))
        self.assertEqual(cov["chapter_ids"], ["ch1"])

    def test_part_status_must_match_row(self):
        self.assertTrue(any("row ch1 says 'full'" in e for e in self.errs(ds="deep")))

    def test_part_range_must_match_its_row(self):
        self.assertTrue(any("differ from" in e for e in self.errs(pagerange="11-39")))

    def test_missing_chapter_on_part(self):
        self.assertTrue(any("requires `chapter:`" in e for e in self.errs(chapter="")))

    def test_missing_id_on_row(self):
        self.assertTrue(any("missing id" in e for e in self.errs(id1="", part=False, st1="—", link1="")))

    def test_duplicate_id(self):
        self.assertTrue(any("duplicate chapter id" in e for e in self.errs(id1="ch2", part=False, st1="—", link1="")))

    def test_changed_id(self):
        errs = self.errs(id1="ch9", outline=2)
        self.assertTrue(any("chapter id changed" in e for e in errs), errs)

    def test_count_differs_from_outline(self):
        self.assertTrue(any("outline has 3" in e for e in self.errs(outline=3)))

    def test_part_chapter_with_no_row(self):
        self.assertTrue(any("ch7 has no row" in e for e in self.errs(chapter="ch7", st1="—", link1="")))

    def test_row_digested_with_no_page(self):
        self.assertTrue(any("does not exist" in e for e in self.errs(part=False)))

    def test_old_partition_table_points_at_migrate(self):
        h = hub_text().replace("## Chapters", "## Partition")
        _h, errs, _w = self.run_check({"book-2000-a-book": ("wiki/book-2000-a-book.md", lint.parse_frontmatter(h), h)})
        self.assertTrue(any("ops -- migrate" in e for e in errs))

    def test_empty_overview_warns(self):
        _h, errs, warns = self.run_check(self.pages(overview=""))
        self.assertEqual(errs, [])
        self.assertTrue(any("## Overview" in w for w in warns))


class IngestBooksTest(unittest.TestCase):
    def test_verify_accepts_partial(self):
        import inspect
        from kb_distillery.ingest import verify
        self.assertIn('"partial"', inspect.getsource(verify.verify_raw))

    def test_part_slug_carries_the_chapter_id(self):
        from kb_distillery.ingest.sources.books.book import part_slug
        self.assertEqual(part_slug("book-2014-x", "Chapter 1. Boolean functions", "ch1"),
                         "part-2014-x-ch1-boolean-functions")
        self.assertEqual(part_slug("book-2014-x", "Appendix A. Tables", "appA"), "part-2014-x-appa-tables")
        self.assertEqual(part_slug("book-2014-x", "Chapter 11. Gauss", "ch11b"), "part-2014-x-ch11b-gauss")

    def test_session_id_per_chapter(self):
        from kb_distillery.ingest.session import session_id
        self.assertEqual(session_id("abc", {}), "abc")
        self.assertEqual(session_id("abc", {"book": "b", "pages": [3, 9], "chapter": "ch2"}), "abc-ch2")


if __name__ == "__main__":
    unittest.main()

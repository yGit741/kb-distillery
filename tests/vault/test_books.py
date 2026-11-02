import os
import sys
import unittest

from kb_distillery.vault import books
from kb_distillery.lint import lint


def row(a, b, status="—", slug="", title="x"):
    return {"title": title, "start": a, "end": b, "status": status, "slug": slug}


HUB = """---
type: book
raw: raw/printed-docs/2000-a-book.pdf
book_pages: 100
maturity: reading
---

# A Book (2000)

## Overview

{overview}

## Partition

Coverage: **30 / 90 pp (33%)** · skip rows excluded · parts ≤ 60 pp

| # | Part | Pages | Status | Note |
|---|------|-------|--------|------|
| 1 | Front matter | 1–10 | skip | |
| 2 | Chapter 1. Start | 11–40 | full | [[part-2000-a-book-ch1-start]] |
| 3 | Chapter 2. More | 41–100 | — | |

## Threads
"""
PART = """---
type: part
book: book-2000-a-book
year: 2000
maturity: digested
depth: {ds}
raw: raw/printed-docs/2000-a-book.pdf
section_pages: {pages}
---

# Ch. 1
"""
PROSE = ("A long enough paragraph about what this book is, how it is organised, and why "
         "it matters for the thesis, so the overview check passes.")


class PartitionTest(unittest.TestCase):
    def test_parse(self):
        rows = books.parse_partition(HUB.format(overview=PROSE))
        self.assertEqual([(r["start"], r["end"], r["status"]) for r in rows],
                         [(1, 10, "skip"), (11, 40, "full"), (41, 100, "—")])
        self.assertEqual(rows[1]["slug"], "part-2000-a-book-ch1-start")

    def test_valid_partition(self):
        errs, warns = books.validate([row(1, 10, "skip"), row(11, 50), row(51, 100)], 100)
        self.assertEqual((errs, warns), ([], []))

    def test_gap_overlap_and_tail(self):
        errs, _ = books.validate([row(1, 10), row(12, 50), row(50, 90)], 100)
        text = " ".join(errs)
        self.assertIn("gap: pages 11–11", text)
        self.assertIn("overlap", text)
        self.assertIn("pages 91–100", text)

    def test_cap_is_a_warning(self):
        errs, warns = books.validate([row(1, 100)], 100, cap=60)
        self.assertEqual(errs, [])
        self.assertTrue(any("over the 60-page cap" in w for w in warns))

    def test_digested_row_needs_link(self):
        errs, _ = books.validate([row(1, 100, "full")], 100)
        self.assertTrue(any("needs a [[part-page]]" in e for e in errs))

    def test_coverage_and_status(self):
        rows = [row(1, 10, "skip"), row(11, 40, "full", "a"), row(41, 100)]
        self.assertEqual(books.coverage(rows), (30, 90))
        self.assertEqual(books.book_status(rows), "reading")
        self.assertEqual(books.book_status([row(1, 10, "skip"), row(11, 100, "deep", "a")]),
                         "digested")
        self.assertEqual(books.book_status([row(1, 100)]), "to-read")

    def test_carve_splits_undigested_rows(self):
        rows = books.carve([row(1, 10, "skip"), row(11, 100)], 30, 60, "full", "p", "Mid")
        self.assertEqual([(r["start"], r["end"], r["status"]) for r in rows],
                         [(1, 10, "skip"), (11, 29, "—"), (30, 60, "full"), (61, 100, "—")])
        self.assertEqual(books.validate(rows, 100)[0], [])

    def test_carve_refuses_digested(self):
        with self.assertRaises(ValueError):
            books.carve([row(1, 50, "full", "a"), row(51, 100)], 40, 70, "full", "b", "x")

    def test_replace_partition_round_trip(self):
        text = HUB.format(overview=PROSE)
        rows = books.carve(books.parse_partition(text), 41, 70, "easy", "part-2000-a-book-ch2", "Ch 2")
        out = books.replace_partition(text, rows)
        self.assertIn("## Threads", out)
        self.assertEqual(len(books.parse_partition(out)), 4)
        self.assertIn(books.coverage_line(rows), out)

    def test_overview(self):
        self.assertTrue(books.overview_ok(HUB.format(overview=PROSE)))
        self.assertFalse(books.overview_ok(HUB.format(overview="<!-- todo -->")))


class ProposeTest(unittest.TestCase):
    def entries(self):
        # outline in src/kb_distillery/ingest/book.py read_toc shape
        def e(level, title, a, b):
            return {"level": level, "title": title, "start": a, "end": b}
        return [e(1, "Preface", 5, 10), e(1, "Part I Basics", 11, 130),
                e(2, "Chapter 1", 13, 40), e(2, "Chapter 2", 41, 70), e(2, "Chapter 3", 71, 130),
                e(1, "Chapter 4", 131, 160), e(1, "Index", 161, 170)]

    def test_exhaustive_disjoint_and_split_at_boundaries(self):
        rows = books.propose(self.entries(), 170, cap=60)
        self.assertEqual(books.validate(rows, 170, cap=60)[0], [])
        spans = [(r["start"], r["end"], r["status"]) for r in rows]
        self.assertEqual(spans[0], (1, 10, "skip"))           # front matter + preface merged
        self.assertEqual(spans[-1], (161, 170, "skip"))       # index
        self.assertIn((11, 70, "—"), spans)                   # lead-in pages + ch1 + ch2
        self.assertIn((71, 130, "—"), spans)
        self.assertIn((131, 160, "—"), spans)

    def test_no_outline(self):
        self.assertEqual(books.propose([], 50), [row(1, 50, title="Whole book")])


class LintBooksTest(unittest.TestCase):
    def run_check(self, pages):
        lint.errors, lint.warnings = [], []
        hubs = lint.check_books(pages)
        return hubs, list(lint.errors), list(lint.warnings)

    def pages(self, ds="full", pagerange="11-40", overview=PROSE):
        hub = HUB.format(overview=overview)
        part = PART.format(ds=ds, pages=pagerange)
        return {"book-2000-a-book": ("wiki/book-2000-a-book.md", lint.parse_frontmatter(hub), hub),
                "part-2000-a-book-ch1-start": ("wiki/part-2000-a-book-ch1-start.md",
                                          lint.parse_frontmatter(part), part)}

    def test_consistent_book_passes(self):
        hubs, errs, warns = self.run_check(self.pages())
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        cov = lint.book_coverage(self.pages(), hubs)
        self.assertEqual(cov["raw/printed-docs/2000-a-book.pdf"]["covered"], 30)
        self.assertEqual(cov["raw/printed-docs/2000-a-book.pdf"]["total"], 90)

    def test_part_status_must_match_row(self):
        _h, errs, _w = self.run_check(self.pages(ds="deep"))
        self.assertTrue(any("row says 'full'" in e for e in errs))

    def test_part_range_must_be_a_row(self):
        _h, errs, _w = self.run_check(self.pages(pagerange="11-39"))
        self.assertTrue(any("matches no row" in e for e in errs))

    def test_empty_overview_warns(self):
        _h, errs, warns = self.run_check(self.pages(overview=""))
        self.assertEqual(errs, [])
        self.assertTrue(any("## Overview" in w for w in warns))


class IngestBooksTest(unittest.TestCase):
    def test_verify_accepts_partial(self):
        import inspect
        from kb_distillery.ingest import verify
        self.assertIn('"partial"', inspect.getsource(verify.verify_raw))

    def test_part_slug(self):
        from kb_distillery.ingest.book import part_slug
        self.assertEqual(part_slug("book-2014-x", "Chapter 1. Boolean functions"),
                         "part-2014-x-ch1-boolean-functions")
        self.assertEqual(part_slug("book-2014-x", "Part I Foundations"), "part-2014-x-part-i-foundations")

    def test_session_id_per_part(self):
        from kb_distillery.ingest.session import session_id
        self.assertEqual(session_id("abc", {}), "abc")
        self.assertEqual(session_id("abc", {"book": "b", "pages": [3, 9]}), "abc-p3-9")


if __name__ == "__main__":
    unittest.main()

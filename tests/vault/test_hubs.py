import os
import sys
import unittest

from kb_distillery.vault import hubs

HUB = """---
type: course
maturity: reading
institution: openu
course_code: "20229"
---

# Linear Algebra 2

## Overview

Second course.

## Contents

Coverage: **1 / 2 items (50%)** · skip rows excluded

| # | Item | Raw | Status | Note |
|---|------|-----|--------|------|
| 1 | Lecture 1 · Spaces | `raw/presentations/la-01.pdf` `raw/handwritten/la-01-notes.pdf` | full | [[lecture-la-01-spaces]] |
| 2 | Course book | `raw/printed-docs/la-book.pdf` | — | |
| 3 | Scratch | `raw/handwritten/la-scratch.pdf` | skip | |

## Threads
"""
MEMBERS = {"raw/presentations/la-01.pdf", "raw/handwritten/la-01-notes.pdf",
           "raw/printed-docs/la-book.pdf", "raw/handwritten/la-scratch.pdf"}


class ContentsTest(unittest.TestCase):
    def setUp(self):
        self.rows = hubs.parse_contents(HUB)

    def test_parse(self):
        self.assertEqual(len(self.rows), 3)
        self.assertEqual(self.rows[0]["raws"], ["raw/presentations/la-01.pdf",
                                                "raw/handwritten/la-01-notes.pdf"])
        self.assertEqual(self.rows[0]["slug"], "lecture-la-01-spaces")
        self.assertEqual(self.rows[1]["status"], "—")
        self.assertEqual(self.rows[2]["status"], "skip")

    def test_valid_against_members(self):
        errs, _ = hubs.validate(self.rows, MEMBERS, "course-openu-linear-algebra-2")
        self.assertEqual(errs, [])

    def test_member_missing_from_table(self):
        errs, _ = hubs.validate(self.rows, MEMBERS | {"raw/printed-docs/extra.pdf"}, "c")
        self.assertTrue(any("extra.pdf" in e and "no contents row" in e for e in errs))

    def test_row_not_a_member(self):
        errs, _ = hubs.validate(self.rows, MEMBERS - {"raw/printed-docs/la-book.pdf"}, "c")
        self.assertTrue(any("la-book.pdf" in e and "does not name" in e for e in errs))

    def test_digested_row_needs_link(self):
        rows = [dict(self.rows[1], status="full")]
        errs, _ = hubs.validate(rows, {"raw/printed-docs/la-book.pdf"}, "c")
        self.assertTrue(any("needs a [[page]] link" in e for e in errs))

    def test_duplicate_path(self):
        rows = self.rows + [{"title": "dup", "raws": ["raw/printed-docs/la-book.pdf"],
                             "status": "—", "slug": ""}]
        errs, _ = hubs.validate(rows, MEMBERS, "c")
        self.assertTrue(any("listed twice" in e for e in errs))

    def test_coverage_and_status(self):
        self.assertEqual(hubs.coverage(self.rows), (1, 2))
        self.assertEqual(hubs.hub_status(self.rows), "reading")
        self.assertIn("1 / 2 items (50%)", hubs.coverage_line(self.rows))

    def test_render_roundtrip(self):
        text = hubs.replace_contents(HUB, self.rows)
        self.assertEqual(hubs.parse_contents(text), self.rows)
        self.assertIn("## Threads", text)

    def test_note_is_a_page_link_and_keeps_its_text(self):
        rows = [dict(self.rows[0]), dict(self.rows[1], status="full", slug="book-la", link_text="The course book")]
        text = hubs.replace_contents(HUB, rows)
        self.assertIn("[lecture-la-01-spaces](lecture-la-01-spaces.md) |", text)       # no text given: the slug
        self.assertIn("[The course book](book-la.md) |", text)
        back = hubs.parse_contents(text)
        self.assertEqual([r["slug"] for r in back], ["lecture-la-01-spaces", "book-la"])
        self.assertEqual(back[1]["link_text"], "The course book")
        self.assertNotIn("link_text", back[0])
        self.assertEqual(hubs.parse_contents(hubs.replace_contents(HUB, back)), back)   # stable

    def test_old_wikilink_note_still_reads(self):
        text = HUB.replace("## Contents\n", "## Contents\n\n| # | Item | Raw | Status | Note |\n|---|---|---|---|---|\n"
                           "| 1 | A | `raw/x.pdf` | full | [[lecture-a\\|Lecture A]] |\n", 1)
        row = hubs.parse_contents(text)[0]
        self.assertEqual((row["slug"], row.get("link_text")), ("lecture-a", "Lecture A"))

    def test_tick_records_the_link_text(self):
        rows = hubs.tick(self.rows, 1, "easy", "book-la", "Course book")
        self.assertEqual(rows[1]["link_text"], "Course book")
        self.assertIn("[Course book](book-la.md)", hubs.render(rows))

    def test_add_row_and_tick(self):
        rows = hubs.add_row(self.rows, "Lecture 2", ["raw/presentations/la-02.pdf"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(hubs.add_row(rows, "again", ["raw/presentations/la-02.pdf"]), rows)
        rows = hubs.tick(rows, 3, "easy", "lecture-la-02")
        self.assertEqual(rows[3]["status"], "easy")
        with self.assertRaises(ValueError):
            hubs.tick(rows, 0, "full", "lecture-other")

    def test_row_status_by_path(self):
        m = hubs.row_status_by_path(self.rows)
        self.assertEqual(m["raw/handwritten/la-01-notes.pdf"], "full")
        self.assertEqual(m["raw/handwritten/la-scratch.pdf"], "skip")


if __name__ == "__main__":
    unittest.main()

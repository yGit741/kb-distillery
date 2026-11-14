"""0016_book_chapters: a book's ## Partition becomes ## Chapters with fixed ids; parts get `chapter:`, renamed
parts keep their old slug as an alias and every wiki link follows. Idempotent."""
import importlib.util
import os
import tempfile
import unittest

from kb_distillery.config.paths import MIGRATIONS_CODE_PATH
from kb_distillery.lint import lint
from kb_distillery.vault import books

spec = importlib.util.spec_from_file_location("m0016", os.path.join(MIGRATIONS_CODE_PATH, "0016_book_chapters.py"))
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

BOOK = """---
type: book
layer: collection
authors: [Octo Cat]
year: 2010
raw: raw/printed-docs/2010-tiny-fields.pdf
book_pages: 120
maturity: reading
related: []
---

# Tiny Fields (2010)

## Overview

A made-up book.

## Partition

Coverage: **30 / 108 pp (27%)** · skip rows excluded · parts ≤ 60 pp

| # | Part | Pages | Status | Note |
|---|------|-------|--------|------|
| 1 | Front matter · Preface | 1–8 | skip |  |
| 2 | Chapter 1. Groups | 9–30 | full | [Ch. 1](part-2010-tiny-fields-ch1-groups.md) |
| 3 | Chapter 2. Rings | 31–60 | — |  |
| 4 | Chapter 3. Fields: 3.1 Basics → 3.4 Towers | 61–80 | full | [Fields](part-2010-tiny-fields-fields-basics.md) |
| 5 | Chapter 3. Fields: 3.5 Exercises and notes | 81–95 | — |  |
| 6 | Chapter 4. Galois: 4.1 → 4.3 | 96–105 | — |  |
| 7 | Chapter 4. Galois: 4.4 Exercises | 106–110 | — |  |
| 8 | A few hints | 111–116 | — |  |
| 9 | Bibliography · Index | 117–120 | skip |  |

## Threads
"""


def part(slug_section, pages):
    return f"""---
type: part
layer: source
book: book-2010-tiny-fields
maturity: digested
depth: full
raw: raw/printed-docs/2010-tiny-fields.pdf
section: {slug_section}
section_pages: {pages}
---

# {slug_section}
"""


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


class BookChaptersMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "wiki/book-2010-tiny-fields.md", BOOK)
        write(self.root, "wiki/part-2010-tiny-fields-ch1-groups.md", part("Chapter 1. Groups", "9-30"))
        write(self.root, "wiki/part-2010-tiny-fields-fields-basics.md", part("Chapter 3. Fields", "61-80"))
        write(self.root, "wiki/idea-x.md", "---\ntype: idea\nrelated: [part-2010-tiny-fields-fields-basics.md]\n---\n\n"
                                          "See [Fields](part-2010-tiny-fields-fields-basics.md#towers).\n\n"
                                          "## My notes\n\nMine: [[part-2010-tiny-fields-fields-basics]]\n")
        write(self.root, "think/note.md", "[[part-2010-tiny-fields-fields-basics]]\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_partition_becomes_chapters(self):
        report = mig.apply(self.root)
        text = read(self.root, "wiki/book-2010-tiny-fields.md")
        self.assertNotIn("## Partition", text)
        rows = books.parse_chapters(text)
        self.assertEqual([(r["id"], r["start"], r["end"], r["status"]) for r in rows], [
            ("front", 1, 8, "skip"),
            ("ch1", 9, 30, "full"),
            ("ch2", 31, 60, "—"),
            ("ch3a", 61, 80, "full"),        # digested on its own: the exercises row stays a split
            ("ch3b", 81, 95, "—"),
            ("ch4", 96, 116, "—"),           # exercises and the unnumbered hints merge (none digested)
            ("back", 117, 120, "skip"),
        ])
        self.assertIn("outline_chapters: 4", text)
        self.assertEqual(books.validate(rows, 120, 4)[0], [])
        self.assertIn("Coverage: **1 / 4 chapters**", text)
        self.assertEqual(report["renamed"], {"part-2010-tiny-fields-fields-basics": "part-2010-tiny-fields-ch3a-fields-basics"})
        self.assertEqual(report["think"], ["think/note.md"])

    def test_parts_get_chapter_and_old_slugs_stay_aliases(self):
        mig.apply(self.root)
        self.assertIn("chapter: ch1", read(self.root, "wiki/part-2010-tiny-fields-ch1-groups.md"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki/part-2010-tiny-fields-fields-basics.md")))
        moved = read(self.root, "wiki/part-2010-tiny-fields-ch3a-fields-basics.md")
        self.assertIn("chapter: ch3a", moved)
        self.assertIn("aliases: [part-2010-tiny-fields-fields-basics]", moved)
        idea = read(self.root, "wiki/idea-x.md")
        self.assertIn("(part-2010-tiny-fields-ch3a-fields-basics.md#towers)", idea)
        self.assertIn("related: [part-2010-tiny-fields-ch3a-fields-basics.md]", idea)
        self.assertEqual(read(self.root, "think/note.md"), "[[part-2010-tiny-fields-fields-basics]]\n")
        self.assertTrue(idea.endswith("## My notes\n\nMine: [[part-2010-tiny-fields-fields-basics]]\n"))
        from kb_distillery.vault import links
        fms = {fn[:-3]: lint.parse_frontmatter(read(self.root, f"wiki/{fn}")) or {}
               for fn in os.listdir(os.path.join(self.root, "wiki"))}
        self.assertEqual(links.resolve_slug("part-2010-tiny-fields-fields-basics", set(fms), links.alias_map(fms)),
                         "part-2010-tiny-fields-ch3a-fields-basics")

    def test_lint_is_clean_on_the_migrated_book(self):
        mig.apply(self.root)
        pages = {}
        for fn in os.listdir(os.path.join(self.root, "wiki")):
            text = read(self.root, f"wiki/{fn}")
            pages[fn[:-3]] = (f"wiki/{fn}", lint.parse_frontmatter(text) or {}, text)
        lint.errors, lint.warnings = [], []
        lint.check_books(pages)
        self.assertEqual(lint.errors, [])

    def test_idempotent(self):
        mig.apply(self.root)
        snap = {fn: read(self.root, f"wiki/{fn}") for fn in os.listdir(os.path.join(self.root, "wiki"))}
        again = mig.apply(self.root)
        self.assertEqual(again["books"], 0)
        self.assertEqual({fn: read(self.root, f"wiki/{fn}") for fn in os.listdir(os.path.join(self.root, "wiki"))}, snap)

    def test_unreadable_table_is_left_alone(self):
        write(self.root, "wiki/book-2010-tiny-fields.md", BOOK.replace("| 31–60 |", "| soon |"))
        report = mig.apply(self.root)
        self.assertIn("book-2010-tiny-fields", report["skipped"])
        self.assertIn("## Partition", read(self.root, "wiki/book-2010-tiny-fields.md"))

    def test_produces_the_current_schema(self):
        from kb_distillery.vault.schema import SCHEMA_VERSION
        self.assertEqual(mig.PRODUCES, SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()

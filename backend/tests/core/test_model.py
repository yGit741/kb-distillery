"""The data model: format folders × collection membership × type-prefixed slugs."""
import os
import sys
import unittest
from unittest import mock

from kb.lint import lint
from kb.core import schema
from kb.ingest import catalog


def page(slug, text):
    return (f"wiki/{slug}.md", lint.parse_frontmatter(text), text)


COURSE = """---
type: course
status: to-read
---

# RL

## Overview

A long enough paragraph about what this course is, how it is organised, and why it matters
for the thesis, so the overview check passes.

## Contents

Coverage: **0 / 2 items (0%)** · skip rows excluded

| # | Item | Raw | Status | Note |
|---|------|-----|--------|------|
| 1 | Lecture 1 | `raw/presentations/rl-01.pdf` | — | |
| 2 | Lecture 2 | `raw/presentations/rl-02.pdf` | — | |
| 3 | Scratch | `raw/handwritten/rl-scratch.pdf` | skip | |
"""


def run(fn, *args):
    lint.errors, lint.warnings = [], []
    out = fn(*args)
    return out, list(lint.errors), list(lint.warnings)


class SlugTest(unittest.TestCase):
    def check(self, slug, t):
        _o, errs, _w = run(lint._check_slug, f"wiki/{slug}.md", slug, t)
        return errs

    def test_prefix_matches_type(self):
        self.assertEqual(self.check("paper-2023-toolformer", "paper"), [])
        self.assertEqual(self.check("course-openu-rl", "course"), [])
        self.assertEqual(self.check("tensor-rank", "concept"), [])
        self.assertTrue(self.check("2023-toolformer", "paper"))
        self.assertTrue(self.check("paper-tensor-rank", "concept"))
        self.assertTrue(self.check("theme-quantum", "course"))

    def test_make_and_strip(self):
        self.assertEqual(schema.make_slug("book", "2014-x"), "book-2014-x")
        self.assertEqual(schema.make_slug("book", "book-2014-x"), "book-2014-x")
        self.assertEqual(schema.strip_prefix("part-2014-x-ch1"), "2014-x-ch1")

    def test_unit_type_from_format(self):
        u = schema.unit_slug_for_raw
        self.assertEqual(u("raw/printed-docs/2023-toolformer.pdf"), "paper-2023-toolformer")
        self.assertEqual(u("raw/presentations/rl-lecture-01-intro.pdf"), "lecture-rl-01-intro")
        self.assertEqual(u("raw/emails/2020-11-08-re/thread.md"), "mail-2020-11-08-re")
        self.assertEqual(u("raw/web-clips/2017-rowspace.md"), "article-2017-rowspace")

    def test_member_name_is_unique_and_kebab(self):
        self.assertEqual(catalog.member_name("Lecture 3 - .pdf", "course-openu-rl"),
                         "openu-rl-lecture-3.pdf")
        self.assertEqual(catalog.member_name("GPT2 .pdf", ""), "gpt2.pdf")


class DigestionStatusTest(unittest.TestCase):
    def wiki(self, fm):
        text = "---\n" + fm + "\n---\n\n# T\n"
        with mock.patch.object(lint, "walk", return_value=["wiki/paper-2000-x.md"]), \
                mock.patch("builtins.open", mock.mock_open(read_data=text)), \
                mock.patch.object(lint.os.path, "exists", return_value=True):
            _p, errs, _w = run(lint.check_wiki)
        return errs

    def test_required_and_consistent(self):
        base = "type: paper\nraw: raw/printed-docs/2000-x.pdf\n"
        self.assertTrue(any("requires `depth:`" in e
                            for e in self.wiki(base + "status: to-read")))
        self.assertTrue(any("status must be to-read" in e
                            for e in self.wiki(base + "status: digested\ndepth: listed")))
        self.assertTrue(any("status must be digested" in e
                            for e in self.wiki(base + "status: to-read\ndepth: easy")))
        self.assertFalse(any("digestion" in e
                             for e in self.wiki(base + "status: digested\ndepth: full")))


class CollectionTest(unittest.TestCase):
    def pages(self):
        return {"course-openu-rl": page("course-openu-rl", COURSE),
                "nadav-cohen": page("nadav-cohen", "---\ntype: person\nstatus: seed\n---\n"),
                "tensor-rank": page("tensor-rank", "---\ntype: concept\nstatus: seed\n---\n")}

    def rows(self, **extra):
        rows = {p: {"path": p, "disposition": "queued", "collection": "course-openu-rl"}
                for p in ("raw/presentations/rl-01.pdf", "raw/presentations/rl-02.pdf",
                          "raw/handwritten/rl-scratch.pdf")}
        rows.update(extra)
        return rows

    def check(self, rows):
        tables, _e, _w = run(lint.check_contents, self.pages())
        self.assertEqual(_e, [])
        _o, errs, _w = run(lint.check_collections, self.pages(), tables, rows)
        return errs

    def test_table_matches_collection(self):
        self.assertEqual(self.check(self.rows()), [])

    def test_member_missing_from_table(self):
        extra = {"raw/presentations/rl-03.pdf": {"path": "raw/presentations/rl-03.pdf",
                                                 "disposition": "queued",
                                                 "collection": "course-openu-rl"}}
        self.assertTrue(any("rl-03.pdf" in e for e in self.check(self.rows(**extra))))

    def test_listed_but_not_a_member(self):
        rows = self.rows()
        rows["raw/presentations/rl-02.pdf"]["collection"] = ""
        self.assertTrue(any("rl-02.pdf" in e and "does not name" in e for e in self.check(rows)))

    def test_collection_must_be_hub_or_person(self):
        extra = {"raw/printed-docs/2000-x.pdf": {"path": "raw/printed-docs/2000-x.pdf",
                                                 "disposition": "queued",
                                                 "collection": "nadav-cohen,tensor-rank,nope"}}
        errs = self.check(self.rows(**extra))
        self.assertTrue(any("'tensor-rank' is a concept page" in e for e in errs))
        self.assertTrue(any("'nope' is not a wiki page" in e for e in errs))
        self.assertFalse(any("nadav-cohen" in e for e in errs))


class ReconcileTest(unittest.TestCase):
    def test_table_row_overrides_stale_skip(self):
        manifest = {
            "raw/presentations/rl-01.pdf": {"path": "raw/presentations/rl-01.pdf", "sha1": "a",
                                            "kind": "presentations", "disposition": "skip",
                                            "slug": "", "collection": "course-openu-rl"},
            "raw/handwritten/rl-scratch.pdf": {"path": "raw/handwritten/rl-scratch.pdf",
                                               "sha1": "b", "kind": "handwritten",
                                               "disposition": "queued", "slug": "",
                                               "collection": "course-openu-rl"},
        }
        files = sorted(manifest)
        with mock.patch.object(lint, "read_manifest", return_value=manifest), \
                mock.patch.object(lint, "write_manifest"), \
                mock.patch.object(lint, "sha1", side_effect=lambda r: manifest[r]["sha1"]):
            rows, _ms = lint.reconcile(files, set(), set(files), {}, {},
                                       {"raw/presentations/rl-01.pdf": "—",
                                        "raw/handwritten/rl-scratch.pdf": "skip"})
        self.assertEqual(rows["raw/presentations/rl-01.pdf"]["disposition"], "queued")
        self.assertEqual(rows["raw/handwritten/rl-scratch.pdf"]["disposition"], "skip")
        self.assertEqual(rows["raw/presentations/rl-01.pdf"]["collection"], "course-openu-rl")


if __name__ == "__main__":
    unittest.main()

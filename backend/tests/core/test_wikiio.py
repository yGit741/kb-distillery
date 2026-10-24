#!/usr/bin/env python3
"""backend/src/kb/core/wikiio.py and the writers routed through it: a body-touching front-matter write raises,
and the reserved `## My notes` survives every writer that patches or regenerates a page."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.core import wikiio

NOTES = "## My notes\n\nMine — never overwritten. Ask about $\\{x\\}$ on Tuesday.\n"
PAGE = "---\ntype: concept\nstatus: seed\n---\n\n# T\n\n## Connections\n- [[a]]\n\n" + NOTES


class WikiioUnit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kb-wikiio-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "t.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(PAGE)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_split(self):
        fm, body = wikiio.split_page(PAGE)
        self.assertEqual(fm, "---\ntype: concept\nstatus: seed\n---\n")
        self.assertEqual(fm + body, PAGE)
        self.assertEqual(wikiio.split_page("no front matter\n"), ("", "no front matter\n"))

    def test_front_matter_write_keeps_body(self):
        self.assertTrue(wikiio.write_front_matter(self.path, ["type: idea", "layer: concept", "status: seed"]))
        self.assertEqual(self.read(), PAGE.replace("type: concept\n", "type: idea\nlayer: concept\n"))

    def test_body_touching_write_raises(self):
        for bad in ("---\ntype: x\n---\n\nextra body\n---\n", "type: x\n---\n\nsmuggled"):
            with self.assertRaises(wikiio.BodyChanged):
                wikiio.write_front_matter(self.path, bad)
        self.assertEqual(self.read(), PAGE)                       # nothing written

    def test_set_key_only_front_matter(self):
        text = "---\ntype: paper\nstatus: to-read\n---\n\nstatus: a body line\n"
        out = wikiio.set_key(text, "status", "digested")
        self.assertEqual(out, "---\ntype: paper\nstatus: digested\n---\n\nstatus: a body line\n")
        out = wikiio.set_key(text, "depth", "easy", after="status")
        self.assertEqual(out.split("---\n")[1], "type: paper\nstatus: to-read\ndepth: easy\n")

    def test_preserve_my_notes(self):
        regenerated = "---\ntype: concept\n---\n\n# T\n\n## New section\nx\n"
        out = wikiio.preserve_my_notes(PAGE, regenerated)
        self.assertTrue(out.endswith(NOTES))
        self.assertEqual(out.count("## My notes"), 1)
        moved = "---\ntype: concept\n---\n\n# T\n\n" + NOTES + "\n## Appended\nlate\n"
        out = wikiio.preserve_my_notes(PAGE, moved)
        self.assertTrue(out.endswith(NOTES))
        self.assertIn("## Appended\nlate", out)
        self.assertEqual(wikiio.preserve_my_notes("---\na: 1\n---\nx\n", regenerated), regenerated)

    def test_write_page_keeps_notes(self):
        wikiio.write_page(self.path, "---\ntype: concept\n---\n\n# Rewritten\n")
        self.assertTrue(self.read().endswith(NOTES))
        self.assertIn("# Rewritten", self.read())

    def test_lint_rule(self):
        self.assertEqual(wikiio.check_my_notes(PAGE), [])
        self.assertTrue(wikiio.check_my_notes(PAGE + "\n## After\n"))
        self.assertTrue(wikiio.check_my_notes(PAGE + "\n" + NOTES))


class WritersKeepNotes(unittest.TestCase):
    """Each page writer, run on a page carrying `## My notes`, leaves the section intact and last."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-writers-")
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("wiki", "meta", "raw/printed-docs"):
            os.makedirs(os.path.join(self.root, d))

    def w(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def r(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def assertNotesKept(self, rel):
        text = self.r(rel)
        self.assertTrue(text.endswith(NOTES), text[-300:])
        self.assertEqual(text.count("## My notes"), 1)
        self.assertEqual(wikiio.check_my_notes(text), [])

    def test_theme_papers_update(self):
        from kb.ingest import session
        self.w("wiki/theme-x.md", "---\ntype: theme\nstatus: seed\n---\n\n# X\n\n## Scope\n\ns\n\n" + NOTES)
        with patch.object(session, "ROOT", self.root):
            session._apply_moc_updates({"moc_updates": [{"moc": "theme-x", "link": "paper-y"}]})
        self.assertIn("## Papers\n\n- [[paper-y]]", self.r("wiki/theme-x.md"))
        self.assertNotesKept("wiki/theme-x.md")

    def test_finalize_overwriting_an_existing_concept(self):
        from tests.ingest.test_digest_robustness import Vault
        from kb.ingest import session, paths

        class V(Vault):
            def runTest(self):
                pass
        v = V()
        v.setUp()
        self.addCleanup(v.doCleanups)
        v.w("wiki/tensor-rank.md", PAGE)
        sha = session.begin(v.raw)
        v.w(f"meta/.ingest/{sha}/plan.json", json.dumps({"wiki_slug": "paper-x", "type": "paper"}))
        v.w(f"meta/.ingest/{sha}/staging/tensor-rank.md", "---\ntype: concept\nstatus: seed\n---\n\n# Redrafted\n")
        with patch.object(session, "validate_plan", lambda p: None), \
                patch.object(session, "_record_book_part", lambda *a: None), \
                patch.object(session, "_record_hub_row", lambda *a: None), \
                patch.object(session, "_append_log", lambda *a: None), \
                patch.object(session.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = run.return_value.stderr = ""
            self.assertEqual(session.finalize(sha), 0)
        text = v.r("wiki/tensor-rank.md")
        self.assertIn("# Redrafted", text)
        self.assertTrue(text.endswith(NOTES))
        self.assertEqual(paths.load_session(sha)["status"], "closed")

    def test_course_hub_table_and_status(self):
        from kb.ingest import course, paths
        hub = ("---\ntype: course\nshort: t\nstatus: to-read\n---\n\n# C\n\n## Overview\n\nx\n\n"
               "## Contents\n\n| # | Item | Raw | Status | Note |\n|---|------|-----|--------|------|\n\n" + NOTES)
        self.w("wiki/course-t.md", hub)
        self.w("meta/corpus.tsv", "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n")
        with patch.object(course, "ROOT", self.root), patch.object(paths, "ROOT", self.root), \
                patch.object(course, "set_collection", lambda *a: None):
            course.add_member("course-t", "raw/printed-docs/t-a.pdf", "A")
            course.record_row("course-t", ["raw/printed-docs/t-a.pdf"], "lecture-t-a", "easy")
        text = self.r("wiki/course-t.md")
        self.assertIn("[[lecture-t-a]]", text)
        self.assertNotesKept("wiki/course-t.md")

    def test_person_regenerated(self):
        from kb.ingest import researcher
        self.w("wiki/ada.md", "---\ntype: person\n---\n\n# Ada\n\n## Why it matters here\n\n- [[theme-x]]\n\n" + NOTES)
        with patch.object(researcher, "ROOT", self.root), patch.object(researcher, "wiki_slugs", lambda: set()):
            researcher._write_person_wiki({"slug": "ada", "name": "Ada"})
        self.assertNotesKept("wiki/ada.md")
        self.assertIn("## Why it matters here", self.r("wiki/ada.md"))

    def test_distill_apply(self):
        from kb.distill import apply as dapply
        self.w("wiki/q-x.md", "---\ntype: question\nstatus: open\n---\n\n# Q\n\n## Threads\n\n- a\n\n" + NOTES)
        with patch.object(dapply, "ROOT", self.root):
            dapply.apply_proposal({"target": "wiki/q-x.md", "action": "append_papers", "text": "- [[paper-z]]"})
            dapply.apply_proposal({"target": "wiki/q-x.md", "action": "append_threads", "text": "- b"})
        text = self.r("wiki/q-x.md")
        self.assertIn("[[paper-z]]", text)
        self.assertIn("- b", text)
        self.assertNotesKept("wiki/q-x.md")

    def test_backfill_field_edit(self):
        from kb.ingest import backfill
        body = "\n# P\n\nurl: this body line is not front matter\n\n" + NOTES
        self.w("wiki/paper-p.md", "---\ntype: paper\nurl:\n---\n" + body)
        backfill._set_field(os.path.join(self.root, "wiki/paper-p.md"), backfill.FM_URL, "url: https://x.org")
        self.assertEqual(self.r("wiki/paper-p.md"), "---\ntype: paper\nurl: https://x.org\n---\n" + body)

    def test_easy_digest_status_edit(self):
        from kb.ingest import easy_digest
        body = "\n# P\n\nstatus: a body line\n\n" + NOTES
        self.w("wiki/paper-p.md", "---\ntype: paper\nstatus: to-read\ndepth: catalog\n---\n" + body)
        with patch.object(easy_digest, "ROOT", self.root):
            easy_digest._update_wiki_digestion("paper-p", "raw/printed-docs/p.pdf")
        self.assertEqual(self.r("wiki/paper-p.md"),
                         "---\ntype: paper\nstatus: digested\ndepth: easy\n---\n" + body)


if __name__ == "__main__":
    unittest.main()

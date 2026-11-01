"""easy-digest batch options (--into a series page, --no-tick, --no-lint) and lint's partial
checkout: a clone without the gitignored raw binaries keeps their manifest rows."""
import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.lint import lint
from kb_distillery.ingest import easy_digest


class AddRawTests(unittest.TestCase):
    def test_scalar_becomes_list_and_list_appends_once(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "page.md")
            open(p, "w").write("---\ntype: article\nstatus: to-read\nraw: raw/web-clips/a.md\n---\n# T\n")
            easy_digest._add_raw(p, "raw/web-clips/b.md")
            self.assertIn("raw: [raw/web-clips/a.md, raw/web-clips/b.md]", open(p).read())
            easy_digest._add_raw(p, "raw/web-clips/b.md")             # idempotent
            self.assertEqual(open(p).read().count("raw/web-clips/b.md"), 1)
            easy_digest._add_raw(p, "raw/web-clips/c.md")
            self.assertIn("raw: [raw/web-clips/a.md, raw/web-clips/b.md, raw/web-clips/c.md]", open(p).read())
        finally:
            shutil.rmtree(d)


class PartialCheckoutTests(unittest.TestCase):
    def test_detection_needs_several_missing_binaries(self):
        d = tempfile.mkdtemp()
        try:
            old_root, lint.ROOT = lint.ROOT, d
            rows = {f"raw/printed-docs/{i}.pdf": {} for i in range(4)}
            rows["raw/web-clips/a.md"] = {}                       # text, never counts
            self.assertFalse(lint.partial_checkout(rows))         # 4 missing: a deletion, reconcile normally
            rows["raw/images/x-01.png"] = {}
            self.assertTrue(lint.partial_checkout(rows))          # 5 missing binaries: a partial checkout
        finally:
            lint.ROOT = old_root
            shutil.rmtree(d)

    def test_missing_binaries_keep_their_rows_and_sha1(self):
        rows_before = {
            "raw/printed-docs/2020-x.pdf": {"path": "raw/printed-docs/2020-x.pdf", "sha1": "abc", "kind": "printed-docs",
                                           "disposition": "digested", "slug": "paper-2020-x", "collection": ""},
            "raw/images/clip-01.png": {"path": "raw/images/clip-01.png", "sha1": "def", "kind": "images",
                                       "disposition": "asset:raw/web-clips/clip.md", "slug": "", "collection": ""},
            "raw/web-clips/clip.md": {"path": "raw/web-clips/clip.md", "sha1": "", "kind": "web-clips",
                                      "disposition": "queued", "slug": "", "collection": "series-x"},
        }
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "raw", "web-clips"))
            os.makedirs(os.path.join(d, "meta"))
            open(os.path.join(d, "raw", "web-clips", "clip.md"), "w").write("x")
            old_root, lint.ROOT = lint.ROOT, d
            lint.write_manifest(rows_before)
            on_disk = ["raw/web-clips/clip.md"]
            missing = {"raw/printed-docs/2020-x.pdf", "raw/images/clip-01.png"}
            rows, _ms = lint.reconcile(sorted(set(on_disk) | missing), set(), set(on_disk) | missing,
                                       missing=missing)
            self.assertEqual(set(rows), set(rows_before))                 # nothing dropped
            self.assertEqual(rows["raw/printed-docs/2020-x.pdf"]["sha1"], "abc")
            self.assertEqual(rows["raw/printed-docs/2020-x.pdf"]["disposition"], "digested")   # not re-queued
            self.assertEqual(rows["raw/images/clip-01.png"]["disposition"], "asset:raw/web-clips/clip.md")
            self.assertTrue(rows["raw/web-clips/clip.md"]["sha1"])        # the on-disk file was hashed
        finally:
            lint.ROOT = old_root
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()

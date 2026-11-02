"""Tests for src/kb_distillery/search/explore_raw.py: a tiny temp vault, explore_raw.ROOT and the index patched."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery.search import explore_raw

CLIP = "raw/web-clips/2024-hypercontractivity-note.md"
OTHER = "raw/printed-docs/2020-unrelated-topic.pdf"
PAGE = """---
type: article
maturity: digested
depth: full
---
# Page

## Takeaways for my thesis
- hypercontractivity matters

## Connections
- [[theme-fourier-analysis]]
"""


def row(path, disp, slug="", coll=""):
    return {"path": path, "sha1": "abcdef1234567890", "kind": "web-clips", "disposition": disp,
            "slug": slug, "collection": coll}


class ExploreRawTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        os.makedirs(os.path.join(r, "raw/web-clips"))
        os.makedirs(os.path.join(r, "wiki"))
        with open(os.path.join(r, CLIP), "w") as f:
            f.write("---\ntitle: x\n---\nHypercontractivity bounds noise operators on the cube.\n")
        with open(os.path.join(r, "wiki/article-hyper.md"), "w") as f:
            f.write(PAGE)
        rows = {CLIP: row(CLIP, "queued"), OTHER: row(OTHER, "digested", "article-hyper"),
                "raw/images/a-01.png": row("raw/images/a-01.png", "asset:" + CLIP)}
        for patch in (mock.patch.object(explore_raw, "ROOT", r),
                      mock.patch.object(explore_raw, "_manifest", lambda: rows),
                      mock.patch.object(explore_raw, "_index", lambda: {"article-hyper": {"status": "digested", "summary": "noise"}}),
                      mock.patch.object(explore_raw, "_hub_rows", lambda p: [])):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = explore_raw.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_find_marks_undigested_and_skips_assets(self):
        code, out, _ = self.run_cli("find", "hypercontractivity", "cube")
        self.assertEqual(code, 0)
        line = [l for l in out.splitlines() if CLIP in l][0]
        self.assertIn("UNDIGESTED", line)
        self.assertNotIn("a-01.png", out)

    def test_read_refuses_inbox_and_unknown(self):
        code, _, err = self.run_cli("read", "raw/inbox/x.pdf")
        self.assertEqual(code, 2)
        self.assertIn("catalog first", err)
        self.assertEqual(self.run_cli("read", "raw/web-clips/nope.md")[0], 2)

    def test_read_clip_prints_header_and_text(self):
        code, out, _ = self.run_cli("read", CLIP)
        self.assertEqual(code, 0)
        self.assertIn("UNDIGESTED", out)
        self.assertIn("Hypercontractivity bounds", out)

    def test_check_prints_source_and_page(self):
        code, out, _ = self.run_cli("check", CLIP, "--pages-of", "article-hyper")
        self.assertEqual(code, 0)
        self.assertIn("=== SOURCE ===", out)
        self.assertIn("=== PAGE article-hyper ===", out)
        self.assertIn("hypercontractivity matters", out)

    def test_recommend_ends_with_tiers(self):
        code, out, _ = self.run_cli("recommend", CLIP)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines()[-1], explore_raw.TIERS)


if __name__ == "__main__":
    unittest.main()

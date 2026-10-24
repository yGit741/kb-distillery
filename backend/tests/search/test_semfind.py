#!/usr/bin/env python3
"""Tests for backend/src/kb/search/semfind.py and backend/src/kb/core/graph.py."""
import os
import sys
import unittest

from kb.core.graph import one_hop, score_pair


def _page(slug, links):
    text = f"""---
type: idea
layer: concept
related: [{", ".join(links)}]
---

# {slug}

## One-liner

Concept about tensor rank and margin maximization.
"""
    return (f"wiki/{slug}.md", {"type": "idea", "related": links}, text)


class SemfindGraphTest(unittest.TestCase):
    def test_one_hop(self):
        pages = {
            "seed": _page("seed", ["neighbor"]),
            "neighbor": _page("neighbor", ["seed"]),
            "far": _page("far", []),
        }
        hop = one_hop("seed", pages)
        self.assertIn("neighbor", hop)
        self.assertNotIn("far", hop)

    def test_score_pair_positive(self):
        pages = {
            "a": _page("a", []),
            "b": _page("b", []),
        }
        self.assertGreater(score_pair("a", "b", pages), 0)

    def test_moc_session_id(self):
        import tempfile
        from kb.lint import lint as lint_mod
        from kb.search import semfind as sf

        with tempfile.TemporaryDirectory() as tmp:
            old_lint_root = lint_mod.ROOT
            old_sf_root = sf.ROOT
            old_semfind = sf.SEMFIND_DIR
            try:
                lint_mod.ROOT = tmp
                sf.ROOT = tmp
                sf.SEMFIND_DIR = os.path.join(tmp, "meta", ".semfind")
                pages_dir = os.path.join(tmp, "wiki")
                os.makedirs(pages_dir)
                for slug in ("moc-test", "concept-a"):
                    with open(os.path.join(pages_dir, f"{slug}.md"), "w") as f:
                        f.write(_page(slug, ["moc-test" if slug == "concept-a" else "concept-a"])[2])
                rc = sf.build_bundle(
                    ["wiki/moc-test.md"],
                    "moc:moc-test",
                    session_id="moc-moc-test",
                )
                self.assertEqual(rc, 0)
                self.assertTrue(os.path.isfile(
                    os.path.join(sf.SEMFIND_DIR, "moc-moc-test", "bundle.md")))
            finally:
                lint_mod.ROOT = old_lint_root
                sf.ROOT = old_sf_root
                sf.SEMFIND_DIR = old_semfind


if __name__ == "__main__":
    unittest.main()

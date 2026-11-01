import os
import sys
import os
import unittest

from kb_distillery.services.pipeline import build_digestion_snapshot


class DigestionDataTest(unittest.TestCase):
    def test_build_snapshot(self):
        snap = build_digestion_snapshot()
        for key in ("generated_at", "server", "summary", "items", "inbox", "collections",
                    "titles", "active_ingest", "coherence", "distill_review", "shallow_papers"):
            self.assertIn(key, snap)

        summary = snap["summary"]
        for key in ("files", "queued", "queued_units", "queued_mb", "inbox_count", "depth",
                    "coherence_open", "active_ingest", "distill_review", "shallow_papers",
                    "collections_open"):
            self.assertIn(key, summary)
        self.assertEqual(summary["files"], len(snap["items"]))
        self.assertIsInstance(summary["queued_mb"], float)

        for item in snap["items"][:20]:
            for key in ("path", "kind", "collections", "unit", "status", "depth", "slug",
                        "size_kb", "next"):
                self.assertIn(key, item)
            self.assertNotIn(":", item["status"])           # dupe:/ink: targets split out

        for c in snap["collections"]:
            for key in ("slug", "type", "covered", "total", "unit", "rows"):
                self.assertIn(key, c)

        # two status models: every non-companion item has exactly one ingestion value, and a
        # digestion value exactly when it is cataloged; companions never count on their own
        parents = [i for i in snap["items"] if not i["companion_of"]]
        self.assertEqual(sum(summary["ingestion"].values()), len(parents))
        self.assertEqual(sum(summary["digestion"].values()), summary["ingestion"]["cataloged"])
        for item in snap["items"]:
            self.assertEqual(bool(item["digestion"]), item["ingestion"] == "cataloged")
            if item["status"] in ("ink", "dupe", "asset"):
                self.assertTrue(item["companion_of"], "an overlay/duplicate/figure must fold into its parent")
                self.assertNotEqual(item["unit"], item["path"])

        if snap["coherence"]:
            row = snap["coherence"][0]
            for key in ("id", "kind", "score", "slugs", "summary"):
                self.assertIn(key, row)

    def test_a_figure_folds_into_its_clip(self):
        """`asset:<clip>` rows (figures downloaded with a web clip) are companions like ink
        overlays: they fold into the clip's unit and never count as uncataloged on their own."""
        from kb_distillery.services.pipeline import _items
        rows = {
            "raw/web-clips/ex-post.md": {"path": "raw/web-clips/ex-post.md", "kind": "web-clips",
                                         "disposition": "queued", "slug": "", "collection": "series-ex"},
            "raw/images/ex-post-01.png": {"path": "raw/images/ex-post-01.png", "kind": "images",
                                          "disposition": "asset:raw/web-clips/ex-post.md", "slug": "",
                                          "collection": ""},
        }
        items = {i["path"]: i for i in _items(rows, {}, [], 0.0, cataloged={"raw/web-clips/ex-post.md"})}
        fig = items["raw/images/ex-post-01.png"]
        self.assertEqual(fig["status"], "asset")
        self.assertEqual(fig["companion_of"], "raw/web-clips/ex-post.md")
        self.assertEqual(fig["unit"], "raw/web-clips/ex-post.md")
        self.assertFalse(items["raw/web-clips/ex-post.md"]["companion_of"])

    def test_clip_source_url_from_frontmatter(self):
        """A Markdown raw file's frontmatter `url:` is surfaced so the preview can link to the
        original page; other files and clips without one get an empty string."""
        import tempfile
        from kb_distillery.services import pipeline as digestion_data
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw", "web-clips"))
            with open(os.path.join(tmp, "raw", "web-clips", "post.md"), "w", encoding="utf-8") as f:
                f.write('---\ntitle: "A post"\nurl: https://example.com/a-post/\ndate: 2020-01-01\n---\n# A post\n')
            with open(os.path.join(tmp, "raw", "web-clips", "plain.md"), "w", encoding="utf-8") as f:
                f.write("# no frontmatter\nurl: https://example.com/not-frontmatter\n")
            old = digestion_data.ROOT
            digestion_data.ROOT = tmp
            try:
                self.assertEqual(digestion_data._source_url("raw/web-clips/post.md", ".md"), "https://example.com/a-post/")
                self.assertEqual(digestion_data._source_url("raw/web-clips/plain.md", ".md"), "")
                self.assertEqual(digestion_data._source_url("raw/printed-docs/x.pdf", ".pdf"), "")
            finally:
                digestion_data.ROOT = old


if __name__ == "__main__":
    unittest.main()

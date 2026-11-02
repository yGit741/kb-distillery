import os
import sys
import unittest

from kb_distillery.graph.snapshot import build_graph_snapshot


class GraphDataTest(unittest.TestCase):
    def test_build_snapshot(self):
        snap = build_graph_snapshot()
        self.assertIn("nodes", snap)
        self.assertIn("links", snap)
        self.assertIn("etag", snap)
        self.assertGreater(len(snap["nodes"]), 10)
        node = snap["nodes"][0]
        for key in ("id", "type", "inDegree", "outDegree", "path"):
            self.assertIn(key, node)
        if snap["links"]:
            link = snap["links"][0]
            self.assertIn("source", link)
            self.assertIn("target", link)

    def test_default_snapshot_has_no_raw_layer(self):
        snap = build_graph_snapshot()
        for key in ("raw_nodes", "raw_links", "piles", "pile_links", "layer"):
            self.assertNotIn(key, snap)

    def test_raw_layer_piles_match_manifest(self):
        from collections import Counter
        from kb_distillery.lint.lint import read_manifest
        snap = build_graph_snapshot(layer="raw")
        want = Counter(r["kind"] for r in read_manifest().values() if r["disposition"] != "sidecar")
        got = {p["format"]: p["count"] for p in snap["piles"] if p["count"]}
        self.assertEqual(got, dict(want))
        ids = {n["id"] for n in snap["raw_nodes"]}
        self.assertEqual(len(ids), sum(want.values()))
        for l in snap["raw_links"]:
            self.assertIn(l["source"], ids)
            if l["kind"] in ("asset", "ink", "dupe"):
                self.assertIn(l["target"], ids)
        self.assertNotEqual(snap["etag"], build_graph_snapshot()["etag"])


if __name__ == "__main__":
    unittest.main()

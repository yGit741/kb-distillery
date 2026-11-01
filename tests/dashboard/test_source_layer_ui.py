#!/usr/bin/env python3
"""S7 graph UI data: every node carries its layer, /api/schema drives the JS (concepts by default,
person off), concepts that share sources get counted edges, and the static JS keeps no type lists."""
import os
import re
import sys
import unittest

from kb_distillery.paths import CODE_DIR, vault_root
META = os.path.join(vault_root(), "meta")
from kb_distillery.core import schema
from kb_distillery.services import graph as graph_data
from kb_distillery.services.schema import schema_payload

STATIC = os.path.join(CODE_DIR, "dashboard", "static")


class ConceptLinks(unittest.TestCase):
    def test_shared_sources_are_counted_once_per_source(self):
        nodes = [{"id": "a", "layer": "concept"}, {"id": "b", "layer": "concept"}, {"id": "c", "layer": "concept"},
                 {"id": "p1", "layer": "source"}, {"id": "p2", "layer": "source"}, {"id": "k", "layer": "collection"}]
        links = [{"source": "p1", "target": "a"}, {"source": "p1", "target": "b"}, {"source": "b", "target": "p1"},
                 {"source": "a", "target": "p2"}, {"source": "p2", "target": "b"}, {"source": "p2", "target": "c"},
                 {"source": "k", "target": "a"}, {"source": "k", "target": "c"}]   # a collection is no source
        got = graph_data.concept_links(nodes, links)
        self.assertEqual(got, [{"source": "a", "target": "b", "shared": 2},
                               {"source": "a", "target": "c", "shared": 1},
                               {"source": "b", "target": "c", "shared": 1}])

    def test_real_snapshot(self):
        snap = graph_data.build_graph_snapshot()
        self.assertTrue(all(n["layer"] in schema.LAYERS for n in snap["nodes"]))
        ids = {n["id"]: n for n in snap["nodes"]}
        for l in snap["concept_links"]:
            self.assertEqual(ids[l["source"]]["layer"], "concept")
            self.assertEqual(ids[l["target"]]["layer"], "concept")
            self.assertGreaterEqual(l["shared"], 1)
        self.assertEqual(snap["schema"], schema_payload())


class SchemaDrivesTheJs(unittest.TestCase):
    def test_default_view_is_concepts_without_people(self):
        p = schema_payload()
        self.assertEqual(set(p["default_visible"]), schema.CONCEPT_TYPES - {"person"})
        self.assertEqual([t["id"] for t in p["types"]], list(schema.TYPE_ORDER))

    def test_static_js_keeps_no_type_lists(self):
        old = re.compile(r"[\"'](theme|concept)[\"']\s*[:,\]]|READING_UNITS|digestion-status")
        for fn in ("graph.js", "explore.js", "selection.js", "datalayer.js", "graph-shell.js", "digestion.js"):
            with open(os.path.join(STATIC, fn), encoding="utf-8") as f:
                text = f.read()
            self.assertIsNone(old.search(text), fn)
        with open(os.path.join(STATIC, "graph.js"), encoding="utf-8") as f:
            g = f.read()
        self.assertIn('fetch("/api/schema")', g)
        for fn in ("seeSources", "addSharedSourceLinks", "concept_links"):
            self.assertIn(fn, g)
        with open(os.path.join(STATIC, "graph-shell.js"), encoding="utf-8") as f:
            self.assertIn("sources (${k})", f.read())
        with open(os.path.join(STATIC, "explore.js"), encoding="utf-8") as f:
            self.assertIn("See sources (${srcIds.length})", f.read())


if __name__ == "__main__":
    unittest.main()

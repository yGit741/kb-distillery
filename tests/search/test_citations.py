#!/usr/bin/env python3
"""Tests for src/kb_distillery/search/citations.py (no network)."""
import os
import sys
import tempfile
import unittest

from kb_distillery.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.search import citations as C


def P(slug, refs=(), cits=(), title=None):
    return {"slug": slug, "title": title or slug, "year": 2020, "arxiv": None, "doi": None,
            "citationCount": 1, "references": list(refs), "citations": list(cits), "fetched_at": "x"}


def fixture():
    # vault: A B C D ; external: X (cited by A,B,C), Y (cited by A), Z (citing A and B)
    papers = {
        "A": P("a", ["B", "X", "Y"], ["Z"]),
        "B": P("b", ["C", "X"], ["A", "Z"]),
        "C": P("c", ["X"], ["B"]),
        "D": P("d", ["C"], []),
        "X": P(None, title="Ext X"), "Y": P(None, title="Ext Y"), "Z": P(None, title="Ext Z"),
    }
    return {"version": 1, "fetched_at": "x", "papers": papers,
            "slugs": {"a": "A", "b": "B", "c": "C", "d": "D"}, "misses": {}}


class CitationsTest(unittest.TestCase):
    def test_coupling_and_cocitation(self):
        c = fixture()
        self.assertEqual(C.coupling(c, "A"), {"B": 1, "C": 1})
        self.assertEqual(C.cocitation(c, "A"), {"B": 1})

    def test_rank_for_order_and_exclude(self):
        c = fixture()
        rows = C.rank_for(c, "A")
        self.assertEqual(rows[0][0], "b")          # direct (A cites B, B cited by A) + coupling + cocitation
        self.assertEqual([r[0] for r in rows], ["b", "c"])
        self.assertEqual(rows[0][1], 2 * 1 + 1 + 1)
        self.assertEqual([r[0] for r in C.rank_for(c, "A", exclude={"b"})], ["c"])

    def test_missing_for(self):
        c = fixture()
        self.assertEqual(C.missing_for(c), [(3, "X"), (1, "Y")])
        self.assertEqual(C.missing_for(c, ["a"]), [(1, "X"), (1, "Y")])

    def test_shortest_path(self):
        c = fixture()
        self.assertEqual(C.shortest_path(c, "A", "C"), ["A", "B", "C"])
        self.assertIsNone(C.shortest_path(c, "C", "A"))
        self.assertEqual(C.shortest_path(c, "A", "X", any_node=True)[-1], "X")
        self.assertIsNone(C.shortest_path(c, "A", "X"))

    def test_resolve(self):
        c = fixture()
        c["papers"]["B"]["arxiv"] = "2101.00002"
        self.assertEqual(C.resolve(c, "a"), "A")
        self.assertEqual(C.resolve(c, "arXiv:2101.00002"), "B")
        self.assertIsNone(C.resolve(c, "nope"))

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "citations.json")
            self.assertEqual(C.load_cache(path)["papers"], {})
            C.save_cache(fixture(), path)
            self.assertEqual(C.load_cache(path)["slugs"], fixture()["slugs"])
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_fetch_skips_cached(self):
        calls = []

        def http(path, params=None):
            calls.append(path)
            return {"paperId": "P" + str(len(calls)), "title": "t", "year": 2020, "externalIds": {"ArXiv": "1"},
                    "references": [{"paperId": "R", "title": "r", "year": 1}], "citations": []}
        vault = {"a": {"arxiv": "1.1", "doi": None, "s2": None}, "b": {"arxiv": None, "doi": "10.1/x", "s2": None}}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            C.fetch(["a"], http=http, path=path, vault=vault)
            self.assertEqual(len(calls), 1)
            C.fetch(http=http, path=path, vault=vault)          # a cached, b fetched
            self.assertEqual(len(calls), 2)
            self.assertIn("DOI", calls[1])
            C.fetch(http=http, path=path, vault=vault)
            self.assertEqual(len(calls), 2)
            c = C.load_cache(path)
            self.assertEqual(set(c["slugs"]), {"a", "b"})
            self.assertIsNone(c["papers"]["R"]["slug"])


if __name__ == "__main__":
    unittest.main()

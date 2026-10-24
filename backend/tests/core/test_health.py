#!/usr/bin/env python3
"""Tests for backend/src/kb/core/health.py."""
import os
import sys
import unittest

from kb.core.health import (  # noqa: E402
    METRICS,
    bucket_lint_issues,
    compute_orphans,
    estimate_tokens,
    in_degree_buckets,
    index_savings_pct,
    summarize_coherence,
)


class HealthTest(unittest.TestCase):
    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens(""), 0)

    def test_index_savings_pct(self):
        self.assertEqual(index_savings_pct(1000, 100), 90)
        self.assertEqual(index_savings_pct(0, 100), 0)

    def test_in_degree_buckets(self):
        degree = {"a": 0, "b": 1, "c": 3, "theme-x": 0, "log": 0}
        buckets = in_degree_buckets(degree)
        self.assertEqual(buckets["0"], 1)
        self.assertEqual(buckets["1"], 1)
        self.assertEqual(buckets["2+"], 1)

    def test_orphans(self):
        pages = {
            "alone": ("wiki/alone.md", {"type": "concept"}, "text"),
            "hub": ("wiki/hub.md", {"type": "concept"}, "[[alone]]"),
            "theme-test": ("wiki/theme-test.md", {"type": "theme"}, ""),
        }
        self.assertEqual(compute_orphans(pages), ["hub"])

    def test_metrics_have_help(self):
        for mid, meta in METRICS.items():
            self.assertTrue(meta.get("help"), f"{mid} missing help")
            self.assertIn(meta["cluster"], {"integrity", "coherence", "knowledge", "performance", "tokens"})

    def test_summarize_coherence(self):
        merged = {
            "a": {"kind": "internal", "status": "open"},
            "b": {"kind": "external", "status": "open"},
            "c": {"kind": "cosmetic", "status": "open"},
            "d": {"kind": "internal", "status": "fixed"},
            "e": {"kind": "external", "status": "noted"},
            "f": {"kind": "cosmetic", "status": "dismissed"},
        }
        summary = summarize_coherence(merged)
        self.assertEqual(summary["by_kind"]["internal"], 1)
        self.assertEqual(summary["by_kind"]["external"], 1)
        self.assertEqual(summary["by_kind"]["cosmetic"], 1)
        self.assertEqual(summary["by_kind"]["total"], 3)
        self.assertEqual(summary["by_status"]["open"], 3)
        self.assertEqual(summary["by_status"]["fixed"], 1)
        self.assertEqual(summary["by_status"]["noted"], 1)
        self.assertEqual(summary["by_status"]["dismissed"], 1)

    def test_bucket_lint_issues(self):
        errors = ["coherence: [internal] score=80 bad ingestion (a vs b)"]
        warnings = [
            "wiki/foo.md: wikilink [[missing]] resolves to nothing",
            "raw/inbox: 2 files awaiting triage",
            "coherence: [cosmetic] score=20 asymmetric link",
        ]
        buckets = bucket_lint_issues(errors, warnings)
        self.assertEqual(buckets["errors"]["coherence"], 1)
        self.assertEqual(buckets["warnings"]["wiki"], 1)
        self.assertEqual(buckets["warnings"]["inbox"], 1)
        self.assertEqual(buckets["warnings"]["coherence"], 1)


if __name__ == "__main__":
    unittest.main()

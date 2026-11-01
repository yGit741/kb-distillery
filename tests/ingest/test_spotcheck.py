#!/usr/bin/env python3
"""Easy-digest spot checks: a stable ~5% pick and an append-only verdict log."""
import json
import os
import sys
import tempfile
import unittest

from kb_distillery.ingest import spotcheck


class SpotCheck(unittest.TestCase):
    def test_pick_is_stable_and_about_five_percent(self):
        slugs = [f"article-{i}" for i in range(200)]
        a = spotcheck.pick(slugs)
        self.assertEqual(len(a), 10)
        self.assertEqual(a, spotcheck.pick(list(reversed(slugs))))
        self.assertEqual(len(spotcheck.pick(slugs[:3])), 1)          # at least one per batch
        self.assertEqual(spotcheck.pick([]), [])
        self.assertTrue(set(spotcheck.pick(slugs[:100])) <= set(slugs[:100]))

    def test_log_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "easy", "spotcheck.jsonl")
            spotcheck.log("article-a", "ok", path=path)
            spotcheck.log("article-b", "fix", model="opus", note="wrong main result", path=path)
            with self.assertRaises(ValueError):
                spotcheck.log("article-c", "maybe", path=path)
            rows = [json.loads(l) for l in open(path, encoding="utf-8")]
            self.assertEqual([r["verdict"] for r in rows], ["ok", "fix"])
            self.assertEqual(rows[0]["model"], spotcheck.CHECK_MODEL)
            self.assertEqual(spotcheck.status(path), {"ok": 1, "fix": 1})
        self.assertEqual(spotcheck.DEFAULT_MODEL, "haiku")


if __name__ == "__main__":
    unittest.main()

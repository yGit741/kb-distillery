#!/usr/bin/env python3
"""Tests for src/kb_distillery/services/lifecycle.py — live repo smoke test + temp repo with trailers/tags/branches."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.core.schema import SCHEMA_VERSION

V = "%d.%d" % SCHEMA_VERSION  # knowledge versions under the current schema

from kb_distillery.services.lifecycle import build_lifecycle_snapshot

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def g(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=dict(os.environ, **ENV))


class LiveRepoTests(unittest.TestCase):
    def test_snapshot_keys(self):
        snap = build_lifecycle_snapshot(limit=20)
        for key in ("generated_at", "branch", "version", "next_version", "schema", "policy",
                    "working", "timeline", "snapshots", "infra_branches", "stats", "nightly"):
            self.assertIn(key, snap)
        self.assertTrue(snap["timeline"])


class TempRepoTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = self.tmp.name
        g(r, "init", "-q", "-b", "main")
        g(r, "config", "user.name", "t")
        g(r, "config", "user.email", "t@t")
        self._commit("wiki/a.md", f"kb(digest): a (kb-{V}.1)\n\nKB-Version: {V}.1\nKB-Op: digest\nKB-Target: a")
        g(r, "tag", "-a", f"kb-{V}.1", "-m", "week 43")
        g(r, "checkout", "-q", "-b", "infra/tab")
        self._commit("meta/x.py", "feat(dashboard): tab")
        g(r, "checkout", "-q", "main")
        g(r, "merge", "-q", "--no-ff", "-m", "feat(dashboard): tab (#3)", "infra/tab")
        self._commit("wiki/a.md", f"kb(undo): revert {V}.1 a (kb-{V}.2)\n\nKB-Version: {V}.2\nKB-Op: undo\n"
                                  "KB-Target: a\nKB-Reverts: " + self._sha("HEAD^1"))
        g(r, "checkout", "-q", "-b", "infra/next")
        self._commit("meta/y.py", "feat(ops): next")
        g(r, "checkout", "-q", "main")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def _sha(self, rev):
        return subprocess.run(["git", "rev-parse", rev], cwd=self.root, capture_output=True, text=True).stdout.strip()

    def _commit(self, rel, msg):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a") as f:
            f.write("x\n")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", msg)

    def test_parsed_history(self):
        snap = build_lifecycle_snapshot(self.root)
        self.assertEqual(snap["version"], f"{V}.2")
        self.assertEqual(snap["next_version"], f"{V}.3")
        kinds = [(r["kind"], r["kb_version"], r["pr"]) for r in snap["timeline"]]
        self.assertEqual(kinds, [("kb", f"{V}.2", None), ("pr-merge", None, 3), ("kb", f"{V}.1", None)])
        first = snap["timeline"][-1]
        self.assertEqual(first["snapshot_tag"], f"kb-{V}.1")
        self.assertEqual(first["reverted_by"], snap["timeline"][0]["sha"])
        self.assertEqual([s["tag"] for s in snap["snapshots"]], [f"kb-{V}.1"])
        names = {b["name"]: b for b in snap["infra_branches"]}
        self.assertEqual(names["infra/next"]["ahead"], 1)
        self.assertEqual(snap["stats"]["undone"], 1)


if __name__ == "__main__":
    unittest.main()

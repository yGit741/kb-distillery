#!/usr/bin/env python3
"""Tests for src/kb_distillery/maintenance/daily_sync.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.maintenance.daily_sync import (
    commit_message_from_log,
    existing_stage_paths,
    has_open_sessions,
    main,
)


class CommitMessageTests(unittest.TestCase):
    def test_last_log_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "log.md")
            with open(log, "w", encoding="utf-8") as f:
                f.write("## [2026-08-07] setup | Karpathy alignment\n")
                f.write("## [2026-08-13] ingest | info-bottleneck cluster\n")
            self.assertEqual(
                commit_message_from_log(log),
                "ingest | info-bottleneck cluster (2026-08-13)",
            )

    def test_missing_log_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "missing.md")
            msg = commit_message_from_log(log)
            self.assertTrue(msg.startswith("chore: daily sync "))

    def test_log_without_headings_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "log.md")
            with open(log, "w", encoding="utf-8") as f:
                f.write("# Wiki log\n\nNo headings here.\n")
            msg = commit_message_from_log(log)
            self.assertTrue(msg.startswith("chore: daily sync "))


class OpenSessionTests(unittest.TestCase):
    def test_no_sessions_when_dirs_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ingest, distill = has_open_sessions(tmp)
            self.assertEqual(ingest, [])
            self.assertEqual(distill, [])

    def test_open_ingest_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            sha_dir = os.path.join(tmp, "meta", ".ingest", "abc123")
            os.makedirs(sha_dir)
            session = {
                "status": "open",
                "raw": "raw/papers/foo.pdf",
                "sha1": "abc123",
            }
            with open(os.path.join(sha_dir, "session.json"), "w", encoding="utf-8") as f:
                json.dump(session, f)
            ingest, distill = has_open_sessions(tmp)
            self.assertEqual(len(ingest), 1)
            self.assertEqual(ingest[0]["sha1"], "abc123")
            self.assertEqual(distill, [])


class DelegationTests(unittest.TestCase):
    """main() delegates to ops.core.sync; the behaviour itself is tested in test_ops.py."""

    def test_dry_run_and_no_push_are_forwarded(self):
        from kb_distillery.ops import core as ops_core
        with patch.object(ops_core, "sync", return_value=0) as sync:
            self.assertEqual(main(["--dry-run", "--no-push"]), 0)
            sync.assert_called_once_with(push=False, dry_run=True)

    def test_default_pushes(self):
        from kb_distillery.ops import core as ops_core
        with patch.object(ops_core, "sync", return_value=0) as sync:
            main([])
            sync.assert_called_once_with(push=True, dry_run=False)


class StagePathsTests(unittest.TestCase):
    def test_existing_stage_paths_filters_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "wiki"))
            paths = existing_stage_paths(tmp)
            self.assertIn("wiki/", paths)
            self.assertNotIn("think/", paths)

    def test_stage_paths_are_knowledge_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "wiki"))
            os.makedirs(os.path.join(tmp, ".vscode"))
            open(os.path.join(tmp, "pixi.toml"), "w").close()
            paths = existing_stage_paths(tmp)
            self.assertNotIn(".vscode/", paths)
            self.assertNotIn("pixi.toml", paths)


if __name__ == "__main__":
    unittest.main()

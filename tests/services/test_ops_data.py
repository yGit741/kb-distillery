#!/usr/bin/env python3
"""Tests for the Ops dashboard tab: src/kb_distillery/services/ops.py."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.services import ops as ops_data
from kb_distillery.ops import runlog



class History(unittest.TestCase):
    def test_run_log_topped_up_from_the_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "sync.log")
            with open(log, "w") as f:
                f.write("=== Wed Oct 21 22:00:00 IDT 2026\nhygiene: clean (9 checks)\n")
            runlog.append(tmp, {"kind": "nightly", "started": "2026-10-23T22:00:00+03:00", "status": "warn"})
            with patch("kb_distillery.ops.core.NIGHTLY_LOG", log):
                runs = ops_data.run_history(tmp)
        self.assertEqual([(r["status"], r.get("source", "runlog")) for r in runs], [("warn", "runlog"), ("ok", "log")])
        self.assertEqual(ops_data._run_summary(runs[1])["source"], "log")


if __name__ == "__main__":
    unittest.main()

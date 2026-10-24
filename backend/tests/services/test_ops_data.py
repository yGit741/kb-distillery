#!/usr/bin/env python3
"""Tests for the Ops dashboard tab: backend/src/kb/services/ops.py and ops_routes.py."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.paths import vault_root
ROOT = vault_root()

from kb.dashboard import ops_routes
from kb.services import ops as ops_data
from kb.dashboard.shell import TABS
from kb.ops import runlog
from kb.report import model as m

DOC = m.Doc("t", "ok", "All clear", [m.Section("", [m.Banner("ok", "All clear")])]).as_dict()
SNAP = {"subject": "[thesis-kb] ✓ all clear", "doc": DOC, "threads": [], "runs": [], "log": "", "hygiene": {}}


class FakeHandler:
    def __init__(self):
        self.out = []

    def _respond(self, code, body, ctype):
        self.out.append((code, body, ctype))


class Routes(unittest.TestCase):
    def test_tab_is_in_the_nav(self):
        self.assertIn(("ops", "/ops", "Ops"), TABS)

    def test_handles_only_its_paths(self):
        for p in ("/ops", "/api/ops", "/ops/email-preview"):
            self.assertTrue(ops_routes.handles(p))
        self.assertFalse(ops_routes.handles("/lifecycle"))
        self.assertFalse(ops_routes.handle(FakeHandler(), "/elsewhere", {}))

    def test_page_api_and_preview(self):
        h = FakeHandler()
        ops_routes.handle(h, "/ops", {})
        self.assertIn(b'class="app-nav"', h.out[0][1])
        with patch.object(ops_routes, "build_ops_snapshot", return_value=SNAP) as build:
            ops_routes.handle(h, "/api/ops", {"refresh": ["1"]})
        build.assert_called_once_with(refresh=True)
        self.assertEqual(json.loads(h.out[1][1])["subject"], SNAP["subject"])
        with patch.object(ops_data, "build_ops_snapshot", return_value=SNAP):
            ops_routes.handle(h, "/ops/email-preview", {})
        self.assertTrue(h.out[2][1].startswith(b"<!doctype html>"))

    def test_api_error_is_json_not_a_crash(self):
        h = FakeHandler()
        with patch.object(ops_routes, "build_ops_snapshot", side_effect=RuntimeError("git gone")):
            ops_routes.handle(h, "/api/ops", {})
        self.assertEqual(h.out[0][0], 500)
        self.assertIn("git gone", json.loads(h.out[0][1])["error"])


class History(unittest.TestCase):
    def test_run_log_topped_up_from_the_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "sync.log")
            with open(log, "w") as f:
                f.write("=== Wed Oct 21 22:00:00 IDT 2026\nhygiene: clean (9 checks)\n")
            runlog.append(tmp, {"kind": "nightly", "started": "2026-10-23T22:00:00+03:00", "status": "warn"})
            with patch("kb.ops.core.NIGHTLY_LOG", log):
                runs = ops_data.run_history(tmp)
        self.assertEqual([(r["status"], r.get("source", "runlog")) for r in runs], [("warn", "runlog"), ("ok", "log")])
        self.assertEqual(ops_data._run_summary(runs[1])["source"], "log")


if __name__ == "__main__":
    unittest.main()

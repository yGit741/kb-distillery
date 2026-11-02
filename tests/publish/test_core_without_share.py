"""Core runs with no publisher installed: with `kb_distillery.share` blocked at the import system, every module that used to
import it loads, the API app builds, and the share screens say "no publisher configured" instead of crashing.

It runs in a fresh interpreter: blocking in-process would miss a `kb_distillery.share.*` submodule that is already cached."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery.publish.site_state import share_state
from kb_distillery.publish import NullPublisher

SCRIPT = r'''
import importlib, json, sys, tempfile
from importlib.abc import MetaPathFinder

class Block(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "kb_distillery.share" or name.startswith("kb_distillery.share."):
            raise ImportError("kb_distillery.share is blocked: " + name)

sys.meta_path.insert(0, Block())
MODULES = ["kb_distillery.api.app", "kb_distillery.api.routers.share", "kb_distillery.api.spa", "kb_distillery.dashboard.serve", "kb_distillery.git.ship", "kb_distillery.metrics.d1",
           "kb_distillery.ops.core", "kb_distillery.ops.hygiene", "kb_distillery.ops.nightly_report", "kb_distillery.services.ops"]
for m in MODULES:
    importlib.import_module(m)

from fastapi.testclient import TestClient
from kb_distillery.api.app import create_app
out = {}
with TestClient(create_app()) as c:
    r = c.get("/api/share/status")
    out["status_code"], out["body"] = r.status_code, r.json()

from kb_distillery.ops import core, hygiene, nightly_report
from kb_distillery.dashboard import serve
from kb_distillery.metrics import d1
from kb_distillery import publish
tmp = tempfile.mkdtemp()
core.share_autodeploy("test", tmp)
out["orphans"] = [f.kind for f in hygiene.check_snapshots(tmp, None)]
out["site"] = hygiene.check_site(tmp, None)
out["report_site"] = nightly_report.site_status(tmp)
out["log"] = serve.share_log_tail()
try:
    d1._account()
    out["d1"] = "no error"
except publish.PublishError:
    out["d1"] = "PublishError"
except Exception as e:
    out["d1"] = type(e).__name__
out["leaked"] = sorted(m for m in sys.modules if m == "kb_distillery.share" or m.startswith("kb_distillery.share."))
print("RESULT" + json.dumps(out))
'''


class CoreWithoutShare(unittest.TestCase):
    def test_core_loads_and_reports_no_publisher_with_kb_share_blocked(self):
        env = {**os.environ, "KB_PUBLISHER": "", "PYTHONPATH": os.pathsep.join(sys.path)}
        with tempfile.TemporaryDirectory() as tmp:
            env["KB_ENGINE_CONFIG"] = os.path.join(tmp, "none.toml")
            proc = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        out = json.loads(proc.stdout.split("RESULT", 1)[1])
        self.assertEqual(out["status_code"], 200)
        self.assertIsNone(out["body"]["status"])
        self.assertEqual(out["body"]["chip"]["label"], "no publisher")
        self.assertIn("no publisher configured", out["body"]["chip"]["title"])
        self.assertEqual((out["orphans"], out["site"], out["report_site"]), ([], [], {}))
        self.assertIn("no publisher configured", out["log"])
        self.assertEqual(out["d1"], "PublishError")
        self.assertEqual(out["leaked"], [], "core imported kb_distillery.share")


class ShareScreenWithoutPublisher(unittest.TestCase):
    def test_the_chip_says_why_and_the_status_stays_empty(self):
        state = share_state(NullPublisher(reason="no publisher configured: x"))
        self.assertEqual(state["status"], None)
        self.assertEqual(state["chip"], {"label": "no publisher", "cls": "is-skipped",
                                         "title": "share: no publisher configured: x", "href": ""})

    def test_a_publisher_that_raises_counts_as_nothing_published(self):
        pub = mock.Mock(spec=["status"])
        pub.status.side_effect = RuntimeError("boom")
        self.assertEqual(share_state(pub), {"status": None, "chip": None})


if __name__ == "__main__":
    unittest.main()

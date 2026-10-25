#!/usr/bin/env python3
"""wrangler `versions upload` / `versions deploy` helpers: command construction + output parsing
from recorded fixtures (no network, no wrangler)."""
import subprocess
import unittest
from pathlib import Path

from kb.share import contracts, deploy

FIX = Path(__file__).parent / "fixtures"
VID = "3f1c2a9e-7b4d-4e21-9c6a-0d8e5f4b2a17"
NPX = ["npx", f"wrangler@{contracts.WRANGLER_VERSION}"]


def proc(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class Pins(unittest.TestCase):
    def test_previous_pin_differs(self):
        self.assertRegex(contracts.WRANGLER_PREVIOUS, r"^4\.\d+\.\d+$")
        self.assertNotEqual(contracts.WRANGLER_PREVIOUS, contracts.WRANGLER_VERSION)


class Upload(unittest.TestCase):
    def test_cmd(self):
        self.assertEqual(deploy.upload_version_cmd("kb-share x"), NPX + ["versions", "upload", "--message", "kb-share x"])
        self.assertEqual(deploy.upload_version_cmd("m", tag="t1")[-2:], ["--tag", "t1"])

    def test_parse_fixture(self):
        self.assertEqual(deploy.parse_upload_output((FIX / "wrangler_versions_upload.txt").read_text()), VID)
        self.assertIsNone(deploy.parse_upload_output("nothing here"))

    def test_upload_runs_in_dir(self):
        seen = {}

        def runner(cmd, cwd=None, timeout=600):
            seen.update(cmd=cmd, cwd=cwd)
            return proc(out=(FIX / "wrangler_versions_upload.txt").read_text())
        self.assertEqual(deploy.upload_version("/tmp/w", "msg", runner=runner), VID)
        self.assertEqual(seen["cwd"], "/tmp/w")
        self.assertEqual(seen["cmd"][2:4], ["versions", "upload"])

    def test_upload_failures_raise(self):
        with self.assertRaisesRegex(RuntimeError, "exited 1"):
            deploy.upload_version("/tmp/w", "m", runner=lambda *a, **k: proc(1, err="boom"))
        with self.assertRaisesRegex(RuntimeError, "no version id"):
            deploy.upload_version("/tmp/w", "m", runner=lambda *a, **k: proc(0, out="ok"))


class DeployVersion(unittest.TestCase):
    def test_cmd(self):
        self.assertEqual(deploy.deploy_version_cmd("kb", VID),
                         NPX + ["versions", "deploy", f"{VID}@100", "--name", "kb", "--yes"])
        self.assertEqual(deploy.deploy_version_cmd("kb", VID, 25, "canary")[-4:],
                         ["--name", "kb", "--yes", "--message", "canary"][-4:])
        self.assertIn(f"{VID}@25", deploy.deploy_version_cmd("kb", VID, 25))

    def test_bad_pct(self):
        for p in (0, 101, -5):
            with self.assertRaises(ValueError):
                deploy.deploy_version_cmd("kb", VID, p)

    def test_deploy_raises_on_failure(self):
        deploy.deploy_version("kb", VID, runner=lambda *a, **k: proc(0))
        with self.assertRaisesRegex(RuntimeError, "versions deploy exited 2"):
            deploy.deploy_version("kb", VID, runner=lambda *a, **k: proc(2, err="nope"))


class Deployments(unittest.TestCase):
    def test_parse_fixture(self):
        rows = deploy.parse_deployments((FIX / "wrangler_deployments_list.json").read_text())
        self.assertEqual([r["id"] for r in rows], ["d-new", "d-old"])
        self.assertEqual(rows[0]["versions"][0], ("22222222-2222-4222-8222-222222222222", 90))
        self.assertEqual(rows[1]["message"], "kb-share abc1234 kb-1.0.0 private")

    def test_garbage(self):
        self.assertEqual(deploy.parse_deployments("not json"), [])
        self.assertEqual(deploy.parse_deployments("{}"), [])


if __name__ == "__main__":
    unittest.main()

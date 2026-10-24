#!/usr/bin/env python3
"""Tests for the GitHub backstop deploy: .github/workflows/deploy-main.yml + deploy-main exit codes.

The workflow is parsed with PyYAML when it is importable (a transitive dependency of the pixi
env, not a declared one) and checked by text otherwise. deploy_main() is mocked, so no build,
git or Cloudflare call happens here.
"""
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from kb.paths import vault_root
ROOT = vault_root()

from kb.share import deploy
from kb.share.contracts import DEPLOY_STATES

WORKFLOW = Path(ROOT, ".github", "workflows", "deploy-main.yml")
CI = Path(ROOT, ".github", "workflows", "ci.yml")

try:
    import yaml
except ImportError:  # pragma: no cover — text fallback below
    yaml = None


def _load(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in data:  # PyYAML reads the bare `on:` key as boolean True
        data["on"] = data.pop(True)
    return data


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.wf = _load(WORKFLOW) if yaml else None
        self.steps = self.wf["jobs"]["deploy"]["steps"] if self.wf else []

    def _step(self, pred):
        hits = [s for s in self.steps if pred(s)]
        self.assertEqual(len(hits), 1, f"expected exactly one matching step, got {len(hits)}")
        return hits[0]

    def test_header_explains_the_backstop(self):
        head = self.text.split("name:")[0]
        for word in ("Mac", "skipped-same", "skipped-older", "snapshot"):
            self.assertIn(word, head)

    def test_triggers_and_concurrency(self):
        if not self.wf:
            self.assertRegex(self.text, r"on:\n  schedule:\n    - cron: \"[^\"]+\".*\n  workflow_dispatch:")
            self.assertIn("group: deploy-main", self.text)
            self.assertIn("cancel-in-progress: false", self.text)
            return
        self.assertEqual(self.wf["name"], "deploy-main")
        # daily, never per push: every kb(...) op pushes main, and the Mac already deploys each one
        self.assertNotIn("push", self.wf["on"])
        self.assertEqual(len(self.wf["on"]["schedule"]), 1)
        self.assertIn("workflow_dispatch", self.wf["on"])
        self.assertEqual(self.wf["concurrency"], {"group": "deploy-main", "cancel-in-progress": False})

    def test_job_env_and_runner(self):
        if not self.wf:
            self.assertIn('KB_CI: "1"', self.text)
            self.assertIn('KB_SHARE_AUTODEPLOY: "0"', self.text)
            self.assertIn("runs-on: [self-hosted, macOS, ARM64]", self.text)
            return
        job = self.wf["jobs"]["deploy"]
        # the owner's Mac: GitHub-hosted macOS minutes bill 10x and ran out on the Free plan
        self.assertEqual(job["runs-on"], ["self-hosted", "macOS", "ARM64"])
        self.assertEqual(str(job["env"]["KB_CI"]), "1")
        self.assertEqual(str(job["env"]["KB_SHARE_AUTODEPLOY"]), "0")

    def test_checkout_has_full_history_and_a_local_main(self):
        if not self.wf:
            self.assertIn("fetch-depth: 0", self.text)
            self.assertIn("git branch main origin/main", self.text)
            return
        checkout = self._step(lambda s: str(s.get("uses", "")).startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertTrue(any("git branch main origin/main" in str(s.get("run", "")) for s in self.steps))

    def test_pixi_pinned_like_ci(self):
        ci_text = CI.read_text(encoding="utf-8")
        for key in ("prefix-dev/setup-pixi@", "pixi-version: "):
            mine = re.search(key + r"(\S+)", self.text)
            theirs = re.search(key + r"(\S+)", ci_text)
            self.assertIsNotNone(mine, key)
            self.assertEqual(mine.group(1), theirs.group(1), f"{key} must match ci.yml")

    def test_steps_in_order_and_secrets_by_name_only(self):
        if not self.wf:
            self.assertIn("pixi run test", self.text)
            self.assertIn("pixi run share -- deploy-main", self.text)
            self.assertIn("pixi run share -- status", self.text)
        else:
            runs = [str(s.get("run", "")) for s in self.steps]
            order = [next(i for i, r in enumerate(runs) if cmd in r)
                     for cmd in ("pixi run test", "pixi run share -- deploy-main", "pixi run share -- status")]
            self.assertEqual(order, sorted(order))
            step = self._step(lambda s: "share -- deploy-main" in str(s.get("run", "")))
            self.assertEqual(step["env"]["CLOUDFLARE_API_TOKEN"], "${{ secrets.CLOUDFLARE_API_TOKEN }}")
            self.assertEqual(step["env"]["CLOUDFLARE_ACCOUNT_ID"], "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}")
            self.assertNotIn("--force", step["run"])
        # secrets are referenced, never written down
        self.assertEqual(sorted(set(re.findall(r"secrets\.(\w+)", self.text))),
                         ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"])
        for line in self.text.splitlines():
            if "CLOUDFLARE_" in line:
                self.assertRegex(line, r"CLOUDFLARE_(API_TOKEN|ACCOUNT_ID)(: \$\{\{ secrets\.CLOUDFLARE_\1 \}\})?\b")
        self.assertNotRegex(self.text, r"(?i)(token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{20,}")

    def test_artifact_step(self):
        if not self.wf:
            self.assertIn("actions/upload-artifact@v4", self.text)
            self.assertIn("name: kb-site-main", self.text)
            self.assertIn("retention-days: 30", self.text)
            return
        up = self._step(lambda s: str(s.get("uses", "")).startswith("actions/upload-artifact@v4"))
        self.assertEqual(up["with"]["name"], "kb-site-main")
        self.assertEqual(up["with"]["retention-days"], 30)
        paths = up["with"]["path"].split()
        self.assertEqual(paths, [".exported/share/main/index.html", ".exported/share/main/manifest.json"])
        self.assertEqual(up.get("if"), "always()")


class ExitCodeTests(unittest.TestCase):
    """deploy-main exits 0 on every guard skip (the CI backstop must stay green) and 1 on real failures."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cache = Path(self.tmp, "cache")
        for p in (mock.patch.object(deploy, "CACHE_DIR", cache),
                  mock.patch.object(deploy, "STATUS_PATH", cache / "status.json"),
                  mock.patch.object(deploy, "LOG_PATH", Path(self.tmp, "share.log"))):
            p.start()
            self.addCleanup(p.stop)

    def rc_for(self, state):
        fake = lambda force=False, dry_run=False, build_dir=None: deploy.DeployResult(state=state, url="u")
        with mock.patch.object(deploy, "deploy_main", fake):
            return deploy.cmd_deploy_main(types.SimpleNamespace(force=False, dry_run=False, dir=None))

    def test_every_state_has_an_exit_code(self):
        expected = {"deployed": 0, "skipped-same": 0, "skipped-older": 0, "refused-no-access": 1, "failed": 1}
        self.assertEqual(set(expected), set(DEPLOY_STATES))
        for state, rc in expected.items():
            with self.subTest(state=state):
                self.assertEqual(deploy.deploy_main_exit_code(state), rc)
                self.assertEqual(self.rc_for(state), rc)
        self.assertEqual(deploy.deploy_main_exit_code(deploy.DRY_RUN), 0)
        self.assertEqual(deploy.deploy_main_exit_code("garbage"), 1)

    def test_pending_rerun_decides_the_exit_code(self):
        states = iter(["deployed", "failed"])
        fake = lambda force=False, dry_run=False, build_dir=None: deploy.DeployResult(state=next(states), url="u")
        deploy.pending_path().parent.mkdir(parents=True, exist_ok=True)
        deploy.pending_path().touch()
        with mock.patch.object(deploy, "deploy_main", fake):
            rc = deploy.cmd_deploy_main(types.SimpleNamespace(force=False, dry_run=False, dir=None))
        self.assertEqual(rc, 1)
        self.assertFalse(deploy.pending_path().exists())


if __name__ == "__main__":
    unittest.main()

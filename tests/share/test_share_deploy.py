#!/usr/bin/env python3
"""Tests for src/kb_distillery/share deploy, autodeploy, the Worker auth module and the dashboard chip.

wrangler and the Workers API are mocked through deploy()'s `runner` / `http` seams; the build is
a stub dir (index.html + manifest.json). Worker auth tests run `node --test` when node is around.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.share import autodeploy, deploy
from kb_distillery.share.contracts import DEPLOY_MESSAGE_PREFIX, WORKER_MAIN

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth?x=1"


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


def make_repo(tmp):
    """main: A → B; branch side: A → C. Returns (root, {A, B, C})."""
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    g(root, "init", "-q", "-b", "main")
    g(root, "config", "user.name", "t")
    g(root, "config", "user.email", "t@t")
    shas = {}
    for name in ("A", "B"):
        Path(root, f"{name}.md").write_text(name)
        g(root, "add", "-A")
        g(root, "commit", "-q", "-m", name)
        shas[name] = g(root, "rev-parse", "HEAD")
    g(root, "checkout", "-q", "-b", "side", shas["A"])
    Path(root, "C.md").write_text("C")
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "C")
    shas["C"] = g(root, "rev-parse", "HEAD")
    g(root, "checkout", "-q", "main")
    return root, shas


def make_build(tmp, sha, version="0.10.5", profile="private"):
    d = Path(tmp, "build")
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text("<!doctype html><title>kb</title>")
    (d / "manifest.json").write_text(json.dumps({"content_ref": "main", "content_sha": sha, "kb_version": version,
                                                 "viewer_sha": sha, "profile": profile, "sha256": "0" * 64,
                                                 "built_at": "2026-10-21T10:00:00+00:00"}))
    return d


class FakeCloudflare:
    """Records wrangler invocations; answers deployments/versions list from `live_message`."""

    def __init__(self, live_message=None, gate_ok=True, deploy_rc=0, rollback_rc=0, gate_after=None):
        self.live_message = live_message
        self.gate_ok = gate_ok
        self.gate_after = gate_after  # gate state after a deploy/rollback (None = unchanged)
        self.deploy_rc = deploy_rc
        self.rollback_rc = rollback_rc
        self.calls = []

    def runner(self, cmd, cwd=None, timeout=None):
        self.calls.append((cmd, cwd))
        sub = cmd[2]
        if sub == "deployments":
            out = json.dumps([{"id": "d1", "versions": [{"version_id": "v-live", "percentage": 100}]}])
            return subprocess.CompletedProcess(cmd, 0, out, "")
        if sub == "versions":
            ann = {"workers/message": self.live_message} if self.live_message else {}
            return subprocess.CompletedProcess(cmd, 0, json.dumps([{"id": "v-live", "annotations": ann}]), "")
        if sub == "deploy":
            assert Path(cwd, "wrangler.jsonc").is_file() and Path(cwd, "public", "index.html").is_file()
            self.deployed_dir = {p.name for p in Path(cwd).iterdir()}
            self.deployed_cfg = Path(cwd, "wrangler.jsonc").read_text()
            if self.gate_after is not None:
                self.gate_ok = self.gate_after
            return subprocess.CompletedProcess(cmd, self.deploy_rc,
                                               "Uploaded kb\nDeployed kb triggers\nCurrent Version ID: " + "a" * 8 +
                                               "-bbbb-cccc-dddd-" + "e" * 12 + "\n", "" if not self.deploy_rc else "boom")
        if sub == "rollback":
            if self.gate_after is not None:
                self.gate_ok = self.gate_after
            return subprocess.CompletedProcess(cmd, self.rollback_rc, "Current Version ID: " + "f" * 8 +
                                               "-bbbb-cccc-dddd-" + "e" * 12, "")
        raise AssertionError(f"unexpected wrangler call {cmd}")

    def http(self, url):
        if not self.gate_ok:
            return 200, ""
        if url.endswith("/auth/login"):
            return 302, GOOGLE
        return 302, "/auth/login"

    @property
    def uploaded(self):
        return any(c[0][2] == "deploy" for c in self.calls)


class ShareCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root, self.shas = make_repo(self.tmp)
        cache = Path(self.tmp, "cache")
        patches = [mock.patch.object(deploy, "CACHE_DIR", cache), mock.patch.object(deploy, "STATUS_PATH", cache / "status.json"),
                   mock.patch.object(deploy, "LOG_PATH", Path(self.tmp, "share.log")),
                   mock.patch.object(autodeploy, "LOG_PATH", Path(self.tmp, "share.log")),
                   mock.patch.dict(os.environ, ENV)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.cfg = {"google_client_id": "cid", "allowed_emails": ["me@x.com"], "compatibility_date": "2026-09-01"}

    def status(self):
        return deploy.status_file().read()

    def run_deploy(self, cf, sha, worker=WORKER_MAIN, require_access=True, **kw):
        build = make_build(self.tmp, sha)
        return deploy.deploy(build, worker, require_access=require_access, runner=cf.runner, http=cf.http,
                             git_root=self.root, config=self.cfg, **kw)


class GateTests(ShareCase):
    def test_gate_down_refuses_and_uploads_nothing(self):
        cf = FakeCloudflare(live_message=f"{DEPLOY_MESSAGE_PREFIX} {self.shas['A']} 0.10.1 private", gate_ok=False)
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "refused-no-access")
        self.assertFalse(cf.uploaded)
        self.assertEqual(self.status()["state"], "refused-no-access")
        self.assertIn("nothing uploaded", self.status()["error"])

    def test_login_not_google_refuses(self):
        cf = FakeCloudflare(live_message=f"{DEPLOY_MESSAGE_PREFIX} {self.shas['A']} 0.10.1 private")
        cf.http = lambda url: (302, "/somewhere") if url.endswith("/auth/login") else (302, "/auth/login")
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "refused-no-access")
        self.assertFalse(cf.uploaded)

    def test_gate_ok_proceeds(self):
        cf = FakeCloudflare(live_message=f"{DEPLOY_MESSAGE_PREFIX} {self.shas['A']} 0.10.1 private")
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "deployed")
        self.assertTrue(cf.uploaded)
        self.assertEqual(r.version_id, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(r.url, "https://kb.yonatan-magen-thesis.workers.dev")

    def test_bootstrap_first_auth_deploy_allowed_then_gate_verified(self):
        cf = FakeCloudflare(live_message=None, gate_ok=False, gate_after=True)  # hello page → auth Worker
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "deployed")
        self.assertTrue(cf.uploaded)

    def test_gate_still_down_after_deploy_is_loud(self):
        cf = FakeCloudflare(live_message=None, gate_ok=False, gate_after=False)
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "failed")
        self.assertIn("AUTH GATE IS DOWN", r.error)
        self.assertEqual(self.status()["state"], "failed")

    def test_snapshot_worker_skips_gate_and_ships_assets_only(self):
        cf = FakeCloudflare(gate_ok=False)
        r = self.run_deploy(cf, self.shas["B"], worker="snapshot-20261021-x", require_access=False)
        self.assertEqual(r.state, "deployed")
        self.assertNotIn("auth.js", cf.deployed_dir)
        self.assertNotIn("admin.js", cf.deployed_dir)  # snapshots are public: no panel API
        self.assertNotIn('"main"', cf.deployed_cfg)
        self.assertNotIn('"vars"', cf.deployed_cfg)


class GuardTests(ShareCase):
    def live(self, sha):
        return f"{DEPLOY_MESSAGE_PREFIX} {sha} 0.10.1 private"

    def test_same_sha_skipped(self):
        cf = FakeCloudflare(self.live(self.shas["B"]))
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "skipped-same")
        self.assertFalse(cf.uploaded)
        self.assertEqual(self.status()["state"], "skipped-same")

    def test_live_not_ancestor_skipped_older(self):
        cf = FakeCloudflare(self.live(self.shas["C"]))  # C is on a side branch, not an ancestor of B
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "skipped-older")
        self.assertFalse(cf.uploaded)

    def test_live_ancestor_deploys(self):
        cf = FakeCloudflare(self.live(self.shas["A"]))
        self.assertEqual(self.run_deploy(cf, self.shas["B"]).state, "deployed")

    def test_unparseable_or_absent_message_deploys(self):
        for msg in (None, "Automatic deployment on upload.", "kb-share garbage"):
            with self.subTest(msg=msg):
                cf = FakeCloudflare(msg)
                self.assertEqual(self.run_deploy(cf, self.shas["B"]).state, "deployed")

    def test_force_deploys_older(self):
        cf = FakeCloudflare(self.live(self.shas["C"]))
        r = self.run_deploy(cf, self.shas["B"], force=True)
        self.assertEqual(r.state, "deployed")
        self.assertTrue(cf.uploaded)

    def test_force_does_not_bypass_gate(self):
        cf = FakeCloudflare(self.live(self.shas["A"]), gate_ok=False)
        self.assertEqual(self.run_deploy(cf, self.shas["B"], force=True).state, "refused-no-access")

    def test_deploy_message_and_config(self):
        cf = FakeCloudflare(None)
        self.run_deploy(cf, self.shas["B"])
        cmd = next(c[0] for c in cf.calls if c[0][2] == "deploy")
        self.assertEqual(cmd[:3], ["npx", "wrangler@4.151.3", "deploy"])
        self.assertEqual(cmd[cmd.index("--message") + 1], f"kb-share {self.shas['B']} 0.10.5 private")
        self.assertIn("auth.js", cf.deployed_dir)
        cfg = json.loads("\n".join(l for l in cf.deployed_cfg.splitlines() if not l.strip().startswith("//")))
        self.assertEqual(cfg["name"], "kb")
        self.assertEqual(cfg["main"], "auth.js")
        self.assertFalse(cfg["preview_urls"])
        self.assertTrue(cfg["workers_dev"])
        self.assertEqual(cfg["assets"], {"directory": "./public", "binding": "ASSETS", "run_worker_first": True})
        self.assertEqual(cfg["vars"], {"GOOGLE_CLIENT_ID": "cid", "ALLOWED_EMAILS": "me@x.com",
                                       "CF_ACCOUNT_ID": deploy.CF_ACCOUNT_ID})
        self.assertNotIn("CF_API_TOKEN", json.dumps(cfg))  # a secret, never rendered
        self.assertEqual(cfg["compatibility_flags"], ["global_fetch_strictly_public"])
        self.assertIn("admin.js", cf.deployed_dir)


class OutcomeTests(ShareCase):
    def test_wrangler_failure_recorded(self):
        cf = FakeCloudflare(None, deploy_rc=1)
        r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "failed")
        self.assertIn("exited 1", r.error)
        self.assertEqual(self.status()["state"], "failed")

    def test_exception_lands_in_status_file(self):
        def exploding(cmd, cwd=None, timeout=None):
            raise OSError("npx vanished")
        cf = FakeCloudflare(None)
        r = deploy.deploy(make_build(self.tmp, self.shas["B"]), WORKER_MAIN, require_access=True, runner=exploding,
                          http=cf.http, git_root=self.root, config=self.cfg)
        self.assertEqual(r.state, "failed")
        self.assertIn("npx vanished", r.error)
        st = self.status()
        self.assertEqual(st["state"], "failed")
        self.assertEqual(st["sha"], self.shas["B"])
        self.assertTrue(Path(self.tmp, "share.log").read_text())

    def test_missing_manifest_raises_before_touching_anything(self):
        d = Path(self.tmp, "empty")
        d.mkdir()
        with self.assertRaises(RuntimeError):
            deploy.deploy(d, WORKER_MAIN, require_access=False, config=self.cfg)
        self.assertIsNone(self.status())

    def test_dry_run_renders_and_prints_without_running(self):
        cf = FakeCloudflare(None)
        with mock.patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as out:
            r = self.run_deploy(cf, self.shas["B"], dry_run=True)
        self.assertEqual(r.state, deploy.DRY_RUN)
        self.assertEqual(cf.calls, [])
        self.assertIsNone(self.status())
        self.assertIn("wrangler@4.151.3 deploy --message", out.getvalue())
        self.assertTrue((deploy.cache_dir() / "dry-run" / "kb" / "auth.js").is_file())


class RollbackTests(ShareCase):
    def test_rollback_then_gate_ok(self):
        cf = FakeCloudflare(f"{DEPLOY_MESSAGE_PREFIX} {self.shas['A']} 0.10.1 private")
        r = deploy.rollback(WORKER_MAIN, runner=cf.runner, http=cf.http)
        self.assertEqual(r.state, "deployed")
        cmd = next(c[0] for c in cf.calls if c[0][2] == "rollback")
        self.assertEqual(cmd[2:5], ["rollback", "--name", "kb"])
        self.assertEqual(self.status()["state"], "deployed")
        self.assertEqual(self.status()["kb_version"], "0.10.1")

    def test_rollback_snapshot_skips_gate_and_keeps_its_own_status(self):
        cf = FakeCloudflare(gate_ok=False)  # a public snapshot has no gate: that must not read as failure
        status = Path(self.tmp, "cache", "status-snapshot-20261001-pub.json")
        r = deploy.rollback("snapshot-20261001-pub", runner=cf.runner, http=cf.http, require_access=False,
                            status_path=status)
        self.assertEqual(r.state, "deployed", r.error)
        self.assertTrue(status.exists())
        cmd = next(c[0] for c in cf.calls if c[0][2] == "rollback")
        self.assertEqual(cmd[2:5], ["rollback", "--name", "snapshot-20261001-pub"])

    def test_rollback_target_resolution(self):
        from kb_distillery.share import snapshots
        scripts = [{"name": "snapshot-20261001-pub"}, {"name": "snapshot-20261005-pub"}, {"name": "snapshot-20261002-cohen"}]
        with mock.patch.object(snapshots, "snapshot_scripts", lambda: scripts):
            self.assertEqual(deploy.rollback_target("kb"), ("kb", True, None))
            w, gate, status = deploy.rollback_target("cohen")
            self.assertEqual((w, gate), ("snapshot-20261002-cohen", False))
            self.assertEqual(Path(status).name, "status-snapshot-20261002-cohen.json")
            w, gate, status = deploy.rollback_target("snapshot-20261005-pub")
            self.assertEqual((w, gate), ("snapshot-20261005-pub", False))
            with self.assertRaises(ValueError) as cm:
                deploy.rollback_target("pub")
            self.assertIn("ambiguous", str(cm.exception))
            with self.assertRaises(ValueError):
                deploy.rollback_target("my-other-worker")

    def test_rollback_to_version(self):
        cf = FakeCloudflare(None)
        deploy.rollback(WORKER_MAIN, "v-old", runner=cf.runner, http=cf.http)
        cmd = next(c[0] for c in cf.calls if c[0][2] == "rollback")
        self.assertEqual(cmd[3], "v-old")

    def test_gate_failure_after_rollback_is_loud(self):
        cf = FakeCloudflare(None, gate_after=False)
        r = deploy.rollback(WORKER_MAIN, runner=cf.runner, http=cf.http)
        self.assertEqual(r.state, "failed")
        self.assertIn("AUTH GATE IS DOWN", r.error)
        self.assertEqual(self.status()["state"], "failed")


class LockAndDebounceTests(ShareCase):
    def test_lock_held_returns_failed_without_touching_status(self):
        with deploy.deploy_lock():
            cf = FakeCloudflare(None)
            r = self.run_deploy(cf, self.shas["B"])
        self.assertEqual(r.state, "failed")
        self.assertIn("another deploy", r.error)
        self.assertIsNone(self.status())

    def test_stale_lock_reclaimed(self):
        deploy.lock_path().parent.mkdir(parents=True)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        deploy.lock_path().write_text(str(dead.pid))
        self.assertIsNone(deploy.lock_owner())
        self.assertFalse(deploy.lock_path().exists())
        cf = FakeCloudflare(None)
        self.assertEqual(self.run_deploy(cf, self.shas["B"]).state, "deployed")

    def test_two_triggers_during_deploy_rerun_once(self):
        spawned = []
        with mock.patch.object(autodeploy, "spawn", lambda root: spawned.append(root)), \
                mock.patch.object(autodeploy, "enabled", lambda root: True):
            with deploy.deploy_lock():
                self.assertEqual(autodeploy.trigger("one"), "pending")
                self.assertEqual(autodeploy.trigger("two"), "pending")
            self.assertEqual(spawned, [])
            self.assertTrue(deploy.pending_path().exists())
            runs = []
            fake = lambda force=False, dry_run=False, build_dir=None, app=True: runs.append(app) or deploy.DeployResult(state="deployed")
            with mock.patch.object(deploy, "deploy_main", fake):
                rc = deploy.cmd_deploy_main(types.SimpleNamespace(force=False, dry_run=False))
            self.assertEqual(rc, 0)
            self.assertEqual(runs, [True, True])  # the deploy + exactly one rerun, both the app layout
            self.assertFalse(deploy.pending_path().exists())
            self.assertEqual(autodeploy.trigger("three"), "spawned")
            self.assertEqual(len(spawned), 1)

    def test_cmd_deploy_main_while_locked_marks_pending(self):
        with deploy.deploy_lock():
            with mock.patch.object(deploy, "deploy_main", side_effect=AssertionError("must not run")):
                rc = deploy.cmd_deploy_main(types.SimpleNamespace(force=False, dry_run=False))
        self.assertEqual(rc, 0)
        self.assertTrue(deploy.pending_path().exists())


class AutodeployTests(ShareCase):
    def test_opt_out_spawns_nothing(self):
        with mock.patch.dict(os.environ, {"KB_SHARE_AUTODEPLOY": "0"}), \
                mock.patch.object(autodeploy, "spawn", side_effect=AssertionError("spawned")):
            self.assertEqual(autodeploy.trigger("x", ROOT), "disabled")

    def test_non_share_repo_spawns_nothing(self):
        with mock.patch.object(autodeploy, "spawn", side_effect=AssertionError("spawned")):
            self.assertEqual(autodeploy.trigger("x", self.root), "disabled")

    def test_spawn_is_detached_and_logged(self):
        with mock.patch.object(autodeploy, "COMMAND", [sys.executable, "-c", "import time; print('hi'); time.sleep(0.3)"]):
            t0 = time.monotonic()
            proc = autodeploy.spawn(self.root)
            self.assertLess(time.monotonic() - t0, 0.25)
            self.assertIsNone(proc.poll())
            proc.wait(5)
        self.assertIn("hi", Path(self.tmp, "share.log").read_text())

    def test_trigger_never_raises(self):
        with mock.patch.object(autodeploy, "enabled", side_effect=RuntimeError("kaboom")):
            self.assertEqual(autodeploy.trigger("x"), "error")
        with mock.patch.object(autodeploy, "enabled", lambda root: True), \
                mock.patch.object(autodeploy, "spawn", side_effect=OSError("no pixi")):
            self.assertEqual(autodeploy.trigger("x"), "error")

    def test_run_foreground_never_raises(self):
        with mock.patch.object(autodeploy, "enabled", lambda root: True), \
                mock.patch.object(autodeploy.subprocess, "run", side_effect=OSError("no pixi")):
            self.assertEqual(autodeploy.run_foreground("nightly", self.root), -1)


class CommitOpHookTests(unittest.TestCase):
    """commit_op kicks the trigger after the sha is known, detached, and shrugs off failures."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.remote = os.path.join(self.tmp, "remote.git")
        self.root = os.path.join(self.tmp, "kb")
        g(self.tmp, "init", "-q", "--bare", "-b", "main", self.remote)
        g(self.tmp, "clone", "-q", self.remote, self.root)
        g(self.root, "config", "user.name", "t")
        g(self.root, "config", "user.email", "t@t")
        _lint = mock.patch("kb_distillery.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test
        _lint.start()
        self.addCleanup(_lint.stop)
        for rel, text in (("meta/stub.py", "x = 1\n"), ("wiki/log.md", "# Log\n"),
                          (".gitignore", "meta/.ops/\n"), ("wiki/b.md", "v1\n"), ("wiki/index.md", "v1\n")):
            Path(self.root, rel).parent.mkdir(parents=True, exist_ok=True)
            Path(self.root, rel).write_text(text)
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "chore: init (retro)")
        g(self.root, "push", "-q", "-u", "origin", "main")

    def test_commit_op_returns_before_the_deploy_finishes_and_survives_trigger_errors(self):
        from kb_distillery.ops import core
        self.enterContext(mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": "1"}))  # the old direct path
        Path(self.root, "wiki/b.md").write_text("v2\n")
        started = []
        procs = []

        def slow_trigger(reason, root=None):
            started.append((reason, root))
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
            self.addCleanup(proc.kill)
            procs.append(proc)
            return "spawned"
        with mock.patch("kb_distillery.share.autodeploy.trigger", slow_trigger):
            sha = core.commit_op("refine", "b", paths=["wiki/b.md"], lint=False, root=self.root)
            # The fake deploy is still running when commit_op returns: it does not wait for it.
            # (Not a wall-clock bound — git alone takes several seconds on a loaded machine.)
            self.assertIsNone(procs[0].poll())
        self.assertTrue(sha)
        self.assertEqual(len(started), 1)
        self.assertIn("refine", started[0][0])
        self.assertEqual(started[0][1], self.root)

        Path(self.root, "wiki/b.md").write_text("v3\n")
        with mock.patch("kb_distillery.share.autodeploy.trigger", side_effect=RuntimeError("boom")):
            sha2 = core.commit_op("refine", "b", paths=["wiki/b.md"], lint=False, root=self.root)
        self.assertTrue(sha2)
        self.assertNotEqual(sha, sha2)

    def test_real_trigger_on_a_test_repo_is_a_no_op(self):
        from kb_distillery.ops import core
        Path(self.root, "wiki/b.md").write_text("v2\n")
        with mock.patch.object(autodeploy, "spawn", side_effect=AssertionError("spawned")):
            self.assertTrue(core.commit_op("refine", "b", paths=["wiki/b.md"], lint=False, root=self.root))


class ChipTests(unittest.TestCase):
    def test_every_state_renders(self):
        from kb_distillery.publish.site_state import share_chip
        import datetime as dt
        now = dt.datetime(2026, 10, 21, 12, 0, tzinfo=dt.timezone.utc)
        base = {"sha": "abcdef1234", "kb_version": "0.10.5", "at": "2026-10-21T11:30:00+00:00", "error": None,
                "url": "https://kb.yonatan-magen-thesis.workers.dev"}
        chip = share_chip({**base, "state": "deployed"}, now)
        self.assertEqual((chip["label"], chip["cls"], chip["href"]), ("kb-0.10.5 · 30 min ago", "is-deployed", base["url"]))
        self.assertEqual(share_chip({**base, "state": "deploying"}, now)["cls"], "is-deploying")
        for st in ("skipped-same", "skipped-older"):
            self.assertEqual(share_chip({**base, "state": st}, now)["cls"], "is-skipped")
        failed = share_chip({**base, "state": "failed", "error": "wrangler exited 1"}, now)
        self.assertEqual((failed["cls"], failed["href"]), ("is-failed", "/share-log"))
        self.assertIn("wrangler exited 1", failed["title"])
        self.assertEqual(share_chip({**base, "state": "refused-no-access"}, now)["cls"], "is-failed")
        self.assertIsNone(share_chip(None))
        self.assertIsNone(share_chip({}))

    def test_nav_has_chip_slot_and_server_routes(self):
        from kb_distillery.dashboard.shell import render_nav
        from kb_distillery.dashboard import serve
        self.assertIn('id="share-chip"', render_nav("graph"))
        self.assertIn("share_status", serve.Handler.do_GET.__code__.co_names)
        with tempfile.TemporaryDirectory() as d:
            log = Path(d, "share.log")
            log.write_text("".join(f"line {i}\n" for i in range(300)))
            with mock.patch("kb_distillery.share.contracts.LOG_PATH", log):
                tail = serve.share_log_tail()
            self.assertEqual(tail.splitlines()[0], "line 100")
            self.assertEqual(len(tail.splitlines()), 200)


class ConfigTests(unittest.TestCase):
    def test_env_overrides_file_and_save_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "share.toml")
            shutil.copy(deploy.CONFIG_PATH, p)
            cfg = deploy.load_config(p)
            self.assertEqual(cfg["allowed_emails"], ["ygreenshpan@gmail.com"])
            self.assertTrue(cfg["google_client_id"].endswith(".apps.googleusercontent.com"))
            with mock.patch.dict(os.environ, {"KB_SHARE_GOOGLE_CLIENT_ID": "env-id"}):
                self.assertEqual(deploy.load_config(p)["google_client_id"], "env-id")
            cfg["google_client_id"] = "stored-id"
            deploy.save_config(cfg, p)
            again = deploy.load_config(p)
            self.assertEqual(again["google_client_id"], "stored-id")
            self.assertTrue(p.read_text().startswith("# Share deploy config"))


class WorkerAuthTests(unittest.TestCase):
    def test_node_suite(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        proc = subprocess.run([node, "--test", "--test-reporter=tap",   # newer Node defaults to spec
                               os.path.join(ROOT, "share", "auth.test.mjs")],
                              capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-2000:])
        self.assertIn("# fail 0", proc.stdout)


if __name__ == "__main__":
    unittest.main()


class PixiPathTests(unittest.TestCase):
    def test_falls_back_to_home_install_when_not_on_path(self):
        with mock.patch.object(autodeploy.shutil, "which", return_value=None):
            self.assertEqual(autodeploy._pixi(), str(Path.home() / ".pixi" / "bin" / "pixi"))

    def test_uses_path_when_available(self):
        with mock.patch.object(autodeploy.shutil, "which", return_value="/opt/x/pixi"):
            self.assertEqual(autodeploy._pixi(), "/opt/x/pixi")

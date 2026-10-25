"""Tests for kb.share.owner: dedupe per sha, retry classifier, rollback on failed health, nudging
callers, single instance. wrangler, git, http, the builder and the event poster are all mocked."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb.share import deploy as dp
from kb.share import owner

SHA = "a" * 40
OLD_VID = "11111111-1111-1111-1111-111111111111"
NEW_VID = "22222222-2222-2222-2222-222222222222"


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class FakeCF:
    """wrangler stand-in: tracks which version serves 100%."""

    def __init__(self, upload_fail=None, deploy_fail=None):
        self.live = OLD_VID
        self.messages = {OLD_VID: "kb-share " + "b" * 40 + " 1.0.0 private"}
        self.calls = []
        self.upload_fail = list(upload_fail or [])
        self.deploy_fail = list(deploy_fail or [])

    def __call__(self, cmd, cwd=None, **kw):
        args = cmd[2:]
        self.calls.append(args)
        if args[:2] == ["deployments", "list"]:
            return cp(out=json.dumps([{"id": "d", "created_on": "2026-10-25T00:00:00Z",
                                       "versions": [{"version_id": self.live, "percentage": 100}]}]))
        if args[:2] == ["versions", "list"]:
            return cp(out=json.dumps([{"id": k, "annotations": {"workers/message": v}}
                                      for k, v in self.messages.items()]))
        if args[:2] == ["versions", "upload"]:
            if self.upload_fail:
                return cp(1, err=self.upload_fail.pop(0))
            self.messages[NEW_VID] = args[args.index("--message") + 1]
            return cp(out=f"Uploaded kb\nWorker Version ID: {NEW_VID}\n")
        if args[:2] == ["versions", "deploy"]:
            if self.deploy_fail:
                return cp(1, err=self.deploy_fail.pop(0))
            self.live = args[2].split("@")[0]
            return cp(out="ok")
        return cp(1, err=f"unexpected {args}")


def good_http(url):
    if url.endswith("/auth/login"):
        return 302, "https://accounts.google.com/o/oauth2"
    if url.endswith("/app"):
        return 302, "/auth/login"
    return 302, "/auth/login"


def git_for(sha, subject="feat(share): x (#42)"):
    def git(args, root):
        if args[0] == "fetch":
            return cp()
        if args[0] == "rev-parse":
            return cp(out=sha + "\n")
        if args[0] == "log":
            return cp(out=subject + "\n")
        return cp(1)
    return git


class OwnerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        cache = self.root / ".cache" / "share"
        self.patches = [
            mock.patch.object(dp, "cache_dir", lambda: cache),
            mock.patch.object(dp, "status_file", lambda: dp.StatusFile(cache / "status.json")),
            mock.patch.object(dp, "log", lambda line: None),
            mock.patch.object(dp, "render_worker_dir", lambda b, w, r, c, dest: dest),
            mock.patch.dict(os.environ, {"KB_SHARE_OWNER_STATUS": ""}),
        ]
        for p in self.patches:
            p.start()
        self.builds = []
        self.posts = []

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def builder(self, sha, out_root):
        self.builds.append(sha)
        d = Path(out_root) / sha
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"content_sha": sha, "kb_version": "1.2.3", "profile": "private"}))
        return d

    def cycle(self, cf, http=good_http, sha=SHA, sleeps=None):
        return owner.cycle(self.root, runner=cf, http=http, sleep=(sleeps.append if sleeps is not None else lambda s: None),
                           git=git_for(sha), builder=self.builder,
                           poster=lambda pr, ev, s, root, **kv: self.posts.append((pr, ev, s)), config={})


class TestDedupe(OwnerBase):
    def test_builds_and_deploys_once_per_sha(self):
        cf = FakeCF()
        self.assertEqual(self.cycle(cf), "deployed")
        self.assertEqual(cf.live, NEW_VID)
        self.assertEqual(self.cycle(cf), "idle")
        self.assertEqual(self.cycle(cf), "idle")
        self.assertEqual(self.builds, [SHA])
        self.assertEqual(sum(1 for c in cf.calls if c[:2] == ["versions", "upload"]), 1)
        self.assertEqual(self.posts, [(42, "deployed", SHA)])
        st = owner.load_state(self.root)
        self.assertEqual(st["shas"][SHA]["state"], "deployed")
        self.assertTrue(st["last_success_at"])
        self.assertTrue(owner.fresh(24, self.root))

    def test_new_sha_deploys_again_and_build_is_reused(self):
        cf = FakeCF()
        self.cycle(cf)
        other = "c" * 40
        self.assertEqual(self.cycle(cf, sha=other), "deployed")
        self.assertEqual(self.builds, [SHA, other])
        # a cached build dir is reused, not rebuilt
        owner.load_state(self.root)
        st = owner.load_state(self.root)
        st["shas"].pop(other)
        owner.save_state(st, self.root)
        self.cycle(FakeCF(), sha=other)
        self.assertEqual(self.builds, [SHA, other])

    def test_already_live_sha_is_skipped(self):
        cf = FakeCF()
        cf.messages[OLD_VID] = f"kb-share {SHA} 1.2.3 private"
        self.assertEqual(self.cycle(cf), "skipped")
        self.assertFalse(any(c[:2] == ["versions", "upload"] for c in cf.calls))


class TestRetry(OwnerBase):
    def test_classifier(self):
        for text in ("TypeError: fetch failed", "read ECONNRESET", "connect ETIMEDOUT 1.2.3.4:443",
                     "tunneling socket could not be established", "502 Bad Gateway", "HTTP 503"):
            self.assertTrue(owner.is_network_error(text), text)
        for text in ("Authentication error [code: 10000]", "SyntaxError in auth.js", "no manifest.json"):
            self.assertFalse(owner.is_network_error(text), text)
        self.assertTrue(owner.is_network_error(TimeoutError()))

    def test_network_errors_retry_with_backoff(self):
        sleeps = []
        cf = FakeCF(upload_fail=["fetch failed", "read ECONNRESET"])
        self.assertEqual(self.cycle(cf, sleeps=sleeps), "deployed")
        self.assertEqual(sleeps, [10, 60, owner.SETTLE_SECONDS])

    def test_non_network_error_fails_fast(self):
        sleeps = []
        cf = FakeCF(upload_fail=["Authentication error [code: 10000]"])
        self.assertEqual(self.cycle(cf, sleeps=sleeps), "failed")
        self.assertEqual(sleeps, [])
        self.assertEqual(cf.live, OLD_VID)
        self.assertEqual(self.cycle(cf), "idle")  # failed for good: not retried on the next cycle

    def test_exhausted_network_retries_try_again_next_cycle(self):
        sleeps = []
        cf = FakeCF(upload_fail=["fetch failed"] * 4)
        self.assertEqual(self.cycle(cf, sleeps=sleeps), "failed-network")
        self.assertEqual(sleeps, [10, 60, 300])
        self.assertEqual(self.cycle(cf), "deployed")


class TestRollback(OwnerBase):
    def test_failed_health_rolls_back(self):
        def bad_http(url):
            if url.endswith("/app"):
                return 500, ""
            return good_http(url)
        cf = FakeCF()
        self.assertEqual(self.cycle(cf, http=bad_http), "rolled-back")
        self.assertEqual(cf.live, OLD_VID)
        self.assertEqual(self.posts, [(42, "rolled-back", SHA)])
        st = owner.load_state(self.root)
        self.assertEqual(st["shas"][SHA]["state"], "rolled-back")
        self.assertEqual(st["rollbacks"], 1)
        self.assertEqual(self.cycle(cf, http=bad_http), "idle")

    def test_gate_down_rolls_back(self):
        cf = FakeCF()
        self.assertEqual(self.cycle(cf, http=lambda u: (200, "")), "rolled-back")
        self.assertEqual(cf.live, OLD_VID)


class TestRollbackEdges(OwnerBase):
    def test_health_exception_rolls_back(self):
        cf = FakeCF()
        with mock.patch.object(owner, "health", side_effect=RuntimeError("boom")):
            self.assertEqual(self.cycle(cf), "rolled-back")
        self.assertEqual(cf.live, OLD_VID)

    def test_failed_rollback_is_not_reported_as_rolled_back(self):
        cf = FakeCF(deploy_fail=[])
        orig = cf.__call__
        def bad_http(url):
            return (500, "") if url.endswith("/app") else good_http(url)
        calls = {"n": 0}
        def runner(cmd, cwd=None, **kw):
            if cmd[2:4] == ["versions", "deploy"]:
                calls["n"] += 1
                if calls["n"] == 2:
                    return cp(1, err="Authentication error")
            return orig(cmd, cwd=cwd)
        self.assertEqual(self.cycle(runner, http=bad_http), "rollback-failed")
        self.assertEqual(self.posts, [])


class TestNudge(unittest.TestCase):
    def test_ops_share_autodeploy_touches_wake(self):
        from kb.ops import core
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("kb.share.autodeploy.enabled", lambda root: True), \
                mock.patch("kb.share.autodeploy.trigger") as trig, \
                mock.patch("kb.share.autodeploy.run_foreground") as fg, \
                mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": ""}):
            core.share_autodeploy("commit_op x", tmp)
            core.share_autodeploy("nightly sync", tmp, foreground=True)
            self.assertTrue(Path(tmp, ".cache", "share", "wake").is_file())
            trig.assert_not_called()
            fg.assert_not_called()

    def test_direct_escape_keeps_old_path(self):
        from kb.ops import core
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("kb.share.autodeploy.trigger") as trig, \
                mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": "1"}):
            core.share_autodeploy("commit_op x", tmp)
            trig.assert_called_once()
            self.assertFalse(Path(tmp, ".cache", "share", "wake").exists())

    def test_disabled_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"KB_SHARE_AUTODEPLOY": "0"}):
            self.assertEqual(owner.nudge("x", tmp), "disabled")

    def test_ship_merge_goes_through_ops_share_autodeploy(self):
        src = Path(__file__).resolve().parents[2] / "src" / "kb" / "git" / "ship.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("ops_core.share_autodeploy(", text)
        self.assertNotIn("autodeploy.trigger", text)


class TestSingleInstance(unittest.TestCase):
    def test_second_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with owner.single_instance(tmp):
                with self.assertRaises(dp.LockHeld):
                    with owner.single_instance(tmp):
                        pass
            with owner.single_instance(tmp):  # released after exit
                pass

    def test_run_exits_when_another_owner_holds_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(owner, "cycle") as cyc:
            with owner.single_instance(tmp):
                self.assertEqual(owner.run(tmp, max_cycles=1), 1)
            cyc.assert_not_called()
            self.assertEqual(owner.run(tmp, max_cycles=1), 0)
            cyc.assert_called_once()


if __name__ == "__main__":
    unittest.main()

"""Tests for kb_distillery.publish.cloudflare.owner: dedupe per sha, retry classifier, rollback on failed health, nudging
callers, single instance. wrangler, git, http, the builder and the event poster are all mocked."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb_distillery.publish.cloudflare import deploy as dp
from kb_distillery.publish.cloudflare import owner

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
                     "tunneling socket could not be established", "502 Bad Gateway", "HTTP 503",
                     "START CF API RESPONSE: Internal Server Error 500",
                     "failed. An unknown error has occurred. If this error persists, ... [code: 10013]"):
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
        from kb_distillery.ops import core
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("kb_distillery.publish.cloudflare.autodeploy.enabled", lambda root: True), \
                mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger") as trig, \
                mock.patch("kb_distillery.publish.cloudflare.autodeploy.run_foreground") as fg, \
                mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": ""}):
            core.share_autodeploy("commit_op x", tmp)
            core.share_autodeploy("nightly sync", tmp, foreground=True)
            self.assertTrue(Path(tmp, ".cache", "share", "wake").is_file())
            trig.assert_not_called()
            fg.assert_not_called()

    def test_direct_escape_keeps_old_path(self):
        from kb_distillery.ops import core
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger") as trig, \
                mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": "1"}):
            core.share_autodeploy("commit_op x", tmp)
            trig.assert_called_once()
            self.assertFalse(Path(tmp, ".cache", "share", "wake").exists())

    def test_disabled_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"KB_SHARE_AUTODEPLOY": "0"}):
            self.assertEqual(owner.nudge("x", tmp), "disabled")

    def test_ship_merge_goes_through_ops_share_autodeploy(self):
        src = Path(__file__).resolve().parents[3] / "src" / "kb_distillery" / "git" / "ship.py"
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


    def test_run_exits_for_restart_when_code_changes(self):
        hashes = iter(["h1", "h1", "h2"])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(owner, "cycle") as cyc, \
                mock.patch.object(owner.time, "sleep"):
            self.assertEqual(owner.run(tmp, poll=0, max_cycles=5, hasher=lambda: next(hashes)), 0)
        cyc.assert_called_once()  # the second cycle never ran: it exited on the changed hash

    def test_code_hash_tracks_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.js"
            f.write_text("x")
            h = owner.code_hash([(tmp, "*.js")])
            self.assertEqual(h, owner.code_hash([(tmp, "*.js")]))
            f.write_text("y")
            self.assertNotEqual(h, owner.code_hash([(tmp, "*.js")]))

    def test_supersede_marks_older_pending_only(self):
        state = {"shas": {"a": {"state": "failed-network"}, "b": {"state": "deployed"},
                          "c": {"state": "failed"}, "d": {"state": "failed-network"}}}
        self.assertEqual(owner.supersede(state, "d"), 1)
        self.assertEqual(state["shas"]["a"]["state"], "superseded")
        self.assertEqual(state["shas"]["c"]["state"], "failed")
        self.assertEqual(state["shas"]["d"]["state"], "failed-network")


class ModuleErrorTests(unittest.TestCase):
    def test_unresolvable_module_is_retried_once_then_terminal(self):
        err = 'build failed: Could not resolve "./flags.gen.js"'
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(owner, "fetch_main", return_value=SHA), \
                mock.patch.object(owner, "_prune_builds"), mock.patch.object(dp, "status_file") as sf:
            sf.return_value = mock.Mock()
            boom = mock.Mock(side_effect=RuntimeError(err))
            self.assertEqual(owner.cycle(tmp, builder=boom, sleep=lambda s: None), "failed-module")
            self.assertEqual(owner.cycle(tmp, builder=boom, sleep=lambda s: None), "failed")
            self.assertEqual(owner.cycle(tmp, builder=boom, sleep=lambda s: None), "idle")


if __name__ == "__main__":
    unittest.main()


# ---------- launchd env capture + TLS reason ----------
def test_tls_reason_classification():
    from kb_distillery.publish.cloudflare import owner as ow
    wr = ("TypeError: fetch failed\n▲ [WARNING] ... a corporate proxy or VPN ... certificate mismatch")
    assert ow.tls_reason(wr) == ow.TLS_REASON
    assert ow.is_network_error(wr)  # still retried
    assert ow.tls_reason("TypeError: fetch failed") is None
    assert ow.describe(ow.NetworkError(wr)).startswith("TLS: proxy CA missing")
    assert ow.describe(RuntimeError("boom")) == "boom"
    assert ow.is_network_error("SSL certificate problem: unable to get local issuer certificate")


def test_install_script_captures_env_without_secrets(tmp_path):
    import os, plistlib, shutil, subprocess, sys
    import pytest
    if sys.platform != "darwin" or not shutil.which("plutil"):
        pytest.skip("plutil (macOS) required")
    script = Path(__file__).resolve().parents[3] / "examples/launchd/install-deploy-owner.sh"
    plist = tmp_path / "p.plist"
    plist.write_bytes(plistlib.dumps({"Label": "x"}))
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
           "NODE_EXTRA_CA_CERTS": "/etc/ca dir/root.pem", "https_proxy": "http://proxy:8080",
           "CLOUDFLARE_API_TOKEN": "s3cret", "HTTP_PROXY": "http://u:pw@p:1", "SOME_KEY": "k"}
    out = subprocess.run(["bash", "-c", f'source "{script}" && capture_env "{plist}"'],
                         env=env, capture_output=True, text=True, check=True).stdout
    got = plistlib.loads(plist.read_bytes())["EnvironmentVariables"]
    assert got["NODE_EXTRA_CA_CERTS"] == "/etc/ca dir/root.pem"
    assert got["https_proxy"] == "http://proxy:8080"
    assert "HTTP_PROXY" not in got and "CLOUDFLARE_API_TOKEN" not in got and "SOME_KEY" not in got
    assert "/usr/bin" in got["PATH"]
    assert "s3cret" not in out and "NODE_EXTRA_CA_CERTS" in out

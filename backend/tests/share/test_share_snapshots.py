#!/usr/bin/env python3
"""Tests for backend/src/kb/share snapshots (audit, snapshot, list, remove, prune) and cf_api.

Cloudflare is mocked at cf_api's helpers (list_scripts, latest_deployment, delete_worker, views,
fetch_manifest) and at the network seams (run, http_json, http_get); the build is a stub that
returns a temp dir with an index.html carrying the embedded kb-data.
"""
import contextlib
import datetime as _dt
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb.paths import vault_root
ROOT = vault_root()

from kb.share import __main__ as share_main
from kb.share import cf_api, snapshots
from kb.share.contracts import DeployResult, snapshot_worker_name

TODAY = _dt.date(2026, 10, 21)
W_A = "snapshot-20261020-alpha"
W_B = "snapshot-20261021-beta"
MANIFEST = {"content_ref": "kb-0.9.4", "content_sha": "a" * 40, "kb_version": "0.9.4", "viewer_sha": "b" * 40,
            "profile": "public", "sha256": "0" * 64, "built_at": "2026-10-01T00:00:00+00:00"}


def page(slug, ptype, body="", **fm):
    return {"card": {"id": slug, "title": slug, "type": ptype, "preview": body[:40]}, "frontmatter": dict(type=ptype, **fm),
            "markdown": body, "backlinks": [], "outbound": [], "suggested": []}


def data_of(*pages):
    return {"graph": {"nodes": [{"id": p["card"]["id"], "type": p["card"]["type"]} for p in pages], "links": []},
            "index": {"pages": [p["card"] for p in pages], "links": []},
            "pages": {p["card"]["id"]: p for p in pages}}


CLEAN = data_of(page("tensor-rank", "concept", "Rank of a tensor; see [[cp-decomposition]]."),
                page("2019-some-paper", "paper", "Problem: bounds on rank.", year="2019"))
DIRTY = data_of(page("tensor-rank", "concept", "Rank of a tensor."),
                page("jane-doe", "person", "Jane works at Example. Write to jane.doe@example.org or call 054-123-4567."),
                page("2019-some-paper", "paper", "Scanned from `raw/papers/x/2019-some-paper.pdf`."))


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = share_main.main(argv)
    return rc, out.getvalue()


class StubBuild:
    """Replaces snapshots.audit_build: writes the embedded data into a temp dir like a public build."""

    def __init__(self, data, manifest=MANIFEST):
        self.data, self.manifest = data, manifest

    def __call__(self, ref, root=None):
        tmp = tempfile.TemporaryDirectory(prefix="kb-share-test-")
        d = Path(tmp.name) / "public"
        d.mkdir()
        html = ('<!DOCTYPE html><html><head><script type="application/json" id="kb-data">'
                + snapshots.json.dumps(self.data) + "</script></head><body></body></html>")
        (d / "index.html").write_text(html, encoding="utf-8")
        (d / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        report = snapshots.scan(snapshots.extract_data(html))
        report["manifest"] = dict(self.manifest)
        return report, d, tmp


class FakeCloudflare:
    """In-memory Workers registry standing in for cf_api's helpers."""

    def __init__(self, scripts=(), messages=None, manifests=None, views=None, delete_rc=0, versions=None):
        self.scripts = list(scripts)
        self.messages = dict(messages or {})
        # worker → [{version_id, created_on, message}] newest first; default: one version with its message
        self.versions = dict(versions or {})
        self.manifests = dict(manifests or {})
        self._views = views
        self.delete_rc = delete_rc
        self.deleted = []

    def list_scripts(self):
        return [{"name": n, "created_on": "2026-10-20T10:00:00Z", "modified_on": "2026-10-20T10:00:00Z"}
                for n in sorted(self.scripts)]

    def latest_deployment(self, name):
        if name in self.versions and self.versions[name]:
            head = self.versions[name][0]
            return {"message": head["message"], "created_on": head["created_on"], "version_id": head["version_id"]}
        if name not in self.messages:
            return None
        return {"message": self.messages[name], "created_on": "2026-10-20T11:00:00Z", "version_id": "v1"}

    def list_versions(self, name):
        if name in self.versions:
            return list(self.versions[name])
        if name in self.messages:
            return [{"version_id": "v1", "created_on": "2026-10-20T11:00:00Z", "message": self.messages[name]}]
        return []

    def delete_worker(self, name):
        self.deleted.append(name)
        if self.delete_rc:
            return "boom"
        self.scripts.remove(name)
        return None

    def views(self, names, days=7):
        return self._views

    def fetch_manifest(self, url, timeout=10):
        name = url.split("//", 1)[1].split(".", 1)[0]
        m = self.manifests.get(name, "down")
        if m == "timeout":
            return "timeout", None
        if m == "down":
            return "down", None
        return "ok", m

    @contextlib.contextmanager
    def patched(self):
        with mock.patch.object(cf_api, "list_scripts", self.list_scripts), \
                mock.patch.object(cf_api, "latest_deployment", self.latest_deployment), \
                mock.patch.object(cf_api, "delete_worker", self.delete_worker), \
                mock.patch.object(cf_api, "list_versions", self.list_versions), \
                mock.patch.object(cf_api, "views", self.views), \
                mock.patch.object(cf_api, "fetch_manifest", self.fetch_manifest):
            yield


class NameTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(snapshot_worker_name("test-pub", TODAY), "snapshot-20261021-test-pub")

    def test_rejected_with_reason(self):
        for bad, why in (("kb", "reserved"), ("KB", "lowercase"), ("my_snap", "lowercase"), ("-x", "lowercase"),
                         ("", "empty"), ("a" * 70, "max"), ("snäp", "lowercase")):
            with self.assertRaises(ValueError, msg=bad) as cm:
                snapshot_worker_name(bad, TODAY)
            self.assertIn(why, str(cm.exception))


class AuditTests(unittest.TestCase):
    def test_scan_counts_and_flags(self):
        r = snapshots.scan(DIRTY)
        self.assertEqual(r["counts"], {"concept": 1, "paper": 1, "person": 1})
        kinds = {(f["kind"], f["page"]) for f in r["flags"]}
        self.assertEqual(kinds, {("person", "jane-doe"), ("email", "jane-doe"), ("phone", "jane-doe"),
                                 ("raw-path", "2019-some-paper")})
        self.assertIn("jane.doe@example.org", [f["detail"] for f in r["flags"]])

    def test_scan_clean(self):
        r = snapshots.scan(CLEAN)
        self.assertEqual(r["flags"], [])
        self.assertEqual(r["pages"], 2)

    def test_scan_flags_chat_and_distilled(self):
        r = snapshots.scan(data_of(page("conversation-2026-10-01-foo", "source"), page("x", "distilled-think")))
        self.assertEqual({f["kind"] for f in r["flags"]}, {"chat", "distilled-think"})

    def test_cli_exit_codes(self):
        with mock.patch.object(snapshots, "audit_build", StubBuild(DIRTY)):
            rc, out = run_cli(["audit", "kb-0.9.4"])
            self.assertEqual(rc, 1)
            self.assertIn("person", out)
            self.assertIn("jane.doe@example.org", out)
            rc, _ = run_cli(["audit", "kb-0.9.4", "--allow-flags"])
            self.assertEqual(rc, 0)
        with mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            rc, out = run_cli(["audit", "kb-0.9.4"])
            self.assertEqual(rc, 0)
            self.assertIn("flags: none", out)

    def test_build_error_is_a_message(self):
        with mock.patch.object(snapshots, "audit_build", side_effect=RuntimeError("unknown ref 'nope'")):
            rc, out = run_cli(["audit", "nope"])
        self.assertEqual(rc, 1)
        self.assertIn("unknown ref", out)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.deploys = []
        patches = [mock.patch.object(snapshots, "_utc_today", lambda: TODAY),
                   mock.patch.object(snapshots, "CACHE_DIR", Path(self.tmp)),
                   mock.patch("kb.share.deploy.deploy", self.fake_deploy)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_deploy(self, build_dir, worker, **kw):
        self.deploys.append((worker, kw))
        return DeployResult(state="deployed", url=snapshots.worker_url(worker), version_id="v2")

    def test_rejects_bad_name(self):
        rc, out = run_cli(["snapshot", "kb", "main"])
        self.assertEqual(rc, 2)
        self.assertIn("reserved", out)
        self.assertEqual(self.deploys, [])

    def test_refuses_on_flags_then_allows(self):
        cf = FakeCloudflare()
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(DIRTY)):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4"])
            self.assertEqual(rc, 1)
            self.assertEqual(self.deploys, [])
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--allow-flags"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.deploys), 1)

    def test_creates_public_worker(self):
        cf = FakeCloudflare(scripts=["kb"])
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4"])
        self.assertEqual(rc, 0)
        worker, kw = self.deploys[0]
        self.assertEqual(worker, "snapshot-20261021-pub")
        self.assertFalse(kw["require_access"])
        self.assertEqual(kw["message"], f"kb-share {'a' * 40} 0.9.4 public")
        self.assertEqual(Path(kw["status_path"]).name, "status-snapshot-20261021-pub.json")
        self.assertIn("https://snapshot-20261021-pub.yonatan-magen-thesis.workers.dev/", out)

    def test_existing_name_refused_without_replace(self):
        cf = FakeCloudflare(scripts=["kb", "snapshot-20261001-pub"],
                            messages={"snapshot-20261001-pub": f"kb-share {'b' * 40} 0.9.3 public"})
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4"])
            self.assertEqual(rc, 1)
            self.assertIn("--replace", out)
            self.assertEqual(self.deploys, [])
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--replace"])
        self.assertEqual(rc, 0)
        worker, kw = self.deploys[0]
        self.assertEqual(worker, "snapshot-20261001-pub")  # same Worker, same URL
        self.assertFalse(kw["force"])                       # never-same / never-older guard stays on
        self.assertIn("update: snapshot-20261001-pub serves kb 0.9.3 → will serve kb 0.9.4 at the same URL", out)
        self.assertIn("replaced snapshot-20261001-pub", out)
        self.assertIn("share history pub", out)
        self.assertIn("https://snapshot-20261001-pub.yonatan-magen-thesis.workers.dev/", out)

    def test_replace_reports_same_and_refuses_older_without_force(self):
        cf = FakeCloudflare(scripts=["snapshot-20261001-pub"],
                            manifests={"snapshot-20261001-pub": {"kb_version": "0.9.6"}})
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            with mock.patch("kb.share.deploy.deploy", return_value=DeployResult(state="skipped-same")):
                rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--replace"])
            self.assertEqual(rc, 0)
            self.assertIn("already serves this content", out)
            with mock.patch("kb.share.deploy.deploy",
                            return_value=DeployResult(state="skipped-older", error="live abc is not an ancestor")):
                rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--replace"])
            self.assertEqual(rc, 1)
            self.assertIn("NEWER", out)
            self.assertIn("--force", out)
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--replace", "--force"])
        self.assertEqual(rc, 0)
        worker, kw = self.deploys[-1]
        self.assertTrue(kw["force"])
        self.assertIn("downgrade allowed", out)

    def test_force_without_replace_never_bypasses_the_guard(self):
        cf = FakeCloudflare(scripts=["kb"])
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--force"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.deploys[0][1]["force"])

    def test_dry_run_deploys_nothing(self):
        cf = FakeCloudflare()
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("dry-run: would create snapshot-20261021-pub", out)
        self.assertEqual(self.deploys, [])

    def test_failed_deploy_reported(self):
        cf = FakeCloudflare()
        with cf.patched(), mock.patch.object(snapshots, "audit_build", StubBuild(CLEAN)), \
                mock.patch("kb.share.deploy.deploy", return_value=DeployResult(state="failed", error="wrangler exited 1")):
            rc, out = run_cli(["snapshot", "pub", "kb-0.9.4"])
        self.assertEqual(rc, 1)
        self.assertIn("wrangler exited 1", out)


HISTORY = ["0.9.6", "0.9.5", "0.9.4", "0.9.3"]
_ORIGINAL_MAIN_VERSIONS = snapshots.main_versions


class ListTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(snapshots, "main_versions", lambda *a, **k: HISTORY)
        p.start()
        self.addCleanup(p.stop)

    def test_list_filters_and_fields(self):
        cf = FakeCloudflare(
            scripts=["kb", W_A, W_B, "snapshot-20261021-notours", "other-app"],
            messages={"kb": "kb-share " + "c" * 40 + " 0.9.6 private", W_A: "kb-share " + "a" * 40 + " 0.9.4 public",
                      W_B: "kb-share " + "d" * 40 + " 0.9.6 public", "snapshot-20261021-notours": "manual upload",
                      "other-app": "kb-share zzz 0.1.0 public"},
            manifests={W_A: MANIFEST, W_B: "timeout"},
            views={W_A: 12, W_B: 0})
        with cf.patched():
            rows = snapshots.list_snapshots()
        self.assertEqual([r["worker"] for r in rows], [W_A, W_B])
        a, b = rows
        self.assertEqual((a["version"], a["behind_main"], a["views"], a["online"]), ("0.9.4", 2, 12, True))
        self.assertEqual((b["version"], b["behind_main"], b["views"], b["online"]), ("0.9.6", 0, 0, "unknown"))
        self.assertEqual(a["deployed_at"], "2026-10-20T11:00:00Z")
        self.assertEqual(a["url"], "https://snapshot-20261020-alpha.yonatan-magen-thesis.workers.dev/")

    def test_views_unavailable_is_zero_with_note(self):
        cf = FakeCloudflare(scripts=[W_A], messages={W_A: "kb-share " + "a" * 40 + " 0.9.4 public"},
                            manifests={W_A: MANIFEST}, views=None)
        with cf.patched():
            rc, out = run_cli(["list"])
            self.assertEqual(rc, 0)
            self.assertIn("analytics unavailable", out)
            self.assertIn("unknown", snapshots._online_str("unknown"))
            rc, out = run_cli(["list", "--json"])
        rows = json.loads(out)
        self.assertEqual((rows[0]["views"], rows[0]["views_note"]), (0, "analytics unavailable"))

    def test_behind_main_math(self):
        self.assertEqual(snapshots.behind_main("0.9.4", HISTORY), 2)
        self.assertEqual(snapshots.behind_main("kb-0.9.6", HISTORY), 0)
        self.assertIsNone(snapshots.behind_main("0.8.0", HISTORY))
        self.assertIsNone(snapshots.behind_main("", HISTORY))

    def test_main_versions_from_trailers(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

        def g(*args):
            return subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True, text=True, env=env)

        g("init", "-q", "-b", "main")
        g("config", "user.name", "t")
        g("config", "user.email", "t@t")
        for i, v in enumerate(("0.9.4", "0.9.5", "0.9.5", "0.9.6")):
            Path(tmp, f"{i}.md").write_text(v)
            g("add", "-A")
            g("commit", "-q", "-m", f"kb(refine): step {i} (kb-{v})\n\nKB-Version: {v}\nKB-Op: refine\nKB-Target: x")
        versions = _ORIGINAL_MAIN_VERSIONS(Path(tmp))
        self.assertEqual(versions, ["0.9.6", "0.9.5", "0.9.4"])

    def test_empty(self):
        with FakeCloudflare(scripts=["kb"]).patched():
            rc, out = run_cli(["list"])
        self.assertEqual(rc, 0)
        self.assertIn("no snapshots", out)




TRAIL = [
    {"version_id": "v3", "created_on": "2026-10-22T09:00:00Z", "message": f"kb-share {'c' * 40} 0.9.6 public"},
    {"version_id": "v2", "created_on": "2026-10-21T09:00:00Z", "message": f"kb-share {'b' * 40} 0.9.5 public"},
    {"version_id": "v1", "created_on": "2026-10-20T09:00:00Z", "message": f"kb-share {'a' * 40} 0.9.4 public"},
]


class HistoryTests(unittest.TestCase):
    def test_trail_marks_live_and_counts_updates(self):
        cf = FakeCloudflare(scripts=["snapshot-20261020-pub"], versions={"snapshot-20261020-pub": TRAIL},
                            messages={"snapshot-20261020-pub": TRAIL[0]["message"]})
        with cf.patched():
            rows = snapshots.history("snapshot-20261020-pub")
            rc, out = run_cli(["history", "pub"])
        self.assertEqual([r["version"] for r in rows], ["0.9.6", "0.9.5", "0.9.4"])
        self.assertEqual([r["live"] for r in rows], [True, False, False])
        self.assertEqual(rc, 0)
        self.assertIn("2 update(s) since it was created", out)
        self.assertIn("rollback --worker snapshot-20261020-pub --to <version id>", out)
        self.assertIn("v3", out)

    def test_json_and_missing(self):
        cf = FakeCloudflare(scripts=["snapshot-20261020-pub"], versions={"snapshot-20261020-pub": TRAIL})
        with cf.patched():
            rc, out = run_cli(["history", "pub", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["worker"], "snapshot-20261020-pub")
            self.assertEqual(len(data["versions"]), 3)
            rc, out = run_cli(["history", "nope"])
        self.assertEqual(rc, 1)
        self.assertIn("no snapshot Worker matches", out)

    def test_list_shows_updates_and_first_version(self):
        cf = FakeCloudflare(scripts=["snapshot-20261020-pub", "snapshot-20261021-fresh"],
                            versions={"snapshot-20261020-pub": TRAIL},
                            messages={"snapshot-20261020-pub": TRAIL[0]["message"],
                                      "snapshot-20261021-fresh": f"kb-share {'d' * 40} 0.9.6 public"},
                            views={"snapshot-20261020-pub": 0, "snapshot-20261021-fresh": 0})
        with cf.patched(), mock.patch.object(snapshots, "main_versions", lambda *a, **k: HISTORY):
            rows = snapshots.list_snapshots(fetch_manifests=False)
            rc, out = run_cli(["list"])
        by = {r["worker"]: r for r in rows}
        self.assertEqual((by["snapshot-20261020-pub"]["updates"], by["snapshot-20261020-pub"]["first_version"]), (2, "0.9.4"))
        self.assertEqual((by["snapshot-20261021-fresh"]["updates"], by["snapshot-20261021-fresh"]["first_version"]), (0, "0.9.6"))
        self.assertEqual(rc, 0)
        self.assertIn("2 (was 0.9.4)", out)


class RemoveTests(unittest.TestCase):
    def test_kb_always_refused(self):
        cf = FakeCloudflare(scripts=["kb", W_A])
        with cf.patched():
            rc, out = run_cli(["remove", "kb", "--yes"])
            self.assertEqual(rc, 1)
            self.assertIn("live site", out)
            self.assertIsNotNone(snapshots.remove_snapshot("kb"))
        self.assertEqual(cf.deleted, [])

    def test_wrong_confirmation_deletes_nothing(self):
        cf = FakeCloudflare(scripts=["kb", W_A])
        with cf.patched(), mock.patch("builtins.input", return_value="snapshot-20261020-alph"):
            rc, out = run_cli(["remove", "alpha"])
        self.assertEqual(rc, 1)
        self.assertIn("nothing deleted", out)
        self.assertEqual(cf.deleted, [])

    def test_typed_name_deletes_and_verifies(self):
        cf = FakeCloudflare(scripts=["kb", W_A], messages={W_A: "kb-share " + "a" * 40 + " 0.9.4 public"},
                            manifests={W_A: MANIFEST}, views={})
        with cf.patched(), mock.patch("builtins.input", return_value=W_A), \
                mock.patch.object(snapshots, "main_versions", lambda *a, **k: HISTORY):
            rc, out = run_cli(["remove", "alpha"])
            self.assertEqual(rc, 0)
            self.assertEqual(cf.deleted, [W_A])
            self.assertIn("is gone", out)
            rc, out = run_cli(["list"])
        self.assertIn("no snapshots", out)

    def test_delete_failure_names_worker(self):
        cf = FakeCloudflare(scripts=["kb", W_A], delete_rc=1)
        with cf.patched():
            rc, out = run_cli(["remove", W_A, "--yes"])
        self.assertEqual(rc, 1)
        self.assertIn(W_A, out)
        self.assertIn("boom", out)

    def test_ambiguous_and_missing(self):
        cf = FakeCloudflare(scripts=["kb", W_A, "snapshot-20261021-alpha"])
        with cf.patched():
            rc, out = run_cli(["remove", "alpha", "--yes"])
            self.assertEqual(rc, 1)
            self.assertIn("ambiguous", out)
            self.assertIn("snapshot-20261021-alpha", out)
            rc, out = run_cli(["remove", "gamma", "--yes"])
            self.assertEqual(rc, 1)
            self.assertIn("no snapshot Worker", out)
        self.assertEqual(cf.deleted, [])


class PruneTests(unittest.TestCase):
    def make(self, delete_rc=0):
        return FakeCloudflare(scripts=["kb", W_A, W_B, "snapshot-20261001-dead", "other-app"],
                              manifests={W_A: MANIFEST, W_B: "timeout"}, delete_rc=delete_rc)

    def test_dry_run_lists(self):
        cf = self.make()
        with cf.patched():
            rc, out = run_cli(["prune"])
        self.assertEqual(rc, 0)
        self.assertIn("orphan    snapshot-20261001-dead", out)
        self.assertIn("not ours  other-app", out)
        self.assertIn("unknown   snapshot-20261021-beta", out)
        self.assertNotIn("orphan    kb", out)
        self.assertEqual(cf.deleted, [])

    def test_apply_deletes_only_orphans(self):
        cf = self.make()
        with cf.patched():
            rc, out = run_cli(["prune", "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(cf.deleted, ["snapshot-20261001-dead"])
        self.assertIn("deleted   snapshot-20261001-dead", out)
        self.assertIn("other-app", cf.scripts)

    def test_nothing_to_prune(self):
        cf = FakeCloudflare(scripts=["kb", W_A], manifests={W_A: MANIFEST})
        with cf.patched():
            rc, out = run_cli(["prune", "--apply"])
        self.assertEqual(rc, 0)
        self.assertIn("no orphans", out)
        self.assertEqual(cf.deleted, [])


class CfApiTests(unittest.TestCase):
    def test_token_env_wins_and_is_never_printed(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "secret-token"}):
            self.assertEqual(cf_api.api_token(), "secret-token")

    def test_token_from_wrangler_config(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        cfg = Path(tmp, "default.toml")
        cfg.write_text('oauth_token = "oauth-xyz"\nexpiration_time = "2999-01-01T00:00:00Z"\n')
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": ""}), mock.patch.object(cf_api, "WRANGLER_CONFIG", cfg):
            self.assertEqual(cf_api.api_token(), "oauth-xyz")
        cfg.write_text("")
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": ""}), mock.patch.object(cf_api, "WRANGLER_CONFIG", cfg):
            with self.assertRaises(cf_api.CloudflareError):
                cf_api.api_token()

    def test_list_scripts_and_errors(self):
        payload = {"success": True, "result": [{"id": "kb"}, {"id": W_A, "created_on": "x", "modified_on": "y"}]}
        with mock.patch.object(cf_api, "api_token", return_value="t"), \
                mock.patch.object(cf_api, "http_json", return_value=(200, payload)) as hj:
            names = [s["name"] for s in cf_api.list_scripts()]
            self.assertEqual(names, ["kb", W_A])
            self.assertEqual(hj.call_args[0][3]["Authorization"], "Bearer t")
        with mock.patch.object(cf_api, "api_token", return_value="t"), \
                mock.patch.object(cf_api, "http_json", return_value=(403, {"success": False, "errors": [{"code": 10000, "message": "nope"}]})):
            with self.assertRaises(cf_api.CloudflareError) as cm:
                cf_api.list_scripts()
            self.assertIn("nope", str(cm.exception))

    def test_views_parses_and_degrades(self):
        rows = [{"sum": {"requests": 7}, "dimensions": {"scriptName": W_A}},
                {"sum": {"requests": 5}, "dimensions": {"scriptName": W_A}},
                {"sum": {"requests": 99}, "dimensions": {"scriptName": "kb"}}]
        ok = {"data": {"viewer": {"accounts": [{"workersInvocationsAdaptive": rows}]}}}
        with mock.patch.object(cf_api, "api_token", return_value="t"), \
                mock.patch.object(cf_api, "http_json", return_value=(200, ok)):
            self.assertEqual(cf_api.views([W_A, W_B]), {W_A: 12, W_B: 0})
        with mock.patch.object(cf_api, "api_token", return_value="t"), \
                mock.patch.object(cf_api, "http_json", return_value=(200, {"errors": [{"message": "no scope"}], "data": None})):
            self.assertIsNone(cf_api.views([W_A]))
        with mock.patch.object(cf_api, "api_token", side_effect=cf_api.CloudflareError("no creds")):
            self.assertIsNone(cf_api.views([W_A]))

    def test_latest_deployment_from_wrangler_json(self):
        def runner(cmd, cwd=None, timeout=600):
            sub = cmd[2]
            if sub == "deployments":
                out = json.dumps([{"id": "old", "versions": [{"version_id": "v0", "percentage": 100}]},
                                  {"id": "d1", "created_on": "2026-10-20T11:00:00Z",
                                   "versions": [{"version_id": "v1", "percentage": 100}]}])
                return subprocess.CompletedProcess(cmd, 0, out, "")
            if sub == "versions":
                out = json.dumps([{"id": "v1", "annotations": {"workers/message": "kb-share abc 0.9.4 public"}}])
                return subprocess.CompletedProcess(cmd, 0, out, "")
            if sub == "delete":
                return subprocess.CompletedProcess(cmd, 1, "", "not found")
            raise AssertionError(cmd)

        with mock.patch.object(cf_api, "run", runner):
            dep = cf_api.latest_deployment(W_A)
            self.assertEqual(dep, {"message": "kb-share abc 0.9.4 public", "created_on": "2026-10-20T11:00:00Z",
                                   "version_id": "v1"})
            self.assertIn("not found", cf_api.delete_worker(W_A))
        with mock.patch.object(cf_api, "run", return_value=subprocess.CompletedProcess([], 1, "", "err")):
            self.assertIsNone(cf_api.latest_deployment(W_A))

    def test_fetch_manifest_states(self):
        with mock.patch.object(cf_api, "http_get", return_value=(200, json.dumps(MANIFEST).encode())):
            self.assertEqual(cf_api.fetch_manifest("https://x.workers.dev/"), ("ok", MANIFEST))
        with mock.patch.object(cf_api, "http_get", return_value=(404, b"")):
            self.assertEqual(cf_api.fetch_manifest("https://x.workers.dev/"), ("down", None))
        with mock.patch.object(cf_api, "http_get", side_effect=TimeoutError("x")):
            self.assertEqual(cf_api.fetch_manifest("https://x.workers.dev/"), ("timeout", None))


if __name__ == "__main__":
    unittest.main()

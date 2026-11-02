"""Public snapshots already shared must keep resolving at the same URLs: this pins the URL and path shape, the name
format, the listing rows and the account defaults, and that the Cloudflare publisher hands the same rows to core.

It lives here, not in tests/publish/cloudflare, because that folder skips itself outside the monorepo layout. Fakes only."""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from kb_distillery.publish import PublishError
from kb_distillery.publish.cloudflare import cf_api, contracts, deploy
from kb_distillery.publish.site import snapshots
from kb_distillery.publish.cloudflare.publisher import CloudflarePublisher

W = "snapshot-20261020-alpha"
MESSAGE = "kb-share " + "a" * 40 + " 0.9.4 public"
ROW_KEYS = {"worker", "name", "date", "url", "sha", "version", "deployed_at", "online", "views", "views_note", "updates",
            "first_version", "behind_main"}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class SnapshotShape(unittest.TestCase):
    def test_the_url_and_path_shape(self):
        sub = contracts.ACCOUNT_SUBDOMAIN
        self.assertEqual(snapshots.worker_url(W), f"https://{W}.{sub}.workers.dev/")              # snapshots: trailing slash
        self.assertEqual(deploy.worker_url("kb"), f"https://kb.{sub}.workers.dev")                # the site: none
        self.assertEqual(deploy.worker_url(W), f"https://{W}.{sub}.workers.dev")

    def test_the_account_comes_from_the_share_config_not_the_code(self):
        """No account is in the code: the subdomain and the account id come from the share config (the fixture in
        tests/conftest.py here); the worker name default is `kb`."""
        if any(os.environ.get(v) for v in ("KB_CLOUDFLARE_SUBDOMAIN", "KB_CLOUDFLARE_ACCOUNT_ID", "KB_CLOUDFLARE_WORKER")):
            self.skipTest("an account is configured in the environment")
        self.assertEqual(contracts.ACCOUNT_SUBDOMAIN, "acme-example")
        self.assertEqual(cf_api.ACCOUNT_ID, "0" * 32)
        self.assertEqual(deploy.CF_ACCOUNT_ID, "0" * 32)
        self.assertEqual(digest(contracts.WORKER_MAIN), "74fec0c33e96ab90")

    def test_the_names(self):
        self.assertEqual((contracts.SNAPSHOT_PREFIX, contracts.DEPLOY_MESSAGE_PREFIX), ("snapshot-", "kb-share"))
        self.assertEqual(contracts.snapshot_worker_name("alpha", dt.date(2026, 10, 20)), W)
        self.assertEqual(snapshots.parse_worker(W), {"date": "20261020", "name": "alpha"})
        self.assertIsNone(snapshots.parse_worker("snapshot-2026-alpha"))
        self.assertIsNone(snapshots.parse_worker(contracts.WORKER_MAIN))
        for bad in ("", "Alpha", "-a", "a-", "kb" if contracts.WORKER_MAIN == "kb" else contracts.WORKER_MAIN):
            with self.assertRaises(ValueError):
                contracts.snapshot_worker_name(bad, dt.date(2026, 10, 20))

    def listing(self):
        patches = [mock.patch.object(cf_api, "list_scripts", return_value=[{"name": W, "modified_on": "m"}, {"name": "other-app"}]),
                   mock.patch.object(cf_api, "latest_deployment", return_value={"message": MESSAGE, "created_on": "2026-10-20T11:00:00Z"}),
                   mock.patch.object(cf_api, "fetch_manifest", return_value=("ok", {"kb_version": "0.9.4", "content_sha": "b" * 40})),
                   mock.patch.object(cf_api, "views", return_value={W: 12}),
                   mock.patch.object(snapshots, "history", return_value=[{"version": "0.9.4"}, {"version": "0.9.3"}]),
                   mock.patch.object(snapshots, "main_versions", return_value=["0.9.6", "0.9.5", "0.9.4"])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_the_listing_format(self):
        self.listing()
        rows = snapshots.list_snapshots()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row), ROW_KEYS)
        self.assertEqual((row["worker"], row["name"], row["date"], row["url"]),
                         (W, "alpha", "20261020", snapshots.worker_url(W)))
        self.assertEqual((row["sha"], row["version"], row["online"], row["views"], row["behind_main"], row["updates"]),
                         ("b" * 40, "0.9.4", True, 12, 2, 1))
        self.assertEqual(row["first_version"], "0.9.3")
        json.dumps(rows)                                                      # `share list --json` prints exactly this

    def test_the_publisher_hands_core_the_same_rows_and_asks_for_nothing_else(self):
        self.listing()
        self.assertEqual(CloudflarePublisher().snapshots(), snapshots.list_snapshots())


class Settings(unittest.TestCase):
    def test_settings_that_differ_from_a_loaded_account_are_refused(self):
        with self.assertRaises(PublishError):
            CloudflarePublisher(subdomain="another-account")
        CloudflarePublisher(subdomain=contracts.ACCOUNT_SUBDOMAIN, account_id=cf_api.ACCOUNT_ID, worker=contracts.WORKER_MAIN)

    def test_any_account_is_configured_not_hard_coded(self):
        code = ("import json; from kb_distillery.publish.cloudflare.publisher import CloudflarePublisher as P; "
                "p = P(account_id='acct-1', subdomain='acme', worker='site'); "
                "from kb_distillery.publish.cloudflare import cf_api, contracts, deploy; from kb_distillery.publish.site import snapshots; "
                "print(json.dumps([cf_api.ACCOUNT_ID, deploy.CF_ACCOUNT_ID, contracts.WORKER_MAIN, snapshots.worker_url('snapshot-20260101-x'), "
                "deploy.worker_url('site')]))")
        env = {k: v for k, v in os.environ.items() if not k.startswith("KB_CLOUDFLARE_")}
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
        self.assertEqual(json.loads(proc.stdout), ["acct-1", "acct-1", "site", "https://snapshot-20260101-x.acme.workers.dev/",
                                                   "https://site.acme.workers.dev"])


if __name__ == "__main__":
    unittest.main()

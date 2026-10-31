"""The Cloudflare publisher passes the publisher contract and delegates to the share code. Fakes only: nothing here
runs wrangler, calls Cloudflare or touches the live site."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb.publish import PublishError, Snapshot
from kb.publish import registry
from kb.share import cf_api, deploy, owner, snapshots
from kb.share.contracts import DeployResult
from kb.share.publisher import CloudflarePublisher
from tests.publish.test_publisher_contract import PublisherContract


class CloudflareContract(PublisherContract, unittest.TestCase):
    def make(self):
        for patcher in (mock.patch.dict(os.environ, {"KB_SHARE_AUTODEPLOY": "0"}),     # a nudge touches nothing
                        mock.patch.object(cf_api, "list_scripts", return_value=[])):    # no Cloudflare call
            patcher.start()
            self.addCleanup(patcher.stop)
        return CloudflarePublisher("/unused")


class CloudflareBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_status_reads_the_status_file_under_a_given_root(self):
        cache = Path(self.tmp.name) / ".cache" / "share"
        cache.mkdir(parents=True)
        (cache / "status.json").write_text('{"state": "deployed", "sha": "abc", "at": "t"}')
        got = CloudflarePublisher().status(self.tmp.name)
        self.assertEqual(got["state"], "deployed")
        self.assertEqual(got["sha"], "abc")
        self.assertIsNone(CloudflarePublisher().status(os.path.join(self.tmp.name, "empty")))

    def test_publishing_the_live_site_is_deploy_main(self):
        seams = {"runner": object()}
        with mock.patch.object(deploy, "deploy_main", return_value=DeployResult("deployed", url="u", version_id="v")) as dm:
            res = CloudflarePublisher(seams=seams).publish(Snapshot("main", options={"force": True}), dry_run=True)
        dm.assert_called_once_with(force=True, dry_run=True, app=True, **seams)
        self.assertEqual((res.state, res.url, res.version), ("deployed", "u", "v"))

    def test_the_live_site_is_only_built_from_main(self):
        with self.assertRaises(PublishError):
            CloudflarePublisher().publish(Snapshot("kb-1.2.3"))

    def test_a_named_snapshot_goes_through_the_snapshot_command(self):
        with mock.patch.object(snapshots, "cmd_snapshot", return_value=0) as cmd:
            res = CloudflarePublisher().publish(Snapshot("kb-1.2.3", name="demo", public=True,
                                                         options={"replace": True, "app": True}), dry_run=True)
        args = cmd.call_args.args[0]
        self.assertEqual((args.name, args.ref, args.replace, args.app, args.dry_run), ("demo", "kb-1.2.3", True, True, True))
        self.assertEqual(res.state, "deployed")
        with mock.patch.object(snapshots, "cmd_snapshot", return_value=1):
            self.assertEqual(CloudflarePublisher().publish(Snapshot("main", name="demo")).state, "failed")

    def test_rollback_targets_the_live_worker(self):
        with mock.patch.object(deploy, "rollback", return_value=DeployResult("deployed")) as rb:
            CloudflarePublisher().rollback("v1")
        self.assertEqual(rb.call_args.args, ("kb", "v1"))

    def test_orphan_snapshots_come_from_the_prune_plan_and_are_empty_when_cloudflare_is_unreachable(self):
        with mock.patch.object(snapshots, "prune_plan", return_value={"orphans": ["snapshot-1-x"]}):
            self.assertEqual(CloudflarePublisher().orphan_snapshots(), ["snapshot-1-x"])
        with mock.patch.object(snapshots, "prune_plan", side_effect=cf_api.CloudflareError("no credentials")):
            self.assertEqual(CloudflarePublisher().orphan_snapshots(), [])

    def test_request_publish_nudges_the_owner_unless_direct(self):
        with mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": "0"}), \
                mock.patch.object(owner, "nudge", return_value="nudged") as nudge:
            self.assertEqual(CloudflarePublisher().request_publish("why", "/r"), "nudged")
        nudge.assert_called_once_with("why", "/r")

    def test_request_publish_direct_triggers_a_background_deploy_or_runs_it_in_the_foreground(self):
        from kb.share import autodeploy
        with mock.patch.dict(os.environ, {"KB_SHARE_DIRECT": "1"}), \
                mock.patch.object(autodeploy, "trigger", return_value="spawned") as trig, \
                mock.patch.object(autodeploy, "run_foreground", return_value=0) as fg:
            self.assertEqual(CloudflarePublisher().request_publish("a", "/r"), "spawned")
            CloudflarePublisher().request_publish("b", "/r", foreground=True)
        trig.assert_called_once_with("a", "/r")
        fg.assert_called_once_with("b", "/r")

    def test_the_account_api_is_the_cloudflare_rest_client(self):
        api = CloudflarePublisher().account_api()
        with mock.patch.object(cf_api, "_rest", return_value={"ok": 1}) as rest:
            self.assertEqual(api.rest("GET", "/x"), {"ok": 1})
        rest.assert_called_once_with("GET", "/x", None)
        self.assertEqual(api.account_id, cf_api.ACCOUNT_ID)

    def test_available_follows_the_credentials_without_calling_anything(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t"}):
            self.assertTrue(CloudflarePublisher().available())
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": ""}), \
                mock.patch.object(cf_api, "_read_wrangler_config", return_value={}):
            self.assertFalse(CloudflarePublisher().available())


class Selection(unittest.TestCase):
    def test_it_is_a_built_in_that_is_only_chosen_by_name(self):
        self.assertIs(registry.load_class("cloudflare"), CloudflarePublisher)
        with mock.patch.dict(os.environ, {registry.ENV: "cloudflare"}):
            self.assertIsInstance(registry.for_kb(None, "/x"), CloudflarePublisher)
        with mock.patch.dict(os.environ, {registry.ENV: ""}):
            self.assertEqual(registry.selected_name(None), "")

    def test_a_package_cannot_take_the_name(self):
        with mock.patch.object(registry, "_entry_points", return_value={"cloudflare": "os.path:join"}):
            self.assertIs(registry.load_class("cloudflare"), CloudflarePublisher)


if __name__ == "__main__":
    unittest.main()

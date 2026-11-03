"""The Worker inbox in the deploy: the R2 binding in wrangler.jsonc, the scripts in the Worker folder, the checker bundle."""
import json
import tempfile
import unittest
from pathlib import Path

from kb_distillery.publish.cloudflare import config as share_config
from kb_distillery.publish.cloudflare import deploy

CFG = {"google_client_id": "id", "allowed_emails": ["me@example.com"], "compatibility_date": "2026-09-01"}


def conf(text: str) -> dict:
    return json.loads("\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//")))


class InboxWranglerTests(unittest.TestCase):
    def test_no_bucket_means_no_binding(self):
        self.assertNotIn("r2_buckets", conf(deploy.render_wrangler("kb", True, CFG)))

    def test_the_bucket_is_bound_as_kb_inbox_on_the_private_site_only(self):
        cfg = {**CFG, "inbox_bucket": "kb-inbox"}
        self.assertEqual(conf(deploy.render_wrangler("kb", True, cfg))["r2_buckets"], [{"binding": "KB_INBOX", "bucket_name": "kb-inbox"}])
        self.assertNotIn("r2_buckets", conf(deploy.render_wrangler("snapshot-x", False, cfg)))   # public snapshots have no inbox


class InboxWorkerDirTests(unittest.TestCase):
    def render(self, private: bool):
        tmp = Path(tempfile.mkdtemp())
        build = tmp / "build"
        build.mkdir()
        (build / "index.html").write_text("<p>x</p>")
        calls = []
        dest = deploy.render_worker_dir(build, "kb", private, CFG, tmp / "out", bundler=lambda out: (calls.append(out), out.write_text("// bundle")))
        return dest, calls

    def test_a_private_site_gets_the_inbox_scripts_and_a_fresh_checker_bundle(self):
        dest, calls = self.render(True)
        for name in ("auth.js", "inbox.js", "zip.js", "okf.gen.js"):
            self.assertTrue((dest / name).is_file(), name)
        self.assertEqual(calls, [dest / "okf.gen.js"])

    def test_a_public_snapshot_gets_none_of_it(self):
        dest, calls = self.render(False)
        self.assertEqual(calls, [])
        self.assertFalse((dest / "inbox.js").exists())

    def test_every_script_the_worker_imports_ships(self):
        import re
        imported = set()
        for name in deploy.WORKER_SCRIPTS:
            imported |= set(re.findall(r'from "\./([\w.-]+)"', (deploy.WORKER_DIR / name).read_text(encoding="utf-8")))
        self.assertLessEqual(imported, set(deploy.WORKER_SCRIPTS))


class InboxSettingsTests(unittest.TestCase):
    def write(self, text: str) -> Path:
        p = Path(tempfile.mkdtemp()) / "share.toml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_the_bucket_comes_from_the_worker_section(self):
        self.assertEqual(share_config.settings(self.write('[worker]\ninbox_bucket = "kb-inbox"\n'))["inbox_bucket"], "kb-inbox")
        self.assertEqual(share_config.settings(self.write("[worker]\n"))["inbox_bucket"], "")

    def test_the_environment_wins(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {"KB_SHARE_INBOX_BUCKET": "from-env"}):
            self.assertEqual(share_config.settings(self.write('[worker]\ninbox_bucket = "file"\n'))["inbox_bucket"], "from-env")

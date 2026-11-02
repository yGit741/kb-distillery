"""The share config (`kb_distillery.publish.cloudflare.config`): nothing personal is tracked, one reader, a fixed read order,
and a runner without a config refuses to build or deploy. Lives outside tests/publish/cloudflare/ because that folder is
skipped in the split layout and these tests need no monorepo."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb_distillery.publish.cloudflare import config, deploy
from kb_distillery.publish.site import build as sb

CLOUDFLARE_DIR = Path(config.__file__).resolve().parent


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Tree(unittest.TestCase):
    """A fake HOME and knowledge base; the environment names no config unless a test sets one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.home, self.kb = self.tmp / "home", self.tmp / "kb"
        self.kb.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in (config.ENV_FILE, "KB_SHARE_GOOGLE_CLIENT_ID", "KB_SHARE_FLAGS_KV_ID",
                                                                "KB_CLOUDFLARE_SUBDOMAIN")}
        env["HOME"] = str(self.home)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def user_file(self, text):
        return write(self.home / ".config" / "kb-distillery" / "share.toml", text)

    def kb_file(self, text):
        return write(self.kb / ".cache" / "share" / "share.toml", text)


class ReadOrder(Tree):
    def test_env_then_kb_then_user_then_the_example(self):
        self.assertIsNone(config.find(str(self.kb)))
        user = self.user_file('[cloudflare]\nsubdomain = "from-user"\n')
        self.assertEqual(config.find(str(self.kb)), user)
        kb = self.kb_file('[cloudflare]\nsubdomain = "from-kb"\n')
        self.assertEqual(config.find(str(self.kb)), kb)
        env = write(self.tmp / "env.toml", '[cloudflare]\nsubdomain = "from-env"\n')
        with mock.patch.dict(os.environ, {config.ENV_FILE: str(env)}):
            self.assertEqual(config.find(str(self.kb)), env)
            self.assertEqual(config.load(root=str(self.kb))["cloudflare"]["subdomain"], "from-env")
        self.assertEqual(config.load(root=str(self.kb))["cloudflare"]["subdomain"], "from-kb")
        kb.unlink()
        self.assertEqual(config.load(root=str(self.kb))["cloudflare"]["subdomain"], "from-user")

    def test_the_example_fills_gaps_but_is_never_a_config(self):
        self.user_file('[auth]\ngoogle_client_id = "id"\n')
        cfg = config.settings(root=str(self.kb))
        self.assertEqual((cfg["google_client_id"], cfg["allowed_emails"], cfg["compatibility_date"]), ("id", [], config.DEFAULT_COMPAT))

    def test_an_env_file_that_is_missing_is_an_error_not_a_fall_through(self):
        self.user_file('[cloudflare]\nsubdomain = "from-user"\n')
        with mock.patch.dict(os.environ, {config.ENV_FILE: str(self.tmp / "nope.toml")}):
            with self.assertRaises(config.ShareConfigError) as cm:
                config.require(str(self.kb))
            self.assertIn(str(self.tmp / "nope.toml"), str(cm.exception))

    def test_a_broken_file_names_itself(self):
        bad = self.user_file("[auth\n")
        with self.assertRaises(config.ShareConfigError) as cm:
            config.load(root=str(self.kb))
        self.assertIn(str(bad), str(cm.exception))

    def test_environment_overrides_win_over_the_file(self):
        self.user_file('[auth]\ngoogle_client_id = "file-id"\n[cloudflare]\nsubdomain = "file-sub"\n')
        with mock.patch.dict(os.environ, {"KB_SHARE_GOOGLE_CLIENT_ID": "env-id", "KB_CLOUDFLARE_SUBDOMAIN": "env-sub"}):
            self.assertEqual(config.settings(root=str(self.kb))["google_client_id"], "env-id")
            self.assertEqual(config.subdomain(str(self.kb)), "env-sub")

    def test_log_path_defaults_to_a_generic_name_and_follows_the_config(self):
        self.assertEqual(config.log_path(str(self.kb)), self.home / "Library" / "Logs" / "kb-distillery-share.log")
        self.user_file('[share]\nlog_path = "~/elsewhere.log"\n')
        self.assertEqual(config.log_path(str(self.kb)), self.home / "elsewhere.log")

    def test_home_comes_from_the_file(self):
        self.kb_file('[home]\ntour = "first-visit"\n[[home.cards]]\ntitle = "T"\npages = ["a"]\n')
        self.assertEqual(config.home(root=str(self.kb)), {"cards": [{"title": "T", "pages": ["a"]}], "tour": "first-visit"})


class Saving(Tree):
    def test_config_stores_only_what_was_passed_not_env_overrides(self):
        import argparse
        user = self.user_file('[auth]\ngoogle_client_id = "file-id"\nallowed_emails = ["a@b.c"]\n[home]\ntour = "t"\n')
        with mock.patch.dict(os.environ, {"KB_SHARE_GOOGLE_CLIENT_ID": "env-id"}):
            deploy.cmd_config(argparse.Namespace(google_client_id=None, allowed_emails="x@y.z,q@w.e"))
        text = user.read_text()
        self.assertIn('google_client_id = "file-id"', text)
        self.assertIn('allowed_emails = ["x@y.z", "q@w.e"]', text)
        self.assertIn('tour = "t"', text)

    def test_a_set_but_missing_env_file_is_where_values_are_written(self):
        target = self.tmp / "new.toml"
        with mock.patch.dict(os.environ, {config.ENV_FILE: str(target)}):
            deploy.save_config({"google_client_id": "id", "allowed_emails": []})
        self.assertIn('google_client_id = "id"', target.read_text())
        self.assertFalse(config.user_path().exists())


class CleanRunner(Tree):
    def test_require_lists_where_a_config_can_go(self):
        with self.assertRaises(config.ShareConfigError) as cm:
            config.require(str(self.kb))
        msg = str(cm.exception)
        for where in (str(config.kb_path(str(self.kb))), str(config.user_path()), "share.example.toml"):
            self.assertIn(where, msg)

    def test_the_build_refuses_before_any_work(self):
        with self.assertRaises(sb.BuildError) as cm, mock.patch.object(config, "kb_path", return_value=self.kb / "none.toml"):
            sb.build("main", profile="private", root=self.tmp)
        self.assertIn("no share config found", str(cm.exception))

    def test_the_home_load_the_build_does_is_strict(self):
        from kb_distillery.publish.site import home
        self.assertEqual(home.load_home(), {"cards": [], "tour": None})
        with self.assertRaises(home.ShareConfigError):
            home.load_home(strict=True)

    def test_a_deploy_without_a_config_refuses_and_says_why(self):
        build = self.tmp / "build"
        write(build / "manifest.json", json.dumps({"content_sha": "a" * 40, "kb_version": "1.0.0", "profile": "private"}))
        with mock.patch.object(deploy, "STATUS_PATH", self.tmp / "status.json"), mock.patch.object(deploy, "LOG_PATH", self.tmp / "log"), \
                mock.patch.object(config, "kb_path", return_value=self.kb / "none.toml"):
            result = deploy.deploy(build, "kb", require_access=True, dry_run=True)
        self.assertEqual(result.state, "failed")
        self.assertIn("no share config found", result.error)

    def test_a_config_without_the_sign_in_values_does_not_deploy_a_private_site(self):
        with self.assertRaises(config.ShareConfigError) as cm:
            config.check_deploy({"google_client_id": "", "allowed_emails": []}, True, "acme")
        self.assertIn("google_client_id", str(cm.exception))
        self.assertIn("allowed_emails", str(cm.exception))
        config.check_deploy({"google_client_id": "", "allowed_emails": []}, False, "acme")      # a public snapshot needs neither
        with self.assertRaises(config.ShareConfigError):
            config.check_deploy({"google_client_id": "x", "allowed_emails": ["a@b.c"]}, True, "")

    def test_a_private_deploy_needs_the_cloudflare_account_id(self):
        ok = {"google_client_id": "x", "allowed_emails": ["a@b.c"]}
        with mock.patch.dict(os.environ, {"KB_CLOUDFLARE_ACCOUNT_ID": "acct-1"}):
            config.check_deploy(ok, True, "acme")
        with mock.patch.dict(os.environ, {"KB_CLOUDFLARE_ACCOUNT_ID": ""}):
            with self.assertRaises(config.ShareConfigError) as cm:
                config.check_deploy(ok, True, "acme")
            self.assertIn("account_id", str(cm.exception))
            config.check_deploy(ok, False, "acme")                          # a public snapshot does not use the panel


class Tracked(unittest.TestCase):
    def test_no_real_config_is_tracked_and_the_example_holds_no_values(self):
        self.assertFalse((CLOUDFLARE_DIR / "share.toml").exists())
        ex = config.load(config.EXAMPLE)
        self.assertEqual((ex["auth"]["google_client_id"], ex["auth"]["allowed_emails"], ex["cloudflare"]["subdomain"]), ("", [], ""))
        self.assertEqual(ex["cloudflare"]["account_id"], "")
        self.assertTrue(config.EXAMPLE.is_file())

    def test_set_values_changes_only_its_keys(self):
        text = '# keep\n[auth]\ngoogle_client_id = "old"\n\n[home]\ntour = "t"\n'
        out = config.set_values(text, "auth", {"google_client_id": '"new"', "allowed_emails": '["a@b.c"]'})
        self.assertEqual(out, '# keep\n[auth]\ngoogle_client_id = "new"\nallowed_emails = ["a@b.c"]\n\n[home]\ntour = "t"\n')
        self.assertEqual(config.set_values("", "auth", {"k": "1"}), "[auth]\nk = 1\n")


if __name__ == "__main__":
    unittest.main()

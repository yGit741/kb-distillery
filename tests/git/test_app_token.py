"""kb_distillery.git.app_token: JWT signing with a throwaway key, cached token, GH_TOKEN injection, fallback."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import jwt

from kb_distillery.git import app_token, events, ship

TOKEN = "ghs_FAKEtoken1234567890"
FAKE_GH = """#!/bin/bash
echo "GH_TOKEN=${GH_TOKEN:-unset} $*" >> "$FAKE_GH_DIR/calls.log"
echo '{"number": 7, "title": "t", "url": "u", "state": "OPEN", "labels": []}'
"""


class OwnerLoginTest(unittest.TestCase):
    def test_owner_login_needs_config_and_env_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "app.toml")
            with open(p, "w") as f:
                f.write('app_id = 1\ninstallation_id = 2\nowner_login = "yGit741"\n')
            with patch.dict(os.environ, {"KB_APP_CONFIG": p}):
                os.environ.pop("KB_OWNER_LOGIN", None)
                self.assertEqual(app_token.owner_login(), "yGit741")
                with patch.dict(os.environ, {"KB_OWNER_LOGIN": "other"}):
                    self.assertEqual(app_token.owner_login(), "yGit741")   # the toml wins
            with open(p, "w") as f:
                f.write('app_id = 1\ninstallation_id = 2\n')
            with patch.dict(os.environ, {"KB_APP_CONFIG": p, "KB_OWNER_LOGIN": "other"}):
                self.assertEqual(app_token.owner_login(), "other")
            with patch.dict(os.environ, {"KB_APP_CONFIG": os.path.join(d, "missing.toml"), "KB_OWNER_LOGIN": "x"}):
                self.assertIsNone(app_token.owner_login())


class AppTokenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.dir = self.tmp.name
        self.key = os.path.join(d, "key.pem")
        subprocess.run(["openssl", "genrsa", "-out", self.key, "2048"], check=True, capture_output=True)
        pub = subprocess.run(["openssl", "rsa", "-in", self.key, "-pubout"], check=True, capture_output=True)
        self.pub = pub.stdout
        self.cfg = os.path.join(d, "app.toml")
        with open(self.cfg, "w") as f:
            f.write('app_id = 42\ninstallation_id = 99\nslug = "thesis-knowledge-base"\n')
        gh = os.path.join(d, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.root = os.path.join(d, "root")
        os.makedirs(self.root)
        self.env = patch.dict(os.environ, {"KB_APP_CONFIG": self.cfg, "GH_BIN": gh, "FAKE_GH_DIR": d})
        self.env.start()
        self.posts = []

        def fake_post(url, headers):
            self.posts.append((url, headers))
            exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
            return {"token": TOKEN, "expires_at": exp, "permissions": {"contents": "write"}}
        self.http = patch.object(app_token, "_http_post", fake_post)
        self.http.start()
        app_token._warned = app_token._failed = False
        self.origin = patch.object(app_token, "_https_origin", lambda root: True)
        self.origin.start()
        self.addCleanup(self.origin.stop)

    def tearDown(self):
        self.http.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_jwt_is_rs256_signed_for_app(self):
        claims = jwt.decode(app_token._jwt(app_token.load_config()), self.pub, algorithms=["RS256"])
        self.assertEqual(claims["iss"], "42")
        self.assertLessEqual(claims["exp"] - claims["iat"], 600)

    def test_mint_posts_installation_and_caches_600(self):
        self.assertEqual(app_token.token(self.root), TOKEN)
        url, headers = self.posts[0]
        self.assertTrue(url.endswith("/app/installations/99/access_tokens"))
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        cache = os.path.join(self.root, ".cache", "gh-app-token.json")
        self.assertEqual(os.stat(cache).st_mode & 0o777, 0o600)
        app_token.token(self.root)
        self.assertEqual(len(self.posts), 1)   # cached

    def test_refresh_near_expiry(self):
        app_token.token(self.root)
        cache = os.path.join(self.root, ".cache", "gh-app-token.json")
        data = json.load(open(cache))
        data["expires_epoch"] = time.time() + 120   # inside the 5 min margin
        json.dump(data, open(cache, "w"))
        app_token.token(self.root)
        self.assertEqual(len(self.posts), 2)

    def test_gh_helpers_inject_token(self):
        ship.gh(["pr", "view"], self.root)
        events._gh(["pr", "comment", "1"], self.root)
        log = open(os.path.join(self.dir, "calls.log")).read().splitlines()
        self.assertEqual(len(log), 2)
        self.assertTrue(all(l.startswith(f"GH_TOKEN={TOKEN} ") for l in log))

    def test_whoami_bot_without_token_in_output(self):
        out = io.StringIO()
        with patch.object(ship, "ROOT", self.root), contextlib.redirect_stdout(out):
            self.assertEqual(ship.main(["whoami"]), 0)
        self.assertIn("thesis-knowledge-base[bot]", out.getvalue())
        self.assertNotIn(TOKEN, out.getvalue())

    def test_push_spec_keeps_token_in_env_only(self):
        prefix, env = app_token.git_push_cmd(self.root)
        self.assertEqual(prefix, ["git", "-c", "credential.helper="])
        self.assertEqual(env["KB_GIT_TOKEN"], TOKEN)
        self.assertNotIn(TOKEN, open(env["GIT_ASKPASS"]).read())

    def test_missing_config_falls_back(self):
        err = io.StringIO()
        with patch.dict(os.environ, {"KB_APP_CONFIG": os.path.join(self.dir, "none.toml")}), \
                contextlib.redirect_stderr(err):
            self.assertIsNone(app_token.token(self.root))
            self.assertNotIn("GH_TOKEN", {k: v for k, v in app_token.gh_env(self.root, base={}).items()})
            self.assertTrue(app_token.whoami(self.root).startswith("user fallback"))
            self.assertIsNone(app_token.git_push_cmd(self.root))
        self.assertEqual(err.getvalue().count("warning:"), 1)

    def test_mint_failure_falls_back(self):
        def boom(url, headers):
            raise OSError("network down")
        with patch.object(app_token, "_http_post", boom), contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(app_token.token(self.root))


if __name__ == "__main__":
    unittest.main()

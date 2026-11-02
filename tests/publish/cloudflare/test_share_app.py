#!/usr/bin/env python3
"""Tests for the app layout of the share build (`kb_distillery.publish.site.build`, the only layout).

The data path is collect_data / collect_lifecycle / apply_profile, so these tests check the shape of the baked
blob, that the public privacy cuts hold, that `share audit` is clean on the output, the size guard, determinism, and
the Worker config. The frontend is a stub dist (a template index.html + assets/) so nothing here needs node; one test
runs the real `vite build --mode share` when web/node_modules exists. Offline; fixture vault only.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb_distillery.config.paths import vault_root
ROOT = vault_root()

from kb_distillery.publish.site import build as sb
from kb_distillery.publish.cloudflare import deploy
from kb_distillery.publish.site import snapshots
from kb_distillery.publish.cloudflare.contracts import Manifest
from tests.publish.cloudflare.test_share_build import (PAGES, SECRET_EMAIL, SECRET_RAW, STUB_INDEX, THINK_SECRET, _git, _have_git,
                                          build_from, kb_data, make_repo, make_stub_dist)

# the fixture pages minus the prose that the audit rightly flags (raw/ path in a sentence)
CLEAN_PAGES = {k: v.replace("Mentions `raw/notes/scratch.md` in prose.", "Plain prose.") for k, v in PAGES.items()}


def app_build(repo, out, dist, profile="private", **kw):
    return build_from(repo, out, profile, frontend_dist=dist, **kw)


class _AppFixture(unittest.TestCase):
    pages = PAGES

    @classmethod
    def setUpClass(cls):
        if not _have_git():
            raise unittest.SkipTest("git not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-app-test-")
        cls.repo = make_repo(cls.tmp, pages=cls.pages)
        cls.out = os.path.join(cls.tmp, "out")
        cls.dist = make_stub_dist(cls.tmp)
        cls.private = app_build(cls.repo, cls.out, cls.dist, "private", label="private")
        cls.public = app_build(cls.repo, cls.out, cls.dist, "public", label="public")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def html(result):
        return (result.dir / "index.html").read_text(encoding="utf-8")


class AppLayoutTests(_AppFixture):
    def test_output_tree_and_manifest(self):
        for result in (self.private, self.public):
            files = sb.tree_files(result.dir)
            self.assertEqual(files, ["assets/index-abc123.css", "assets/index-abc123.js", "index.html", "manifest.json"])
            m = result.manifest
            self.assertEqual(m.layout, "app")
            self.assertEqual(m.sha256, sb.tree_digest(result.dir))
            on_disk = json.loads((result.dir / "manifest.json").read_text())
            self.assertEqual(on_disk["layout"], "app")
            self.assertEqual(Manifest.from_json((result.dir / "manifest.json").read_text()), m)
        self.assertEqual(self.private.manifest.profile, "private")
        self.assertEqual(self.public.manifest.profile, "public")

    def test_an_old_manifest_without_a_layout_still_reads_as_legacy(self):
        """Snapshots published before the switch have no `layout`; listing and rollback must keep reading them."""
        text = (self.public.dir / "manifest.json").read_text()
        old = {k: v for k, v in json.loads(text).items() if k != "layout"}
        self.assertEqual(Manifest.from_json(json.dumps(old)).layout, "legacy")

    def test_page_is_the_template_with_the_blob_baked_in(self):
        html = self.html(self.public)
        self.assertIn('<script type="module" crossorigin src="/assets/index-abc123.js"></script>', html)
        self.assertIn("<title>Thesis Wiki — kb 0.1.1</title>", html)
        self.assertEqual(html.count('id="kb-data"'), 1)
        self.assertLess(html.index('id="kb-data"'), html.index("</head>"))
        meta = kb_data(html)["meta"]
        self.assertEqual(meta["kb_version"], "0.1.1")
        self.assertEqual(meta["profile"], "public")
        self.assertEqual(meta["content_sha"], self.public.manifest.content_sha)

    def test_public_blob_has_exactly_these_keys(self):
        app = kb_data(self.html(self.public))
        self.assertEqual(set(app), {"graph", "index", "pages", "meta", "home", "rawCards"})   # rawCards: Home pipeline (raw_card.public_card)

    def test_public_privacy(self):
        html = self.html(self.public)
        for secret in (THINK_SECRET, SECRET_RAW, SECRET_EMAIL, "original_name", "Old Name.md", "GAMMA-ONLY-TOKEN",
                       "distilled-think", "lifecycle", "digestion"):
            self.assertNotIn(secret, html)
        data = kb_data(html)
        self.assertEqual({n["id"] for n in data["graph"]["nodes"]}, {"alpha", "beta", "delta"})
        for n in data["graph"]["nodes"]:
            self.assertNotIn("path", n)
        for p in data["pages"].values():
            self.assertNotIn("path", p)
        self.assertNotIn("/Users/", html)

    def test_private_keeps_its_fields_and_adds_the_lifecycle(self):
        data = kb_data(self.html(self.private))
        self.assertIn("gamma", data["pages"])
        self.assertEqual(data["pages"]["alpha"]["frontmatter"]["email"], SECRET_EMAIL)
        life = data["lifecycle"]
        self.assertEqual(life["generated_at"], "2026-01-02T03:04:05Z")
        self.assertTrue(life["timeline"])
        self.assertEqual(life["version"], "0.1.1")
        for key in ("working", "nightly", "stale_worktrees", "unpushed", "infra_branches"):   # local checkout state never ships
            self.assertNotIn(key, life)
        self.assertNotIn(THINK_SECRET, json.dumps(data))
        self.assertNotIn("digestion", data)

    def test_no_stray_files_from_the_dist(self):
        self.assertFalse((self.public.dir / ".src-hash").exists())

    def test_rebuild_into_the_same_dir_leaves_no_stale_files(self):
        stale = self.public.dir / "assets" / "old-chunk.js"
        stale.write_text("old")
        again = app_build(self.repo, self.out, self.dist, "public", label="public")
        self.assertFalse(stale.exists())
        self.assertEqual(again.manifest.sha256, self.public.manifest.sha256)


class AppDeterminismTests(_AppFixture):
    def test_two_runs_and_a_clone_are_identical(self):
        again = app_build(self.repo, self.out, self.dist, "public", label="again")
        self.assertEqual(again.manifest.sha256, self.public.manifest.sha256)
        self.assertEqual((again.dir / "manifest.json").read_text(), (self.public.dir / "manifest.json").read_text())
        for rel in sb.tree_files(self.public.dir):
            self.assertEqual((again.dir / rel).read_bytes(), (self.public.dir / rel).read_bytes(), rel)
        clone = os.path.join(self.tmp, "clone")
        _git(self.tmp, "clone", "-q", self.repo, clone)
        cloned = app_build(clone, self.out, self.dist, "private", label="clone")
        self.assertEqual(cloned.manifest.sha256, self.private.manifest.sha256)

    def test_dirty_tree_has_no_effect(self):
        (Path(self.repo) / "wiki" / "junk.md").write_text("---\ntype: concept\n---\n\n# Junk\n\nJUNK-TOKEN\n")
        try:
            dirty = app_build(self.repo, self.out, self.dist, "public", label="dirty")
        finally:
            (Path(self.repo) / "wiki" / "junk.md").unlink()
        self.assertEqual(dirty.manifest.sha256, self.public.manifest.sha256)
        self.assertNotIn("JUNK-TOKEN", self.html(dirty))

    def test_a_different_frontend_changes_the_digest(self):
        other = make_stub_dist(self.tmp, "dist2")
        (other / "assets" / "index-abc123.js").write_text("console.log('other');\n")
        changed = app_build(self.repo, self.out, other, "public", label="other")
        self.assertNotEqual(changed.manifest.sha256, self.public.manifest.sha256)


class AppAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_git():
            raise unittest.SkipTest("git not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-app-audit-")
        cls.repo = make_repo(cls.tmp, pages=CLEAN_PAGES)
        cls.dist = make_stub_dist(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_audit_of_the_app_build_is_clean(self):
        report, build_dir, tmp = snapshots.audit_build("main", root=self.repo, viewer_root=ROOT,
                                                       viewer_worktree=True, frontend_dist=self.dist)
        with tmp:
            self.assertEqual(report["flags"], [])
            self.assertEqual(report["pages"], 3)
            self.assertEqual(report["counts"], {"concept": 1, "moc": 1, "paper": 1})
            self.assertEqual(report["manifest"]["layout"], "app")
            self.assertTrue((Path(build_dir) / "assets").is_dir())

    def test_audit_of_the_leaky_fixture_is_clean_after_the_public_cuts(self):
        os.makedirs(os.path.join(self.tmp, "leaky"))
        repo = make_repo(os.path.join(self.tmp, "leaky"), pages=PAGES)
        out = os.path.join(self.tmp, "o")
        app = snapshots.scan(snapshots.extract_data(
            (app_build(repo, out, self.dist, "public", label="a").dir / "index.html").read_text(encoding="utf-8")))
        self.assertEqual(app["flags"], [])       # raw/notes/scratch.md in PAGES prose is no longer sensitive (only raw/emails/)


class AppGuardTests(_AppFixture):
    def test_size_guard_applies_to_index_and_to_every_asset(self):
        with mock.patch.object(sb, "MAX_HTML_BYTES", 600):                   # index.html (data) grows past it
            with self.assertRaisesRegex(sb.BuildError, "index.html is"):
                app_build(self.repo, self.out, self.dist, "public", label="big-index")
        big = make_stub_dist(self.tmp, "dist-big")
        (big / "assets" / "index-abc123.js").write_text("x" * 5000)
        with mock.patch.object(sb, "MAX_HTML_BYTES", 4000), mock.patch.object(sb, "WARN_HTML_BYTES", 3000):
            with self.assertRaisesRegex(sb.BuildError, "assets/index-abc123.js is"):
                app_build(self.repo, self.out, big, "public", label="big-asset")

    def test_size_stays_under_the_cap(self):
        for result in (self.private, self.public):
            for rel in sb.tree_files(result.dir):
                self.assertLess((result.dir / rel).stat().st_size, sb.MAX_HTML_BYTES, rel)

    def test_missing_dist_is_a_clear_error(self):
        with self.assertRaisesRegex(sb.BuildError, "no index.html"):
            app_build(self.repo, self.out, Path(self.tmp) / "nope", "public", label="x")

    def test_template_without_title_is_refused(self):
        bad = make_stub_dist(self.tmp, "dist-bad")
        (bad / "index.html").write_text("<html><body></body></html>")
        with self.assertRaisesRegex(sb.BuildError, "inner build failed"):
            app_build(self.repo, self.out, bad, "public", label="bad")

    def test_a_viewer_without_the_app_flag_is_refused(self):
        with mock.patch.object(sb, "APP_FLAG", "--no-such-flag-in-the-viewer"):
            with self.assertRaisesRegex(sb.BuildError, "predates the app layout"):
                app_build(self.repo, self.out, self.dist, "public", label="old")


class WorkerConfigTests(_AppFixture):
    CFG = {"google_client_id": "id", "allowed_emails": ["a@example.com"], "compatibility_date": "2025-01-01"}

    def test_builds_get_the_spa_fallback(self):
        for result in (self.public, self.private):
            dest = Path(self.tmp) / f"worker-{result.dir.name}"
            deploy.render_worker_dir(result.dir, "snapshot-x", result.manifest.profile == "private", self.CFG, dest)
            conf = (dest / "wrangler.jsonc").read_text()
            self.assertIn("single-page-application", conf)
            self.assertTrue((dest / "public" / "index.html").is_file())

    def test_wrangler_text_without_the_spa_fallback_is_unchanged(self):     # a snapshot published before the switch
        self.assertNotIn("not_found_handling", deploy.render_wrangler("kb", True, self.CFG))
        self.assertNotIn("not_found_handling", deploy.render_wrangler("snapshot-x", False, self.CFG))
        self.assertIn("not_found_handling", deploy.render_wrangler("snapshot-x", False, self.CFG, spa=True))


class FrontendDistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="share-app-fe-"))
        fe = self.tmp / "web"
        (fe / "src" / "test").mkdir(parents=True)
        (fe / "node_modules").mkdir()
        (fe / "src" / "main.tsx").write_text("a")
        (fe / "src" / "a.test.ts").write_text("t")
        (fe / "src" / "test" / "setup.ts").write_text("s")
        (fe / "index.html").write_text("<html></html>")
        self.fe = fe
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def runner(self, cmd, env=None, **kw):
        self.calls.append((cmd, env["VITE_SHARE_PROFILE"]))
        out = self.fe / "dist-share" / env["VITE_SHARE_PROFILE"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(STUB_INDEX)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def test_builds_once_per_source_state_and_profile(self):
        d1 = sb.ensure_frontend_dist("public", self.fe, runner=self.runner)
        sb.ensure_frontend_dist("public", self.fe, runner=self.runner)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(d1, self.fe / "dist-share" / "public")
        sb.ensure_frontend_dist("private", self.fe, runner=self.runner)
        self.assertEqual([c[1] for c in self.calls], ["public", "private"])
        (self.fe / "src" / "main.tsx").write_text("changed")
        sb.ensure_frontend_dist("public", self.fe, runner=self.runner)
        self.assertEqual(len(self.calls), 3)

    def test_tests_do_not_invalidate_the_bundle(self):
        before = sb.frontend_source_hash(self.fe)
        (self.fe / "src" / "a.test.ts").write_text("other")
        (self.fe / "src" / "test" / "setup.ts").write_text("other")
        self.assertEqual(sb.frontend_source_hash(self.fe), before)

    def test_missing_node_modules_and_failed_build(self):
        shutil.rmtree(self.fe / "node_modules")
        with self.assertRaisesRegex(sb.BuildError, "web-install"):
            sb.ensure_frontend_dist("public", self.fe, runner=self.runner)
        (self.fe / "node_modules").mkdir()
        fail = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom")  # noqa: E731
        with self.assertRaisesRegex(sb.BuildError, "boom"):
            sb.ensure_frontend_dist("public", self.fe, runner=fail)


class RealFrontendTests(unittest.TestCase):
    """The real `vite build --mode share` for both profiles, when the frontend deps are installed."""

    @classmethod
    def setUpClass(cls):
        if not _have_git() or not (sb.FRONTEND_DIR / "node_modules").is_dir() or not shutil.which("npm"):
            raise unittest.SkipTest("frontend deps / npm not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-app-real-")
        cls.repo = make_repo(cls.tmp, pages=CLEAN_PAGES)
        cls.out = os.path.join(cls.tmp, "out")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def js(self, result):
        return "\n".join((result.dir / rel).read_text(encoding="utf-8") for rel in sb.tree_files(result.dir)
                         if rel.endswith(".js"))

    def test_both_profiles_build_and_exclude_the_private_screens(self):
        public = build_from(self.repo, self.out, "public", frontend_dist=None, label="public")
        private = build_from(self.repo, self.out, "private", frontend_dist=None, label="private")
        self.assertTrue(re.search(r'src="/assets/index-[^"]+\.js"', self.html(public)))
        pub_js, priv_js = self.js(public), self.js(private)
        for banned in ("Could not load the pipeline", "Add or remove an API key", "Could not load scopes"):
            self.assertNotIn(banned, pub_js)
            self.assertNotIn(banned, priv_js)
        self.assertNotIn("Working tree, sessions and the nightly job", pub_js)     # the lifecycle screen
        self.assertIn("Working tree, sessions and the nightly job", priv_js)
        self.assertNotIn("Could not load the current state.", pub_js)              # the Start screen (screen.start): private only
        self.assertIn("Could not load the current state.", priv_js)
        self.assertNotIn('id="kb-data"', (sb.FRONTEND_DIR / "dist-share" / "public" / "index.html").read_text())

    @staticmethod
    def html(result):
        return (result.dir / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

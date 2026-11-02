#!/usr/bin/env python3
"""Tests for the private site's Lifecycle data and its GitHub link (src/kb_distillery/share/build.py).

Builds the same synthetic vault as test_share_build (private + public) once per class and checks: the private blob
carries the Lifecycle snapshot of the content commit and the public one carries none of it; the snapshot has no local
state or absolute paths; builds are byte-deterministic. The real-repo cases run only when git and the kb-* tags are
available.
"""
import shutil
import tempfile
import unittest

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.share import build as sb
from tests.share.test_share_build import (_Fixture, _git, _have_tags, build_from, kb_data,  # noqa: E402
                                          read_html, sha256)

GITHUB_URL = "https://github.com/acme/vault"
# local checkout state: never in the blob (the build does not read it; this pins that it stays out)
LOCAL_STATE_KEYS = ("working", "nightly", "stale_worktrees", "unpushed", "server", "failures", "recent",
                    "active_ingest", "infra_branches")
ABS_PATH_MARKERS = ("/Users/", "OneDrive", "~/Library", "/var/folders", "/tmp/", "/private/")


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)
    elif isinstance(obj, str):
        yield obj


class LifecycleTests(_Fixture):
    def test_github_url_normaliser(self):
        for remote in ("git@github.com:acme/vault.git", "https://github.com/acme/vault.git",
                       "https://github.com/acme/vault", "ssh://git@github.com/acme/vault.git\n"):
            self.assertEqual(sb.github_url(remote), GITHUB_URL, remote)
        for remote in ("", None, "https://gitlab.com/acme/vault.git", "git@example.com:acme/vault.git"):
            self.assertIsNone(sb.github_url(remote), remote)

    def test_lifecycle_data(self):
        lc = self.data["lifecycle"]
        sha = self.private.manifest.content_sha
        self.assertEqual(lc["generated_at"], "2026-01-02T03:04:05Z")
        self.assertEqual(lc["branch"], "main")
        self.assertEqual(lc["head"], sha[:9])
        self.assertEqual(lc["version"], "0.1.1")
        self.assertIsNone(lc["github"])                              # the fixture repo has no GitHub remote
        from kb_distillery.core.schema import SCHEMA_VERSION
        self.assertEqual(lc["schema"]["version"], f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}")
        self.assertEqual([r["sha"] for r in lc["timeline"]], [sha])
        self.assertEqual(lc["timeline"][0]["op"], "import")
        self.assertEqual(lc["stats"], {"kb_steps": 1, "pr_merges": 0, "ops_30d": {"import": 1}, "undone": 0})
        self.assertEqual(lc["snapshots"], [])
        self.assertEqual(sorted(lc["policy"]), ["mode", "strict"])
        for k in LOCAL_STATE_KEYS:
            self.assertNotIn(k, lc)

    def test_the_github_remote_lands_in_the_lifecycle(self):
        _git(self.repo, "remote", "add", "origin", "git@github.com:acme/vault.git")
        try:
            res = build_from(self.repo, self.out, "private", label="with-remote")
        finally:
            _git(self.repo, "remote", "remove", "origin")
        self.assertEqual(kb_data(read_html(res))["lifecycle"]["github"], GITHUB_URL)
        self.assertNotIn("acme/vault", self.pub_html)                  # public builds never name the repo

    def test_lifecycle_snapshots_are_annotated_tags_on_the_history(self):
        _git(self.repo, "tag", "-a", "kb-0.1.1", "-m", "week 1")
        try:
            res = build_from(self.repo, self.out, "private", label="annotated")
        finally:
            _git(self.repo, "tag", "-d", "kb-0.1.1")
        lc = kb_data(read_html(res))["lifecycle"]
        self.assertEqual([(s["tag"], s["label"]) for s in lc["snapshots"]], [("kb-0.1.1", "week 1")])
        self.assertRegex(lc["snapshots"][0]["date"], r"^\d{4}-\d{2}-\d{2}$")   # the tag's creation date
        self.assertEqual(lc["timeline"][0]["snapshot_tag"], "kb-0.1.1")

    def test_private_data_has_no_local_state_or_paths(self):
        lc = self.data["lifecycle"]
        for s in walk_strings(lc):
            for marker in ABS_PATH_MARKERS:
                self.assertNotIn(marker, s, repr(s))
            self.assertFalse(s.startswith("think/"), repr(s))
            self.assertNotIn("/think/", s, repr(s))
        self.assertNotIn("digestion", self.data)                        # the old Digestion tab's data is gone
        self.assertNotIn(self.repo, self.html)                          # the fixture's own absolute path
        self.assertNotIn(self.tmp, self.html)

    def test_public_has_none_of_it(self):
        self.assertNotIn("lifecycle", self.pub_data)
        self.assertNotIn("digestion", self.pub_data)
        self.assertNotIn('"lifecycle"', self.pub_html)

    def test_deterministic(self):
        again = build_from(self.repo, self.out, "private", label="again-lifecycle")
        self.assertEqual(again.manifest.sha256, self.private.manifest.sha256)
        self.assertEqual(sha256(again.dir / "index.html"), sha256(self.private.dir / "index.html"))


class RealRepoLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_tags():
            raise unittest.SkipTest("real kb-* tags not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-real-lifecycle-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _build(self, ref, label):
        return build_from(ROOT, self.tmp, "private", ref=ref, label=label)

    def test_main_lifecycle_has_data(self):
        res = self._build("main", "main-lifecycle")
        html = read_html(res)
        self.assertLessEqual(len(html.encode("utf-8")), sb.MAX_HTML_BYTES)
        lc = kb_data(html)["lifecycle"]
        self.assertEqual(lc["branch"], "main")
        self.assertEqual(lc["version"], res.manifest.kb_version)
        self.assertEqual(lc["generated_at"], res.manifest.built_at)
        self.assertTrue(lc["timeline"])
        self.assertEqual(lc["timeline"][0]["sha"], res.manifest.content_sha)
        self.assertTrue(lc["snapshots"])
        # the newest annotated snapshot on main is listed (older ones age out of the recent history shown)
        newest = next(line.split()[0] for line in _git(ROOT, "for-each-ref", "--sort=-creatordate", "--merged", "main",
                                                       "--format=%(refname:short) %(objecttype)", "refs/tags/kb-*").stdout.splitlines()
                      if line.split()[1] == "tag")
        self.assertIn(newest, [s["tag"] for s in lc["snapshots"]])
        self.assertTrue(lc["github"].startswith("https://github.com/"))
        for s in walk_strings(lc):
            for marker in ABS_PATH_MARKERS:
                self.assertNotIn(marker, s)
            self.assertFalse(s.startswith("think/"), s)
        for k in LOCAL_STATE_KEYS:
            self.assertNotIn(k, lc)
        self.assertNotIn(ROOT, html)

    def test_old_tag_builds_twice_identically(self):
        a = self._build("kb-0.9.6", "tag-a")
        b = self._build("kb-0.9.6", "tag-b")
        self.assertEqual(a.manifest.sha256, b.manifest.sha256)
        self.assertEqual(sha256(a.dir / "index.html"), sha256(b.dir / "index.html"))
        lc = kb_data(read_html(a))["lifecycle"]
        self.assertEqual(lc["version"], "0.9.6")
        self.assertEqual(lc["timeline"][0]["sha"], a.manifest.content_sha)
        self.assertEqual(lc["generated_at"], a.manifest.built_at)
        self.assertFalse(any(s["tag"] == "kb-0.10.5" for s in lc["snapshots"]))   # later history is not there


if __name__ == "__main__":
    unittest.main()

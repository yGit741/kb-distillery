"""The share build is the React app only: a snapshot of the fixture kb, built from a committed ref, keeps its file list and
its `kb-data` payload byte for byte (tests/fixtures/golden/share-app/{private,public}.json), and a missing share config
refuses to build.

It lives here, not in tests/publish/cloudflare, because that folder skips itself outside the monorepo layout. Offline: a stub frontend
dist stands in for `vite build`, so only the Python side of the build is pinned. After an intended change to the data,
regenerate with `KB_UPDATE_GOLDEN=1 pixi run pytest tests/publish/test_share_snapshot_golden.py` and review the diff."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest

from kb_distillery.kbconfig import checkout_root
from kb_distillery.publish.site import build as sb
from kb_distillery.publish.site import home

HERE = Path(__file__).resolve().parent
FIXTURE_KB = HERE.parent / "fixtures" / "kb" / "kb-fixture"
GOLDEN_DIR = HERE.parent / "fixtures" / "golden" / "share-app"
DATA_RE = re.compile(r'<script type="application/json" id="kb-data">(.*?)</script>', re.S)
DATE = "2026-01-02T03:04:05+00:00"

STUB_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Thesis KB</title>
    <script type="module" crossorigin src="/assets/index-abc123.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-abc123.css">
  </head>
  <body><div id="root"></div></body>
</html>
"""


def _git(root, *args, env=None):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, env=env)


def copy_tracked(src, dest):
    """The tracked files of the fixture kb only (`git ls-files`), so a stray .DS_Store or cache on this machine cannot
    change the commit sha; a source tree without git history is copied whole."""
    cp = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=src, capture_output=True, text=True, check=False)
    names = [n for n in cp.stdout.split("\0") if n] if cp.returncode == 0 else []
    if not names:
        shutil.copytree(src, dest)
        return
    for name in names:
        target = os.path.join(dest, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(src, name), target)


def make_repo(base):
    """A git repo holding the fixture kb in one `kb(import)` commit with fixed dates, so the sha is stable."""
    root = os.path.join(base, "repo")
    copy_tracked(FIXTURE_KB, root)
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    _git(root, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE=DATE, GIT_COMMITTER_DATE=DATE)
    _git(root, "commit", "-q", "-m", "kb(import): fixture (kb-0.1.1)\n\nKB-Version: 0.1.1\nKB-Op: import", env=env)
    return root


def make_stub_dist(base):
    dist = Path(base) / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(STUB_INDEX, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log('app');\n", encoding="utf-8")
    (dist / "assets" / "index-abc123.css").write_text("body{margin:0}\n", encoding="utf-8")
    (dist / ".src-hash").write_text("x\n", encoding="utf-8")        # a stamp must never ship
    return dist


def stable(payload):
    """The `kb-data` blob minus what depends on the checkout running the test, not on the fixture or the build:
    the viewer sha (HEAD of this checkout), the schema version and git policy constants, and the Home tour and
    cards (the owner's share.toml)."""
    data = json.loads(json.dumps(payload))
    data["meta"]["viewer_sha"] = "<viewer>"
    if "home" in data:
        data["home"]["tour"] = "<tour>"
        data["home"]["cards"] = "<cards>"
    if "lifecycle" in data:
        data["lifecycle"]["schema"] = "<schema>"
        data["lifecycle"]["policy"] = "<policy>"
    return data


def golden_path(profile):
    return GOLDEN_DIR / f"{profile}.json"


class SnapshotGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("git") is None:
            raise unittest.SkipTest("git not available")
        root = checkout_root()
        if root is None or not (Path(root) / "src" / "kb_distillery" / "publish" / "site" / "build.py").is_file():
            raise unittest.SkipTest("not a source checkout: the share build renders with this checkout's code")
        cls.viewer = root
        cls.tmp = tempfile.mkdtemp(prefix="share-golden-")
        cls.repo = make_repo(cls.tmp)
        cls.dist = make_stub_dist(cls.tmp)
        cls.results = {p: sb.build("main", profile=p, root=cls.repo, viewer_root=cls.viewer, viewer_worktree=True,
                                   out_root=os.path.join(cls.tmp, "out"), label=p, frontend_dist=cls.dist)
                       for p in ("private", "public")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def snapshot_of(self, profile):
        result = self.results[profile]
        html = (result.dir / "index.html").read_text(encoding="utf-8")
        m = result.manifest
        return {"files": sb.tree_files(result.dir),
                "manifest": {"layout": m.layout, "profile": m.profile, "kb_version": m.kb_version,
                             "content_ref": m.content_ref, "built_at": m.built_at},
                "kb_data": stable(json.loads(DATA_RE.search(html).group(1)))}

    def check(self, profile):
        got = self.snapshot_of(profile)
        path = golden_path(profile)
        if os.environ.get("KB_UPDATE_GOLDEN") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertTrue(path.is_file(), f"no golden {path}: run with KB_UPDATE_GOLDEN=1")
        want = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(got["files"], want["files"])
        self.assertEqual(got["manifest"], want["manifest"])
        self.assertEqual(sorted(got["kb_data"]), sorted(want["kb_data"]))
        for key in want["kb_data"]:
            self.assertEqual(got["kb_data"][key], want["kb_data"][key], f"kb-data[{key!r}] differs from the golden")

    def test_private_snapshot_matches_the_golden(self):
        self.check("private")

    def test_public_snapshot_matches_the_golden(self):
        self.check("public")

    def test_the_output_is_the_react_app_layout(self):
        for result in self.results.values():
            self.assertEqual(result.manifest.layout, "app")
            self.assertEqual(result.manifest.sha256, sb.tree_digest(result.dir))
            html = (result.dir / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<iframe", html)
            self.assertNotIn("srcdoc", html)
            self.assertNotIn("kb-doc-", html)

    def test_only_the_private_snapshot_carries_the_lifecycle(self):
        private = json.loads(DATA_RE.search((self.results["private"].dir / "index.html").read_text(encoding="utf-8")).group(1))
        public = json.loads(DATA_RE.search((self.results["public"].dir / "index.html").read_text(encoding="utf-8")).group(1))
        self.assertIn("lifecycle", private)
        self.assertNotIn("lifecycle", public)


class ShareConfigRequired(unittest.TestCase):
    """The build reads the Home tour from share.toml; without that file it stops instead of publishing a site
    that silently lost its Home."""

    def args(self, tmp):
        return SimpleNamespace(out=os.path.join(tmp, "o.html"), profile="public", content_ref="main", content_sha="a" * 40,
                               kb_version="0.1.1", viewer_sha="b" * 40, built_at=DATE, scope=None, hops="1",
                               predicate=None, view=None, stats=None, app_index=os.path.join(tmp, "missing-index.html"))

    def test_a_missing_share_config_refuses_to_build(self):
        with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
            missing = Path(tmp) / "share.toml"
            mp.setattr(home, "CONFIG_PATH", missing)
            with self.assertRaises(sb.BuildError) as cm:
                sb.inner_build_app(self.args(tmp))
            self.assertIn("share config", str(cm.exception))
            self.assertIn(str(missing), str(cm.exception))
            self.assertFalse(Path(self.args(tmp).out).exists())

    def test_a_broken_share_config_refuses_to_build(self):
        with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
            bad = Path(tmp) / "share.toml"
            bad.write_text("[home\ntour = ", encoding="utf-8")
            mp.setattr(home, "CONFIG_PATH", bad)
            with self.assertRaises(sb.BuildError) as cm:
                sb.inner_build_app(self.args(tmp))
            self.assertIn("share config", str(cm.exception))

    def test_load_home_stays_lenient_unless_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "share.toml"
            self.assertEqual(home.load_home(missing), {"cards": [], "tour": None})
            with self.assertRaises(home.ShareConfigError):
                home.load_home(missing, strict=True)

    def test_the_shipped_share_config_loads_strictly(self):
        self.assertIsInstance(home.load_home(strict=True)["cards"], list)


if __name__ == "__main__":
    unittest.main()

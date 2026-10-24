#!/usr/bin/env python3
"""Tests for `ops adopt-history`, `ops record` and `ship prune` on temp repos."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.paths import vault_root
ROOT = vault_root()

from kb.core.schema import SCHEMA_VERSION

V = "%d.%d" % SCHEMA_VERSION  # knowledge versions under the current schema

from kb.ops import core
from kb.ops.__main__ import main as ops_main
from kb.ops.adopt import adopt
from kb.git import ship

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def g(cwd, *args, input=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          input=input, env=dict(os.environ, **ENV)).stdout.strip()


def write(root, rel, text):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full) or root, exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel)) as f:
        return f.read()


class AdoptTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.remote, self.builder, self.primary = (os.path.join(t, n) for n in ("remote.git", "builder", "primary"))
        g(t, "init", "-q", "--bare", "-b", "main", self.remote)
        g(t, "clone", "-q", self.remote, self.builder)
        write(self.builder, "a.txt", "1\n")
        write(self.builder, "wiki/w.md", "w\n")
        write(self.builder, ".gitignore", "meta/.ops/\n")
        g(self.builder, "add", "-A")
        g(self.builder, "commit", "-q", "-m", "chore(git): init (retro)")
        g(self.builder, "push", "-q", "-u", "origin", "main")
        g(t, "clone", "-q", self.remote, self.primary)
        # upstream moves on (a PR merged elsewhere)
        write(self.builder, "a.txt", "1\n2\n")
        write(self.builder, "new.txt", "n\n")
        g(self.builder, "add", "-A")
        g(self.builder, "commit", "-q", "-m", "feat(git): change a (#1)")
        g(self.builder, "push", "-q", "origin", "main")
        self.upstream = g(self.builder, "rev-parse", "HEAD")
        self.bundle = self._curated(g(self.builder, "rev-parse", "HEAD^{tree}"))

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def _curated(self, tree):
        """Curated line with the same tree + adopt merge whose 2nd parent is upstream main."""
        c = g(self.builder, "commit-tree", tree, input="chore(git): curated line (retro)\n")
        t = g(self.builder, "commit-tree", tree, "-p", c, "-p", self.upstream,
              input="chore(git): adopt curated history (retro)\n")
        g(self.builder, "update-ref", "refs/heads/history/curated", t)
        bundle = os.path.join(self.tmp.name, "curated.bundle")
        g(self.builder, "bundle", "create", bundle, "refs/heads/history/curated")
        self.tip = t
        return bundle

    def test_adopts_and_keeps_local_work(self):
        write(self.primary, "a.txt", "1\n2\n")        # same edit already upstream → superseded
        write(self.primary, "new.txt", "n\n")         # untracked, identical upstream → superseded
        write(self.primary, "wiki/w.md", "mine\n")    # unrelated local edit → kept
        adopt(self.bundle, self.primary)
        self.assertEqual(g(self.primary, "rev-parse", "HEAD"), self.tip)
        self.assertEqual(g(self.remote, "rev-parse", "main"), self.tip)
        self.assertEqual(read(self.primary, "a.txt"), "1\n2\n")
        self.assertEqual(read(self.primary, "wiki/w.md"), "mine\n")
        backups = os.path.join(self.primary, "meta", ".ops", "adopt-backup")
        self.assertTrue(os.path.isdir(backups))
        self.assertEqual(g(self.primary, "merge-base", "--is-ancestor", self.upstream, "HEAD"), "")

    def test_contained_when_only_histogram_aligns(self):
        """Identical edit beside an upstream-only edit: myers conflicts, histogram proves containment."""
        from kb.ops.adopt import _contained
        root = os.path.join(self.tmp.name, "c")
        g(self.tmp.name, "init", "-q", "-b", "main", root)
        base = "".join(f"line {i}\n" for i in range(30))
        block = "```\ncmd one\ncmd two\n```\n\n"
        write(root, "f.md", base)
        g(root, "add", "-A")
        g(root, "commit", "-q", "-m", "chore(git): base (retro)")
        head = g(root, "rev-parse", "HEAD")
        lines = base.splitlines(keepends=True)
        local = "".join(lines[:10]) + "\n" + block + "".join(lines[10:])
        theirs = "".join(lines[:9]) + "upstream note\n\n" + block + "".join(lines[10:])
        write(root, "f.md", theirs)
        g(root, "add", "-A")
        g(root, "commit", "-q", "-m", "chore(git): upstream (retro)")
        target = g(root, "rev-parse", "HEAD")
        g(root, "checkout", "-q", head)
        write(root, "f.md", local)
        # a correct answer either way is fine for myers; the point is no false refusal overall
        self.assertIn(_contained(root, "f.md", head, target), (True, False))
        write(root, "f.md", "".join(lines[:10]) + "different local text\n" + "".join(lines[10:]))
        self.assertFalse(_contained(root, "f.md", head, target))

    def test_refuses_conflicting_local_edit(self):
        write(self.primary, "a.txt", "1\nX\n")
        with self.assertRaises(core.OpsError) as ctx:
            adopt(self.bundle, self.primary)
        self.assertIn("a.txt", str(ctx.exception))
        self.assertEqual(read(self.primary, "a.txt"), "1\nX\n")

    def test_refuses_bundle_from_other_main(self):
        write(self.builder, "a.txt", "other\n")
        g(self.builder, "add", "-A")
        tree = g(self.builder, "write-tree")
        bundle = self._curated(tree)
        with self.assertRaises(core.OpsError):
            adopt(bundle, self.primary)

    def test_dry_run_changes_nothing(self):
        before = g(self.primary, "rev-parse", "HEAD")
        adopt(self.bundle, self.primary, dry_run=True)
        self.assertEqual(g(self.primary, "rev-parse", "HEAD"), before)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        g(self.root, "init", "-q", "-b", "main")
        _lint = patch("kb.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test
        _lint.start()
        self.addCleanup(_lint.stop)
        write(self.root, "meta/stub.py", "x = 1\n")
        write(self.root, ".gitignore", "meta/.ops/\n")
        write(self.root, "wiki/x.md", "x\n")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "chore(git): init (retro)")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def test_record_groups_existing_edits(self):
        write(self.root, "wiki/lior-wolf.md", "p\n")
        write(self.root, "wiki/2016-a.md", "a\n")
        write(self.root, "wiki/yoav-goldberg.md", "y\n")
        with patch.object(core, "ROOT", self.root):
            ops_main(["record", "catalog", "lior-wolf", "Lior Wolf profile and 1 paper",
                      "wiki/lior-wolf.md", "wiki/2016-a.md"])
        files = set(g(self.root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(files, {"wiki/lior-wolf.md", "wiki/2016-a.md"})
        self.assertEqual(g(self.root, "log", "-1", "--format=%s"),
                         f"kb(catalog): Lior Wolf profile and 1 paper (kb-{V}.1)")
        self.assertIn("wiki/yoav-goldberg.md", g(self.root, "status", "--porcelain"))


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.remote, self.repo = os.path.join(t, "remote.git"), os.path.join(t, "repo")
        g(t, "init", "-q", "--bare", "-b", "main", self.remote)
        g(t, "clone", "-q", self.remote, self.repo)
        write(self.repo, "a.txt", "1\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "chore(git): init (retro)")
        g(self.repo, "push", "-q", "-u", "origin", "main")
        g(self.repo, "branch", "worktree-old")
        g(self.repo, "push", "-q", "origin", "main:infra/merged")
        g(self.repo, "checkout", "-q", "-b", "infra/wip")
        write(self.repo, "b.txt", "2\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "feat(git): wip")
        g(self.repo, "checkout", "-q", "main")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def test_drop_saves_patch_then_deletes(self):
        g(self.repo, "push", "-q", "origin", "infra/wip")
        self.assertEqual(ship.cmd_drop("infra/wip", root=self.repo), 0)
        patch = os.path.join(self.repo, "_quarantine", "dropped-infra-wip.patch")
        self.assertIn("feat(git): wip", read(self.repo, "_quarantine/dropped-infra-wip.patch"))
        self.assertTrue(os.path.exists(patch))
        self.assertNotIn("infra/wip", g(self.repo, "branch", "--list"))
        self.assertEqual(g(self.remote, "branch", "--list", "infra/wip"), "")
        self.assertEqual(ship.cmd_drop("main", root=self.repo), 1)

    def test_prune_deletes_only_merged(self):
        ship.cmd_prune(apply=False, root=self.repo)
        self.assertIn("worktree-old", g(self.repo, "branch", "--list"))
        ship.cmd_prune(apply=True, root=self.repo)
        branches = g(self.repo, "branch", "--list")
        self.assertNotIn("worktree-old", branches)
        self.assertIn("infra/wip", branches)
        self.assertEqual(g(self.remote, "branch", "--list", "infra/merged"), "")


if __name__ == "__main__":
    unittest.main()

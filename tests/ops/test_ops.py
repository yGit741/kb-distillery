#!/usr/bin/env python3
"""Tests for src/kb_distillery/ops — one commit per knowledge operation, undo, restore, snapshots, sync."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config.paths import vault_root
ROOT = vault_root()

from kb_distillery.vault.schema import SCHEMA_VERSION

V = "%d.%d" % SCHEMA_VERSION  # knowledge versions under the current schema

from kb_distillery.ops import core, wrap
from kb_distillery.git import commit_policy as cp

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "KB_NO_HYGIENE": "1"}  # sync tests: no hygiene run / email against the temp repo


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


class OpsRepo(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.remote = os.path.join(self.tmp.name, "remote.git")
        self.root = os.path.join(self.tmp.name, "kb")
        g(self.tmp.name, "init", "-q", "--bare", "-b", "main", self.remote)
        g(self.tmp.name, "clone", "-q", self.remote, self.root)
        g(self.root, "config", "user.name", "t")
        g(self.root, "config", "user.email", "t@t")
        _lint = patch("kb_distillery.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test
        _lint.start()
        self.addCleanup(_lint.stop)
        self.write("meta/stub.py", "x = 1\n", mode="w")
        self.write("wiki/log.md", "# Log\n", mode="w")
        self.write(".gitignore", "meta/.ops/\nmeta/.ingest/\n*.pdf\n", mode="w")
        for rel in ("wiki/b.md", "raw/papers/x.md", "think/t.md", "wiki/index.md"):
            self.write(rel, "v1")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "chore: init (retro)")
        g(self.root, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def write(self, rel, text, mode="a"):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, mode) as f:
            f.write(text + ("" if text.endswith("\n") else "\n"))

    def read(self, rel):
        with open(os.path.join(self.root, rel)) as f:
            return f.read()

    def files(self, rev="HEAD"):
        return set(filter(None, g(self.root, "show", "--name-only", "--format=", rev).split("\n")))

    def subject(self, rev="HEAD"):
        return g(self.root, "log", "-1", "--format=%s", rev)

    def body(self, rev="HEAD"):
        return g(self.root, "log", "-1", "--format=%B", rev)

    def op(self, op, target, rels, **kw):
        for rel in rels:
            self.write(rel, f"{op} {target}")
        return core.commit_op(op, target, paths=list(rels), root=self.root, **kw)

    def local_op(self, op, target, rels, **kw):
        """A knowledge step that stays local (as if offline) — for divergence scenarios."""
        return self.op(op, target, rels, push=False, **kw)


class PushTests(OpsRepo):
    def test_each_op_pushes_main(self):
        self.op("digest", "a", ["wiki/a.md"])
        self.assertEqual(g(self.remote, "rev-parse", "main"), g(self.root, "rev-parse", "main"))

    def test_no_push_env_and_flag_keep_it_local(self):
        with patch.dict(os.environ, {"KB_NO_PUSH": "1"}):
            self.op("digest", "a", ["wiki/a.md"])
        self.assertNotEqual(g(self.remote, "rev-parse", "main"), g(self.root, "rev-parse", "main"))
        self.local_op("digest", "b", ["wiki/b.md"])
        self.assertEqual(g(self.root, "rev-list", "--count", "origin/main..main"), "2")

    def test_failed_push_is_only_a_note(self):
        g(self.root, "remote", "set-url", "origin", os.path.join(self.tmp.name, "nowhere.git"))
        sha = self.op("digest", "a", ["wiki/a.md"])
        self.assertEqual(g(self.root, "rev-parse", "HEAD"), sha)   # committed regardless

    def test_nightly_status_reports_missing_install(self):
        with patch.object(core, "NIGHTLY_PLIST", os.path.join(self.tmp.name, "none.plist")), \
                patch.object(core, "NIGHTLY_LOG", os.path.join(self.tmp.name, "none.log")):
            st = core.nightly_status(self.root)
        self.assertFalse(st["installed"])
        self.assertEqual(st["summary"], "NOT INSTALLED")
        self.assertEqual(st["hint"], "pixi run install-sync")


class CommitOpTests(OpsRepo):
    def test_commits_only_its_paths_with_version(self):
        self.write("wiki/other.md", "unrelated dirt")
        sha = self.op("digest", "a", ["wiki/a.md"])
        self.assertTrue(sha)
        self.assertEqual(self.subject(), f"kb(digest): a (kb-{V}.1)")
        self.assertEqual(self.files(), {"wiki/a.md", "wiki/log.md"})
        c = cp.parse_message(self.body())
        self.assertEqual((c.trailers["KB-Op"], c.trailers["KB-Target"], c.trailers["KB-Version"]),
                         ("digest", "a", f"{V}.1"))
        self.op("catalog", "c", ["wiki/c.md"])
        self.assertEqual(self.subject(), f"kb(catalog): c (kb-{V}.2)")
        self.assertIn("wiki/other.md", g(self.root, "status", "--porcelain"))

    def test_generated_and_log_ride_along(self):
        self.write("wiki/index.md", "regenerated")
        self.write("wiki/log.md", "\n## 2026-10-22\n\n### ingest | a\n")
        self.op("digest", "a", ["wiki/a.md"])
        self.assertEqual(self.files(), {"wiki/a.md", "wiki/index.md", "wiki/log.md"})

    def test_think_edits_get_their_own_commit(self):
        self.write("think/t.md", "my thought")
        self.op("refine", "b", ["wiki/b.md", "think/t.md"])
        self.assertEqual(self.files("HEAD"), {"wiki/b.md", "wiki/log.md"})
        self.assertEqual(self.files("HEAD~1"), {"think/t.md", "wiki/log.md"})
        self.assertTrue(self.subject("HEAD~1").startswith("kb(think): human edits (1 file)"))
        self.assertIn("KB-Actor: human", self.body("HEAD~1"))

    def test_other_open_session_files_excluded(self):
        sess = os.path.join(self.root, "meta", ".ingest", "abc")
        os.makedirs(sess)
        with open(os.path.join(sess, "session.json"), "w") as f:
            json.dump({"status": "open", "sha1": "abc", "new_files": ["wiki/locked.md"]}, f)
        self.op("digest", "mine", ["wiki/mine.md", "wiki/locked.md"])
        self.assertEqual(self.files(), {"wiki/mine.md", "wiki/log.md"})

    def test_refuses_off_main(self):
        g(self.root, "checkout", "-q", "-b", "infra/x")
        with self.assertRaises(core.OpsError):
            self.op("digest", "a", ["wiki/a.md"])

    def test_nothing_changed_returns_none(self):
        self.assertIsNone(core.commit_op("refine", "x", paths=[], root=self.root))


class LogLineTests(OpsRepo):
    """Every kb(<op>) commit carries its own wiki/log.md entry, in the same commit."""

    def line(self, op, text):
        return f"### {op} | {text}"

    def test_each_op_logs_inside_its_commit(self):
        for op in ("import", "catalog", "digest", "refine", "distill"):
            sha = self.op(op, f"t-{op}", [f"wiki/{op}.md"])
            self.assertIn("wiki/log.md", self.files(sha), op)
            self.assertIn(self.line(op, f"t {op} ← `t-{op}`"), g(self.root, "show", f"{sha}:wiki/log.md"))
        self.assertEqual(g(self.root, "status", "--porcelain"), "")

    def test_session_commit_logs_with_summary(self):
        core.begin("refine", "b", root=self.root)
        self.write("wiki/b.md", "edited")
        core.commit("split the idea", root=self.root)
        self.assertIn(self.line("refine", "split the idea ← `b`"), self.read("wiki/log.md"))

    def test_writer_that_already_logged_is_not_duplicated(self):
        self.write("wiki/log.md", "\n## 2026-10-22\n\n### ingest | a ← `raw/x`\n")
        self.op("digest", "a", ["wiki/a.md"])
        self.assertEqual(self.read("wiki/log.md").count("\n## "), 1)

    def test_nothing_to_commit_logs_nothing(self):
        self.assertIsNone(core.commit_op("refine", "x", paths=[], root=self.root))
        self.assertEqual(self.read("wiki/log.md"), "# Log\n")

    def test_think_edits_log_in_their_own_commit(self):
        self.write("think/t.md", "my thought")
        core.sync_human(self.root)
        self.assertEqual(self.files(), {"think/t.md", "wiki/log.md"})
        self.assertIn(self.line("think", "human edits (1 file) ← `think`"), self.read("wiki/log.md"))

    def test_undo_and_restore_log_once_in_their_commit(self):
        bad = self.op("refine", "split", ["wiki/new.md"])
        core.undo(bad, root=self.root)
        self.assertIn("wiki/log.md", self.files())
        self.assertEqual(self.read("wiki/log.md").count("### undo | "), 1)
        core.snapshot(root=self.root)
        self.op("refine", "later", ["wiki/later.md"])
        core.restore(f"kb-{V}.2", root=self.root)
        self.assertIn("wiki/log.md", self.files())
        self.assertEqual(self.read("wiki/log.md").count("### restore | "), 1)


class SessionTests(OpsRepo):
    def test_begin_commit_excludes_preexisting_dirt(self):
        self.write("wiki/pre.md", "before begin")
        core.begin("refine", "split-x", "split concept x", root=self.root)
        self.write("wiki/x1.md", "half one")
        self.write("wiki/b.md", "edited")
        core.commit(root=self.root)
        self.assertEqual(self.files(), {"wiki/x1.md", "wiki/b.md", "wiki/log.md"})
        self.assertEqual(self.subject(), f"kb(refine): split concept x (kb-{V}.1)")
        self.assertIsNone(core.current_session(self.root))

    def test_second_begin_refused(self):
        core.begin("refine", "a", root=self.root)
        with self.assertRaises(core.OpsError):
            core.begin("refine", "b", root=self.root)

    def test_abort_keeps_files(self):
        core.begin("refine", "a", root=self.root)
        self.write("wiki/a.md", "x")
        self.assertEqual(core.abort(root=self.root), ["wiki/a.md"])
        self.assertTrue(os.path.exists(os.path.join(self.root, "wiki/a.md")))


class UndoTests(OpsRepo):
    def test_undo_restores_wiki_only(self):
        self.op("refine", "warmup", ["wiki/w.md"])
        self.write("wiki/b.md", "bad split")
        self.write("raw/papers/x.md", "raw touched")
        bad = self.op("refine", "split", ["wiki/new.md", "wiki/b.md", "raw/papers/x.md"])
        raw_after = self.read("raw/papers/x.md")
        core.undo(bad, root=self.root)
        self.assertTrue(self.subject().startswith(f"kb(undo): revert {V}.2 split"))
        self.assertIn(f"KB-Reverts: {bad}", self.body())
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki/new.md")))
        self.assertEqual(self.read("wiki/b.md"), "v1\n")
        self.assertEqual(self.read("raw/papers/x.md"), raw_after)  # raw/ never rewritten
        self.assertIn("undo | kb(refine): split", self.read("wiki/log.md"))
        self.assertNotIn("raw/papers/x.md", self.files())

    def test_undo_and_restore_never_rewrite_the_index_or_the_log(self):
        """wiki/index.md (generated) and wiki/log.md (append-only) sit inside wiki/ but are not restorable."""
        self.op("refine", "warmup", ["wiki/w.md"])
        core.snapshot(root=self.root)
        self.write("wiki/index.md", "regenerated by lint")
        self.write("wiki/paper/2020/index.md", "regenerated section")
        bad = self.op("refine", "split", ["wiki/new.md"])
        index_after = self.read("wiki/index.md")
        section_after = self.read("wiki/paper/2020/index.md")
        self.assertIn("wiki/index.md", self.files(bad))                      # it rode along in the step
        self.assertIn("wiki/paper/2020/index.md", self.files(bad))           # and so did every section index
        core.undo(bad, root=self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki/new.md")))
        self.assertEqual(self.read("wiki/index.md"), index_after)           # not rolled back
        self.assertEqual(self.read("wiki/paper/2020/index.md"), section_after)
        self.op("refine", "later", ["wiki/later.md"])
        log_before = self.read("wiki/log.md")
        core.restore(f"kb-{V}.1", root=self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki/later.md")))
        self.assertEqual(self.read("wiki/index.md"), index_after)
        for line in log_before.splitlines():                                  # restore only ever adds an entry
            self.assertIn(line, self.read("wiki/log.md").splitlines())
        self.assertIn("### restore | ", self.read("wiki/log.md"))

    def test_the_commit_names_pages_never_the_reserved_files(self):
        self.write("wiki/index.md", "regenerated")
        self.write("wiki/log.md", "\n## 2026-10-22\n\n### ingest | a\n")
        self.op("digest", "a", ["wiki/a.md", "wiki/index.md", "wiki/log.md"])
        self.assertEqual(core._pages(["wiki/a.md", "wiki/index.md", "wiki/log.md"]), ["a"])
        self.assertEqual(core._target_of(None, ["wiki/index.md", "wiki/log.md", "wiki/a.md"]), "a")
        self.assertNotIn("index", self.subject())

    def test_refusals(self):
        self.write("think/t.md", "mine")
        core.sync_human(root=self.root)
        think_sha = g(self.root, "rev-parse", "HEAD")
        with self.assertRaises(core.OpsError):
            core.undo(think_sha, root=self.root)
        imp = self.op("import", "inbox", ["raw/inbox/a.md"])
        with self.assertRaises(core.OpsError):
            core.undo(imp, root=self.root)
        first = self.op("refine", "a", ["wiki/a.md"])
        self.op("refine", "a2", ["wiki/a.md"])  # later step on the same file
        with self.assertRaises(core.OpsError) as ctx:
            core.undo(first, root=self.root)
        self.assertIn("later steps", str(ctx.exception))

    def test_double_undo_refused(self):
        sha = self.op("refine", "a", ["wiki/a.md"])
        core.undo(sha, root=self.root)
        with self.assertRaises(core.OpsError):
            core.undo(sha, root=self.root)


class SnapshotRestoreTests(OpsRepo):
    def test_snapshot_named_after_version_and_restore(self):
        self.op("digest", "a", ["wiki/a.md"])
        self.assertEqual(core.snapshot("week 43", root=self.root), f"kb-{V}.1")
        self.assertEqual(g(self.root, "cat-file", "-t", f"kb-{V}.1"), "tag")
        self.op("refine", "b", ["wiki/b.md", "wiki/c.md"])
        self.write("think/t.md", "later thought")
        core.sync_human(root=self.root)
        core.restore(f"kb-{V}.1", root=self.root)
        self.assertEqual(self.subject(), f"kb(restore): back to kb-{V}.1 (kb-{V}.4)")
        self.assertIn(f"KB-Snapshot: kb-{V}.1", self.body())
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki/c.md")))
        self.assertEqual(self.read("wiki/b.md"), "v1\n")
        self.assertIn("later thought", self.read("think/t.md"))  # think/ untouched
        self.assertTrue(all(f.startswith("wiki/") or f in ("wiki/log.md",) for f in self.files()))

    def test_restore_needs_annotated_tag(self):
        self.op("digest", "a", ["wiki/a.md"])
        g(self.root, "tag", f"kb-{V}.1")
        with self.assertRaises(core.OpsError):
            core.restore(f"kb-{V}.1", root=self.root)


class SyncTests(OpsRepo):
    def test_sync_commits_think_then_leftovers_and_pushes(self):
        self.write("think/t.md", "night thought")
        self.write("wiki/stray.md", "stray")
        self.assertEqual(core.sync(root=self.root), 0)
        subjects = g(self.root, "log", "--format=%s", "-3").splitlines()
        self.assertTrue(subjects[0].startswith("kb(refine): unlabeled leftovers"))
        self.assertTrue(subjects[1].startswith("kb(think): human edits"))
        self.assertEqual(g(self.remote, "rev-parse", "main"), g(self.root, "rev-parse", "main"))

    def test_sync_waits_for_open_session(self):
        core.begin("refine", "a", root=self.root)
        self.write("wiki/a.md", "in progress")
        core.sync(push=False, root=self.root)
        self.assertIn("wiki/a.md", g(self.root, "status", "--porcelain"))

    def test_closed_researcher_sessions_do_not_block_sync(self):
        for slug, status in (("lior-wolf", "closed"), ("yoav-goldberg", "open")):
            d = os.path.join(self.root, "meta", ".researcher", slug)
            os.makedirs(d)
            with open(os.path.join(d, "session.json"), "w") as f:
                json.dump({"status": status}, f)
        self.assertEqual(core.open_researcher_sessions(self.root), ["yoav-goldberg"])
        os.remove(os.path.join(self.root, "meta", ".researcher", "yoav-goldberg", "session.json"))
        self.write("wiki/stray.md", "stray")
        core.sync(push=False, root=self.root)
        self.assertTrue(self.subject().startswith("kb(refine): unlabeled leftovers"))

    def test_sync_skips_when_locked(self):
        self.write("think/t.md", "x")
        with core.ops_lock(self.root):
            self.assertEqual(core.sync(push=False, root=self.root), 0)
        self.assertIn("think/t.md", g(self.root, "status", "--porcelain"))


class UpdateMainTests(OpsRepo):
    """A PR merges on GitHub while knowledge steps are still local → replay them on top."""

    def _remote_pr_merge(self):
        other = os.path.join(self.tmp.name, "other")
        g(self.tmp.name, "clone", "-q", self.remote, other)
        g(other, "config", "user.name", "t")
        g(other, "config", "user.email", "t@t")
        g(other, "checkout", "-q", "-b", "infra/x")
        with open(os.path.join(other, "meta", "tool.py"), "w") as f:
            f.write("x\n")
        g(other, "add", "-A")
        g(other, "commit", "-q", "-m", "feat(ops): tool")
        g(other, "checkout", "-q", "main")
        g(other, "merge", "-q", "--no-ff", "-m", "feat(ops): tool (#1)", "infra/x")
        g(other, "push", "-q", "origin", "main")

    def test_replays_unpushed_knowledge_steps(self):
        self.local_op("digest", "a", ["wiki/a.md"])
        self.local_op("catalog", "b", ["wiki/b.md"])
        self._remote_pr_merge()
        self.assertEqual(core.update_main(self.root), "replayed 2")
        subjects = g(self.root, "log", "--first-parent", "--format=%s", "-3").splitlines()
        self.assertTrue(subjects[0].startswith("kb(catalog): b"))
        self.assertEqual(subjects[2], "feat(ops): tool (#1)")
        self.assertEqual(core.sync(root=self.root), 0)  # now a plain fast-forward push
        self.assertEqual(g(self.remote, "rev-parse", "main"), g(self.root, "rev-parse", "main"))

    def test_replay_keeps_unrelated_uncommitted_edit(self):
        self.local_op("digest", "a", ["wiki/a.md"])
        self._remote_pr_merge()
        self.write("think/t.md", "draft in progress")  # tracked file, uncommitted
        self.assertEqual(core.update_main(self.root), "replayed 1")
        self.assertIn("draft in progress", self.read("think/t.md"))

    def test_refuses_when_local_has_tooling_commit(self):
        self.write("meta/local.py", "y")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "feat(ops): local tooling")
        self._remote_pr_merge()
        before = g(self.root, "rev-parse", "HEAD")
        with self.assertRaises(core.OpsError):
            core.update_main(self.root)
        self.assertEqual(g(self.root, "rev-parse", "HEAD"), before)

    def test_fast_forward_when_only_behind(self):
        self._remote_pr_merge()
        self.assertEqual(core.update_main(self.root), "fast-forward")

    def _remote_knowledge_step(self, path, text):
        """Another session pushed a kb step from an older base — the same page, other words."""
        other = os.path.join(self.tmp.name, "other2")
        g(self.tmp.name, "clone", "-q", self.remote, other)
        g(other, "config", "user.name", "t")
        g(other, "config", "user.email", "t@t")
        os.makedirs(os.path.dirname(os.path.join(other, path)), exist_ok=True)
        with open(os.path.join(other, path), "w") as f:
            f.write(text)
        g(other, "add", "-A")
        g(other, "commit", "-q", "-m", "kb(refine): same page elsewhere (kb-0.1.9)")
        g(other, "push", "-q", "origin", "main")

    def test_conflict_aborts_without_a_side(self):
        self.local_op("digest", "c", ["wiki/c.md"])
        self._remote_knowledge_step("wiki/c.md", "remote words\n")
        before = g(self.root, "rev-parse", "HEAD")
        with self.assertRaises(core.OpsError) as cm:
            core.update_main(self.root)
        self.assertIn("--prefer", str(cm.exception))
        self.assertEqual(g(self.root, "rev-parse", "HEAD"), before)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".git", "rebase-merge")))

    def test_prefer_local_keeps_the_replayed_text(self):
        self.local_op("digest", "c", ["wiki/c.md"])
        self._remote_knowledge_step("wiki/c.md", "remote words\n")
        self.assertEqual(core.update_main(self.root, prefer="local"), "replayed 1, kept local text in conflicts")
        self.assertEqual(self.read("wiki/c.md"), "digest c\n")
        subjects = g(self.root, "log", "--format=%s", "-2").splitlines()
        self.assertTrue(subjects[0].startswith("kb(digest): c"))
        self.assertTrue(subjects[1].startswith("kb(refine): same page elsewhere"))

    def test_prefer_origin_keeps_github_text(self):
        self.local_op("digest", "c", ["wiki/c.md"])
        self._remote_knowledge_step("wiki/c.md", "remote words\n")
        self.assertEqual(core.update_main(self.root, prefer="origin"), "replayed 1, kept origin text in conflicts")
        self.assertEqual(self.read("wiki/c.md"), "remote words\n")

    def test_prefer_must_be_a_side(self):
        with self.assertRaises(core.OpsError):
            core.update_main(self.root, prefer="mine")


class WrapTests(OpsRepo):
    def _cli(self, writes):
        def cli_main(argv):
            for rel in writes:
                if rel.startswith("wiki/") and rel.endswith(".md"):       # a page the OKF gate accepts
                    self.write(rel, "---\ntype: paper\n---\n\n# Written by cli\n", mode="w")
                else:
                    self.write(rel, "written by cli")
            return 0
        return cli_main

    def test_wrap_commits_only_command_changes(self):
        self.write("wiki/pre.md", "dirt from before")
        with patch.object(core, "ROOT", self.root):
            rc = wrap.run(self._cli(["wiki/2024-x.md", "raw/papers/2024-x.md"]), ["catalog", "raw/inbox/x.pdf"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.subject(), f"kb(catalog): 2024 x (kb-{V}.1)")  # subject in words, slug in KB-Target
        self.assertEqual(self.files(), {"wiki/2024-x.md", "raw/papers/2024-x.md", "wiki/log.md"})

    def test_no_commit_flag(self):
        with patch.object(core, "ROOT", self.root):
            wrap.run(self._cli(["wiki/a.md"]), ["catalog", "x", "--no-commit"])
        self.assertEqual(self.subject(), "chore: init (retro)")

    def test_unmapped_command_passes_through(self):
        with patch.object(core, "ROOT", self.root):
            wrap.run(self._cli(["wiki/a.md"]), ["status"])
        self.assertEqual(self.subject(), "chore: init (retro)")


class MessageTests(OpsRepo):
    def test_body_lists_pages_and_digest_gets_tier(self):
        self.write("wiki/paper-2023-a.md", "---\ntype: paper\nlayer: source\ndepth: full\n---\n", mode="w")
        self.op("digest", "paper-2023-a", ["wiki/paper-2023-a.md", "wiki/concept-x.md"])
        body = self.body()
        self.assertIn("- concept-x\n- paper-2023-a", body)
        c = cp.parse_message(body)
        self.assertEqual(c.trailers.get("KB-Tier"), "full")
        self.assertEqual(c.summary, "2023 a")

    def test_hash_target_falls_back_to_a_page(self):
        self.op("digest", "86c9846f6151", ["wiki/paper-2020-b.md"])
        self.assertEqual(cp.parse_message(self.body()).trailers["KB-Target"], "paper-2020-b")

    def test_long_slug_is_cut_at_a_word(self):
        slug = "paper-2024-transformers-learn-low-sensitivity-functions-investigations-and-implications-for-reasoning"
        self.op("catalog", slug, [f"wiki/{slug}.md"])
        c = cp.parse_message(self.body())
        self.assertLessEqual(len(c.summary), cp.MAX_SUMMARY)
        self.assertTrue(c.summary.endswith("…"))
        self.assertIn(c.summary[:-1].split()[-1], slug.split("-"))   # whole words only
        self.assertEqual(c.trailers["KB-Target"], slug)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for backend/src/kb/git/commit_policy.py — grammar, lanes, versions, push ranges, tags."""
import os
import subprocess
import sys
import tempfile
import unittest

from kb.paths import vault_root
ROOT = vault_root()

from kb.git import commit_policy as cp


def kb_msg(op, summary, version, **extra):
    trailers = {"KB-Version": version, "KB-Op": op, "KB-Target": "x", **extra}
    lines = "\n".join(f"{k}: {v}" for k, v in trailers.items())
    return f"kb({op}): {summary} (kb-{version})\n\n{lines}\n"


def git(cwd, *args, env=None):
    e = os.environ.copy()
    e.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    if env:
        e.update(env)
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=e).stdout.strip()


class TempRepo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name
        git(self.path, "init", "-q", "-b", "main")
        git(self.path, "config", "user.name", "t")
        git(self.path, "config", "user.email", "t@t")

    def write(self, rel, text="x"):
        full = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a") as f:
            f.write(text + "\n")

    def commit(self, message, *files):
        for f in files:
            self.write(f)
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def head(self):
        return git(self.path, "rev-parse", "HEAD")

    def close(self):
        self.tmp.cleanup()


class ParseTests(unittest.TestCase):
    def test_kb(self):
        c = cp.parse_message(kb_msg("digest", "2017-failures", "0.7.3"))
        self.assertEqual((c.kind, c.scope, c.version), ("kb", "digest", (0, 7, 3)))
        self.assertEqual(c.trailers["KB-Op"], "digest")

    def test_infra_and_merges(self):
        self.assertEqual(cp.parse_message("feat(dashboard): graph explorer").kind, "infra")
        m = cp.parse_message("feat(dashboard): graph explorer (#12)")
        self.assertEqual((m.kind, m.pr), ("pr-merge", 12))
        r = cp.parse_message("chore(git): connect remote (retro)")
        self.assertTrue(r.retro)
        self.assertEqual(cp.parse_message("Merge branch 'main' into infra/x").kind, "sync-merge")
        self.assertEqual(cp.parse_message("researcher | amnon").kind, "unknown")

    def test_trailers_need_last_paragraph(self):
        self.assertEqual(cp.parse_trailers("subject only"), {})
        self.assertEqual(cp.parse_trailers("s\n\nbody text\n\nA-B: c"), {"A-B": "c"})
        self.assertEqual(cp.parse_trailers("s\n\nnot a trailer line"), {})


class CheckMessageTests(unittest.TestCase):
    def test_kb_ok(self):
        self.assertEqual(cp.check_message(kb_msg("digest", "x", "0.7.3"), "main", ["wiki/a.md", "index.md"]), [])

    def test_kb_rules(self):
        self.assertTrue(cp.check_message(kb_msg("digest", "x", "0.7.3"), "infra/y", ["wiki/a.md"]))
        self.assertTrue(cp.check_message(kb_msg("digest", "x", "0.7.3"), "main", ["backend/src/kb/git/ship.py"]))
        self.assertTrue(cp.check_message(kb_msg("digest", "x", "0.7.3"), "main", ["think/a.md", "wiki/a.md"]))
        self.assertTrue(cp.check_message(kb_msg("undo", "x", "0.7.3"), "main", ["wiki/a.md"]))
        self.assertEqual(cp.check_message(kb_msg("undo", "x", "0.7.3", **{"KB-Reverts": "abc"}), "main", ["wiki/a.md"]), [])
        bad_trailer = "kb(digest): x (kb-0.7.3)\n\nKB-Version: 0.7.4\nKB-Op: digest"
        self.assertTrue(cp.check_message(bad_trailer, "main", ["wiki/a.md"]))

    def test_kb_think_only(self):
        self.assertEqual(cp.check_message(kb_msg("think", "human edits", "0.7.3"), "main", ["think/a.md"]), [])
        self.assertTrue(cp.check_message(kb_msg("think", "x", "0.7.3"), "main", ["think/a.md", "wiki/b.md"]))

    def test_infra_rules(self):
        self.assertEqual(cp.check_message("feat(ops): undo", "infra/kb-ops", ["backend/src/kb/ops/undo.py"]), [])
        self.assertTrue(cp.check_message("feat(ops): undo", "main", ["backend/src/kb/ops/undo.py"]))
        self.assertTrue(cp.check_message("feat(ops): undo", "infra/kb-ops", ["wiki/a.md"]))
        self.assertEqual(cp.check_message("schema(books): hub", "infra/books", ["backend/src/kb/core/schema.py", "wiki/a.md"]), [])
        self.assertTrue(cp.check_message("nonsense message", "infra/x", ["meta/a.py"]))
        self.assertTrue(cp.check_message("feat(ops): " + "x" * 80, "infra/x", ["meta/a.py"]))

    def test_strict_form(self):
        self.assertTrue(cp.check_message("feat: no scope", "infra/x", ["meta/a.py"]))
        self.assertTrue(cp.check_message("docs(skills): old type", "infra/x", ["meta/a.py"]))
        self.assertTrue(cp.check_message("refactor(ops): old type", "infra/x", ["meta/a.py"]))
        self.assertEqual(cp.check_message("chore(skills): document the flow", "infra/x", ["meta/a.py"]), [])

    def test_merges(self):
        self.assertEqual(cp.check_message("feat(x): y (#3)", "main", [], is_merge=True), [])
        self.assertTrue(cp.check_message("Merge branch 'infra/x'", "main", [], is_merge=True))
        self.assertEqual(cp.check_message("Merge branch 'main' into infra/x", "infra/x", [], is_merge=True), [])
        self.assertTrue(cp.check_message("schema(books): hub (#4)", "main", [], is_merge=True))
        ok = "schema(books): hub (#4)\n\nKB-Version: 0.8.0"
        self.assertEqual(cp.check_message(ok, "main", [], is_merge=True), [])


class MergeVersionTests(unittest.TestCase):
    def test_merge_version(self):
        self.assertEqual(cp.merge_version((0, 8), (0, 7, 4), "schema"), (0, 8, 0))
        self.assertEqual(cp.merge_version((0, 8), None, "schema"), (0, 8, 0))  # no version yet
        self.assertEqual(cp.merge_version((1, 0), (0, 8, 3), "paradigm"), (1, 0, 0))
        with self.assertRaises(ValueError):
            cp.merge_version((0, 9), (0, 7, 4), "schema")
        with self.assertRaises(ValueError):
            cp.merge_version((0, 7), (0, 7, 4), "schema")
        self.assertIsNone(cp.bumped_version(None, "schema"))


class VersionAndPushTests(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.base = self.repo.commit("chore: init (retro)", "README.md")

    def tearDown(self):
        self.repo.close()

    def test_next_version_without_history(self):
        self.assertEqual(cp.next_version(self.repo.path, schema_version=(0, 7)), (0, 7, 1))

    def test_next_version_increments(self):
        self.repo.commit(kb_msg("digest", "a", "0.7.5"), "wiki/a.md")
        self.assertEqual(cp.next_version(self.repo.path, schema_version=(0, 7)), (0, 7, 6))
        self.assertEqual(cp.last_version(self.repo.path), (0, 7, 5))

    def test_push_range_accepts_sequence_and_pr_merge(self):
        old = self.repo.commit(kb_msg("digest", "a", "0.7.1"), "wiki/a.md")
        self.repo.commit(kb_msg("catalog", "b", "0.7.2"), "wiki/b.md")
        git(self.repo.path, "checkout", "-q", "-b", "infra/x")
        self.repo.commit("feat(ops): thing", "backend/src/kb/ops.py")
        git(self.repo.path, "checkout", "-q", "main")
        git(self.repo.path, "merge", "-q", "--no-ff", "-m", "feat(ops): thing (#1)", "infra/x")
        self.repo.commit(kb_msg("refine", "c", "0.7.3"), "wiki/c.md")
        self.assertEqual(cp.check_push_range(self.repo.path, old, self.repo.head()), [])

    def test_push_range_rejects_direct_feat_and_bad_version(self):
        old = self.repo.commit(kb_msg("digest", "a", "0.7.1"), "wiki/a.md")
        self.repo.commit("feat(ops): direct", "backend/src/kb/ops.py")
        self.repo.commit(kb_msg("digest", "b", "0.7.5"), "wiki/b.md")
        v = cp.check_push_range(self.repo.path, old, self.repo.head())
        self.assertTrue(any("only kb" in x for x in v))
        self.assertTrue(any("should be 0.7.2" in x for x in v))

    def test_schema_merge_bumps(self):
        old = self.repo.commit(kb_msg("digest", "a", "0.7.4"), "wiki/a.md")
        git(self.repo.path, "checkout", "-q", "-b", "infra/books")
        self.repo.commit("schema(books): hub", "backend/src/kb/core/schema.py")
        git(self.repo.path, "checkout", "-q", "main")
        git(self.repo.path, "merge", "-q", "--no-ff", "-m", "schema(books): hub (#2)\n\nKB-Version: 0.8.0", "infra/books")
        self.repo.commit(kb_msg("digest", "b", "0.8.1"), "wiki/b.md")
        self.assertEqual(cp.check_push_range(self.repo.path, old, self.repo.head()), [])

    def test_force_push_rejected_unless_allowed(self):
        a = self.repo.commit(kb_msg("digest", "a", "0.7.1"), "wiki/a.md")
        git(self.repo.path, "reset", "-q", "--hard", self.base)
        b = self.repo.commit(kb_msg("digest", "b", "0.7.1"), "wiki/b.md")
        self.assertTrue(cp.check_push_range(self.repo.path, a, b))
        os.environ["KB_ALLOW_REWRITE"] = "1"
        try:
            self.assertEqual(cp.check_push_range(self.repo.path, a, b), [])
        finally:
            del os.environ["KB_ALLOW_REWRITE"]

    def test_tags(self):
        self.repo.commit(kb_msg("digest", "a", "0.7.1"), "wiki/a.md")
        git(self.repo.path, "tag", "-a", "kb-0.7.1", "-m", "week 43")
        git(self.repo.path, "tag", "kb-0.7.9")
        sha_good = git(self.repo.path, "rev-parse", "kb-0.7.1")
        sha_light = git(self.repo.path, "rev-parse", "kb-0.7.9")
        self.assertEqual(cp.check_tag(self.repo.path, "kb-0.7.1", sha_good), [])
        self.assertTrue(cp.check_tag(self.repo.path, "kb-0.7.9", sha_light))


class ConventionHardeningTests(unittest.TestCase):
    def test_hash_target_rejected(self):
        msg = kb_msg("digest", "a", "0.7.1").replace("KB-Target: x", "KB-Target: 86c9846f6151")
        self.assertTrue(any("KB-Target" in v for v in cp.check_message(msg, "main", ["wiki/a.md"])))

    def test_tier_only_on_digest_and_valid(self):
        ok = kb_msg("digest", "a", "0.7.1", **{"KB-Tier": "easy"})
        self.assertEqual(cp.check_message(ok, "main", ["wiki/a.md"]), [])
        for msg in (kb_msg("digest", "a", "0.7.1", **{"KB-Tier": "medium"}),
                    kb_msg("catalog", "a", "0.7.1", **{"KB-Tier": "easy"})):
            self.assertTrue(any("KB-Tier" in v for v in cp.check_message(msg, "main", ["wiki/a.md"])))

    def test_whole_subject_length(self):
        msg = "feat(dashboard-and-everything-else): " + "x" * 70
        self.assertTrue(any("subject line" in v for v in cp.check_message(msg, "infra/a", ["meta/a.py"])))

    def test_pr_title_takes_highest_type(self):
        subjects = ["fix(ops): a", "feat(ops): b", "chore(git): c", "Merge branch 'main' into infra/x"]
        self.assertEqual(cp.highest_type(subjects), "feat")
        self.assertTrue(cp.check_pr_title("fix(ops): a and b", subjects))
        self.assertEqual(cp.check_pr_title("feat(ops): a and b", subjects), [])
        self.assertEqual(cp.check_pr_title("schema(ops): a and b", subjects), [])
        self.assertTrue(cp.check_pr_title("not a title", subjects))
        self.assertTrue(any("too long" in v for v in cp.check_pr_title("feat(ops): " + "y" * 85, subjects)))


if __name__ == "__main__":
    unittest.main()

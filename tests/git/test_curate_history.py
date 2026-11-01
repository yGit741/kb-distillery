#!/usr/bin/env python3
"""Tests for src/kb_distillery/git/curate_history.py on a synthetic repo (split + rename + infra chapter + replay)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.git import curate_history

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=ENV).stdout.strip()


def kb(op, summary, version):
    return f"kb({op}): {summary} (kb-{version})\n\nKB-Version: {version}\nKB-Op: {op}\nKB-Target: t\n"


class CurateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.src)
        g(self.src, "init", "-q", "-b", "main")
        g(self.src, "config", "user.name", "t")
        g(self.src, "config", "user.email", "t@t")
        self.c1 = self._commit("init", {"wiki/a.md": "a", "meta/x.py": "x1"})
        self.c2 = self._commit("big squash", {"meta/x.py": "x2", "meta/y.py": "y", "wiki/b.md": "b",
                                              "wiki/a2.md": "a"}, delete=["wiki/a.md"])
        self.c3 = self._commit("add c", {"wiki/c.md": "c"})
        self._patch_env = unittest.mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull,
                                                                "GIT_CONFIG_NOSYSTEM": "1"})
        self._patch_env.start()

    def tearDown(self):
        self._patch_env.stop()
        self.tmp.cleanup()

    def _commit(self, msg, files, delete=()):
        for rel, text in files.items():
            full = os.path.join(self.src, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(text + "\n")
        for rel in delete:
            os.remove(os.path.join(self.src, rel))
        g(self.src, "add", "-A")
        g(self.src, "commit", "-q", "-m", msg)
        return g(self.src, "rev-parse", "HEAD")

    def plan(self, **over):
        steps = [
            {"id": "c1", "orig": self.c1, "mode": "keep", "chapter": "kb/boot", "verdict": "ok",
             "message": kb("import", "initial vault", "0.0.1"), "author_date": "2026-08-01T10:00:00+03:00"},
            {"id": "n01", "orig": self.c2, "mode": "split", "paths": ["meta/x.py"], "chapter": "infra/tools",
             "verdict": "ok", "message": "feat(tools): update x", "author_date": "2026-08-02T10:00:00+03:00"},
            {"id": "n02", "orig": self.c2, "mode": "split", "paths": ["wiki/b.md", "-wiki/a.md", "wiki/a2.md"],
             "chapter": "kb/notes", "verdict": "ok", "message": kb("refine", "rename a, add b", "0.0.2"),
             "author_date": "2026-08-02T11:00:00+03:00"},
            {"id": "n03", "orig": self.c2, "mode": "split", "paths": ["meta/y.py"], "chapter": "infra/tools",
             "verdict": "ok", "message": "feat(tools): add y", "author_date": "2026-08-02T12:00:00+03:00"},
            {"id": "c3", "orig": self.c3, "mode": "keep", "chapter": "kb/notes", "verdict": "ok",
             "message": kb("catalog", "add c", "0.0.3"), "author_date": "2026-08-03T10:00:00+03:00"},
        ]
        plan = {"horizon": self.c3, "steps": steps,
                "chapters": {"infra/tools": {"message": "feat(tools): x and y (retro)"}}}
        plan.update(over)
        return plan

    def run_build(self, plan, **kw):
        return curate_history.build(self.src, json.loads(json.dumps(plan)), os.path.join(self.tmp.name, "out"), **kw)

    def test_build_verifies_and_shapes_history(self):
        later = self._commit("chore: later", {"meta/z.py": "z"})
        report = self.run_build(self.plan(), keep_old=False)
        self.assertEqual(report["result"], "verified", report)
        repo = os.path.join(self.tmp.name, "out", "repo")
        tip = report["tip"]
        self.assertEqual(g(repo, "rev-parse", f"{tip}^{{tree}}"), g(self.src, "rev-parse", f"{later}^{{tree}}"))
        subjects = g(repo, "log", "--first-parent", "--format=%s", tip).splitlines()
        self.assertEqual(subjects, ["chore: later", "kb(catalog): add c (kb-0.0.3)",
                                    "feat(tools): x and y (retro)", "kb(refine): rename a, add b (kb-0.0.2)",
                                    "kb(import): initial vault (kb-0.0.1)"])
        merge = g(repo, "log", "--first-parent", "--merges", "--format=%H", tip)
        self.assertEqual(len(g(repo, "log", "-1", "--format=%P", merge).split()), 2)
        self.assertIn("Reconstructed-from:", g(repo, "log", "-1", "--format=%B", f"{merge}^2"))
        self.assertEqual(report["tag"], "kb-0.0.3")
        self.assertEqual(g(repo, "cat-file", "-t", "kb-0.0.3"), "tag")
        self.assertEqual(g(self.src, "rev-parse", "main"), later)  # source untouched
        self.assertTrue(os.path.exists(report["bundle"]))

    def test_keep_old_joins_original_history(self):
        report = self.run_build(self.plan())
        self.assertEqual(report["result"], "verified", report)
        self.assertTrue(report["checks"]["fast_forward_from_source_main"])
        repo = os.path.join(self.tmp.name, "out", "repo")
        tip = report["tip"]
        self.assertEqual(g(repo, "log", "-1", "--format=%s", tip), curate_history.ADOPT_SUBJECT)
        parents = g(repo, "log", "-1", "--format=%P", tip).split()
        self.assertEqual(parents[1], self.c3)  # old main kept as second parent
        self.assertEqual(g(repo, "rev-parse", f"{tip}^{{tree}}"), g(self.src, "rev-parse", "main^{tree}"))
        first_parent = g(repo, "log", "--first-parent", "--format=%s", tip).splitlines()
        self.assertNotIn("add c", first_parent)  # curated line, not the originals
        self.assertEqual(report["tag"], "kb-0.0.3")
        self.assertTrue(any("merge --ff-only" in step for step in report["adopt"]))

    def test_replay_message_override(self):
        later = self._commit("schema(books): add hub (#4)\n\nKB-Version: 0.9.0", {"meta/z.py": "z"})
        plan = self.plan(replay_messages={later[:7]: "schema(books): add hub (#4)\n\nKB-Version: 0.1.0"})
        report = self.run_build(plan, keep_old=False)
        repo = os.path.join(self.tmp.name, "out", "repo")
        body = g(repo, "log", "-1", "--format=%B", report["tip"])
        trailers = curate_history.commit_policy.parse_trailers(body)
        self.assertEqual(trailers.get("KB-Version"), "0.1.0")  # still a real trailer
        self.assertEqual(trailers.get("Corrected-from"), later[:12])

    def test_missing_path_is_an_error(self):
        plan = self.plan()
        plan["steps"][3]["paths"] = []
        report = self.run_build(plan)
        self.assertEqual(report["result"], "invalid")
        self.assertTrue(any("not assigned" in e for e in report["errors"]))

    def test_duplicate_and_wrong_deletion(self):
        plan = self.plan()
        plan["steps"][3]["paths"] = ["meta/y.py", "meta/x.py"]
        plan["steps"][2]["paths"] = ["wiki/b.md", "-wiki/a.md", "-wiki/a2.md"]
        report = self.run_build(plan, dry_run=True)
        self.assertTrue(any("assigned to both" in e for e in report["errors"]))

    def test_unreviewed_rejected(self):
        plan = self.plan()
        plan["steps"][0]["verdict"] = None
        self.assertEqual(self.run_build(plan, dry_run=True)["result"], "invalid")
        self.assertEqual(self.run_build(plan, dry_run=True, allow_unreviewed=True)["result"], "valid (dry run)")

    def test_chapter_overlap_detected(self):
        steps = [{"id": "a", "chapter": "infra/t"}, {"id": "b", "chapter": "kb/n"}, {"id": "c", "chapter": "infra/t"}]
        clash = [[("meta/x.py", "1", "s")], [("meta/x.py", "1", "s")], [("meta/y.py", "1", "s")]]
        fine = [[("meta/x.py", "1", "s")], [("wiki/b.md", "1", "s")], [("meta/y.py", "1", "s")]]
        self.assertTrue(curate_history.chapter_overlaps(steps, clash))
        self.assertEqual(curate_history.chapter_overlaps(steps, fine), [])

    def test_valid_plan_dry_run(self):
        self.assertEqual(self.run_build(self.plan(), dry_run=True)["result"], "valid (dry run)")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for src/kb_distillery/ops/migrate.py and the versioned git hooks (scripts/githooks)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.kbconfig import checkout_root
from kb_distillery.paths import CODE_DIR, vault_root
CHECKOUT_ROOT = checkout_root()
ROOT = vault_root()

from kb_distillery.ops import migrate

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB": "", "KB_ROOT": "",
       "PYTHONPATH": ""}   # the temp repo is its own vault, and its hooks must import ITS stub package, not the suite's


def g(cwd, *args, env=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True,
                          env=dict(os.environ, **ENV, **(env or {})))


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        d = os.path.join(self.root, "meta", "migrations")
        os.makedirs(d)
        with open(os.path.join(d, "0001_base.py"), "w") as f:
            f.write("PRODUCES = (0, 7)\ndef apply(root):\n    pass\n")
        with open(os.path.join(d, "0002_add_field.py"), "w") as f:
            f.write("import os\nPRODUCES = (0, 7)\ndef apply(root):\n"
                    "    open(os.path.join(root, 'touched'), 'a').write('x')\n")
        with open(os.path.join(d, "applied.tsv"), "w") as f:
            f.write("id\tdate\tschema\n0001_base\t2026-10-21\t0.7\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_and_run_once(self):
        self.assertEqual(migrate.pending_migrations(self.root), ["0002_add_field"])
        self.assertEqual(migrate.run(self.root, "infra/x", check=True), ["0002_add_field"])
        self.assertEqual(migrate.run(self.root, "infra/x"), ["0002_add_field"])
        self.assertEqual(migrate.pending_migrations(self.root), [])
        self.assertEqual(migrate.run(self.root, "infra/x"), [])
        with open(os.path.join(self.root, "touched")) as f:
            self.assertEqual(f.read(), "x")

    def test_refused_on_main(self):
        with self.assertRaises(RuntimeError):
            migrate.run(self.root, "main")

    def test_produces_ahead_of_schema_refused(self):
        with open(os.path.join(self.root, "meta", "migrations", "0003_future.py"), "w") as f:
            f.write("PRODUCES = (9, 9)\ndef apply(root):\n    pass\n")
        with self.assertRaises(RuntimeError):
            migrate.run(self.root, "infra/x")  # applies 0002, then refuses 0003
        self.assertEqual(migrate.pending_migrations(self.root), ["0003_future"])

    def test_repo_baseline_recorded(self):
        self.assertEqual(migrate.pending_migrations(ROOT), [])


class GitHooksTests(unittest.TestCase):
    """scripts/githooks installed in a temp repo: lint skip token, commit-msg policy, pre-push."""

    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.remote = os.path.join(self.tmp.name, "remote.git")
        self.root = os.path.join(self.tmp.name, "kb")
        g(self.tmp.name, "init", "-q", "--bare", "-b", "main", self.remote)
        g(self.tmp.name, "clone", "-q", self.remote, self.root)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            g(self.root, "config", k, v)
        kb = os.path.join(self.root, "src", "kb_distillery")
        for rel in ("__init__.py", "paths.py", "kbconfig.py", "config/__init__.py", "config/resources.py", "core/__init__.py", "core/schema.py", "core/kbtypes.py",
                    "git/__init__.py", "git/commit_policy.py"):
            os.makedirs(os.path.dirname(os.path.join(kb, rel)), exist_ok=True)
            shutil.copy(os.path.join(CODE_DIR, rel), os.path.join(kb, rel))
        shutil.copytree(os.path.join(CHECKOUT_ROOT, "scripts", "githooks"), os.path.join(self.root, "scripts", "githooks"))
        shutil.copy(os.path.join(CHECKOUT_ROOT, "scripts", "hooks-python.sh"), os.path.join(self.root, "scripts", "hooks-python.sh"))
        os.makedirs(os.path.join(kb, "lint"))
        for rel, text in (("__init__.py", ""),
                          ("lint.py", "import os, sys\nsys.exit(1 if os.path.exists('LINT_FAIL') else 0)\n"),
                          ("okf_check.py", "import os, sys\nsys.exit(1 if os.path.exists('OKF_FAIL') else 0)\n"),
                          ("lint_skills.py", "import sys; sys.exit(0)\n")):
            with open(os.path.join(kb, "lint", rel), "w") as f:
                f.write(text)
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "chore: init (retro)")
        g(self.root, "push", "-q", "-u", "origin", "main")
        g(self.root, "config", "core.hooksPath", "scripts/githooks")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def _write(self, rel):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a") as f:
            f.write("x\n")
        g(self.root, "add", "-A")

    def test_enforce_rejects_bad_message(self):
        self._write("wiki/a.md")
        proc = g(self.root, "commit", "-m", "random message", env={"KB_POLICY": "enforce"}, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("KB Conventional Commits", proc.stderr)

    def test_warn_allows_with_warning(self):
        self._write("wiki/a.md")
        proc = g(self.root, "commit", "-m", "random message", env={"KB_POLICY": "warn"}, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("warning", proc.stderr)

    def test_kb_commit_accepted_and_lint_gate(self):
        self._write("wiki/a.md")
        msg = "kb(digest): a (kb-0.7.1)\n\nKB-Version: 0.7.1\nKB-Op: digest\nKB-Target: a"
        open(os.path.join(self.root, "LINT_FAIL"), "w").close()
        self.assertNotEqual(g(self.root, "commit", "-m", msg, env={"KB_POLICY": "enforce"}, check=False).returncode, 0)
        token = os.path.join(self.root, ".git", "kb-linted")
        with open(token, "w") as f:
            f.write("nonce123")
        proc = g(self.root, "commit", "-m", msg, env={"KB_POLICY": "enforce", "KB_LINTED": "nonce123"}, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)  # lint skipped via the one-time token

    def test_okf_check_blocks_a_direct_commit(self):
        self._write("wiki/a.md")
        msg = "kb(digest): a (kb-0.7.1)\n\nKB-Version: 0.7.1\nKB-Op: digest\nKB-Target: a"
        open(os.path.join(self.root, "OKF_FAIL"), "w").close()
        proc = g(self.root, "commit", "-m", msg, env={"KB_POLICY": "enforce"}, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("okf-check failed", proc.stderr)
        os.remove(os.path.join(self.root, "OKF_FAIL"))
        self.assertEqual(g(self.root, "commit", "-m", msg, env={"KB_POLICY": "enforce"}, check=False).returncode, 0)

    def test_pre_push_rejects_direct_feat_on_main(self):
        self._write("meta/tool.py")
        g(self.root, "commit", "-q", "-m", "feat(x): direct", env={"KB_POLICY": "warn"})
        proc = g(self.root, "push", "origin", "main", env={"KB_POLICY": "enforce"}, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("only kb", proc.stderr)


if __name__ == "__main__":
    unittest.main()

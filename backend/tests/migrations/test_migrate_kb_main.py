"""`ops migrate` on a kb that is its own git repo: runs on its main and commits one chore(schema). Needs no kb content."""
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kb.ops import migrate

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB": "", "KB_ROOT": ""}


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV))


def _kb_files(path):
    os.makedirs(os.path.join(path, "meta", "migrations"))
    with open(os.path.join(path, "meta", "migrations", "0001_bump.py"), "w") as f:
        f.write("PRODUCES = (%d, %d)\ndef apply(root):\n    pass\n" % migrate.SCHEMA_VERSION)
    with open(os.path.join(path, "kb.toml"), "w") as f:
        f.write('[kb]\nid = "x"\nschema_version = "0.1"   # keep this comment\n\n[git]\ntag_prefix = "kb-"\n')


class MigrateOnKbMainTests(unittest.TestCase):
    """A kb that is its own repo migrates on its main: one chore(schema) commit, kb.toml comments kept."""

    def test_own_repo_migrates_on_main_and_commits_one_chore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            _kb_files(root)
            g(root, "init", "-q", "-b", "main")
            for k, v in (("user.name", "t"), ("user.email", "t@t")):
                g(root, "config", k, v)
            g(root, "add", "-A")
            g(root, "commit", "-q", "-m", "init")
            self.assertTrue(migrate.own_repo(root))
            with patch.dict(os.environ, ENV), patch("sys.dont_write_bytecode", True):   # no __pycache__ in the temp kb
                self.assertEqual(migrate.run(root, "main"), ["0001_bump"])
                want = "%d.%d" % migrate.SCHEMA_VERSION
                with open(os.path.join(root, "kb.toml")) as f:
                    self.assertIn(f'schema_version = "{want}"   # keep this comment', f.read())
                self.assertEqual(g(root, "status", "--porcelain").stdout, "")
                self.assertEqual(g(root, "log", "--format=%s", "-1").stdout.strip(),
                                 f"chore(schema): schema {want} (0001_bump)")
                self.assertEqual(migrate.pending_migrations(root), [])
                self.assertEqual(migrate.run(root, "main"), [])        # nothing left: no second commit
                self.assertEqual(g(root, "rev-list", "--count", "HEAD").stdout.strip(), "2")

    def test_a_kb_inside_another_repo_still_needs_a_schema_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = os.path.realpath(tmp)
            g(outer, "init", "-q", "-b", "main")
            inner = os.path.join(outer, "kbs", "demo")
            _kb_files(inner)
            self.assertFalse(migrate.own_repo(inner))
            with self.assertRaises(RuntimeError):
                migrate.run(inner, "main")


if __name__ == "__main__":
    unittest.main()

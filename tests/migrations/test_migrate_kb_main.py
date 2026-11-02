"""`ops migrate` on a kb that is its own git repo: runs on its main and commits one chore(schema). Needs no kb content."""
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.ops import migrate

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB": "", "KB_ROOT": ""}
WANT = "%d.%d" % migrate.SCHEMA_VERSION
KB_TOML = '[kb]\nid = "x"\nschema_version = "0.1"   # keep this comment\n\n[git]\ntag_prefix = "kb-"\n'


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV))


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _kb_files(path, toml=KB_TOML):
    write(path, "meta/migrations/0001_bump.py", "PRODUCES = (%d, %d)\ndef apply(root):\n    pass\n" % migrate.SCHEMA_VERSION)
    write(path, "kb.toml", toml)
    write(path, ".gitignore", "meta/.ops/\n__pycache__/\n")
    write(path, "wiki/a.md", "---\ntype: idea\n---\n\n# A\n")


def make_repo(root, toml=KB_TOML):
    _kb_files(root, toml)
    g(root, "init", "-q", "-b", "main")
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        g(root, "config", k, v)
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "init")


def run(root, branch="main"):
    with patch.dict(os.environ, ENV), patch("sys.dont_write_bytecode", True):
        return migrate.run(root, branch)


class MigrateOnKbMainTests(unittest.TestCase):
    """A kb that is its own repo migrates on its main: one chore(schema) commit, kb.toml comments kept."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_own_repo_migrates_on_main_and_commits_one_chore(self):
        make_repo(self.root)
        self.assertTrue(migrate.own_repo(self.root))
        self.assertEqual(run(self.root), ["0001_bump"])
        with open(os.path.join(self.root, "kb.toml")) as f:
            self.assertIn(f'schema_version = "{WANT}"   # keep this comment', f.read())
        self.assertEqual(g(self.root, "status", "--porcelain").stdout, "")
        self.assertEqual(g(self.root, "log", "--format=%s", "-1").stdout.strip(), f"chore(schema): schema {WANT} (0001_bump)")
        self.assertEqual(migrate.pending_migrations(self.root), [])
        self.assertEqual(run(self.root), [])                       # nothing left: no second commit
        self.assertEqual(g(self.root, "rev-list", "--count", "HEAD").stdout.strip(), "2")

    def test_a_dirty_note_stops_it_before_anything_changes(self):
        make_repo(self.root)
        write(self.root, "wiki/a.md", "---\ntype: idea\n---\n\n# A, edited\n")
        with self.assertRaises(RuntimeError) as cm:
            run(self.root)
        self.assertIn("wiki/a.md", str(cm.exception))
        self.assertEqual(migrate.pending_migrations(self.root), ["0001_bump"])     # nothing applied
        self.assertEqual(g(self.root, "rev-list", "--count", "HEAD").stdout.strip(), "1")

    def test_other_kb_toml_edits_are_allowed_and_named_in_the_commit(self):
        make_repo(self.root)
        write(self.root, "kb.toml", KB_TOML + '\n[edges]\ntypes = ["extends"]\n')
        run(self.root)
        body = g(self.root, "log", "--format=%B", "-1").stdout
        self.assertIn("kb.toml also carried uncommitted edits", body)
        self.assertIn("[edges]", g(self.root, "show", "HEAD:kb.toml").stdout)
        self.assertEqual(g(self.root, "status", "--porcelain").stdout, "")

    def test_a_rerun_finishes_a_run_that_stopped_after_recording_the_migration(self):
        make_repo(self.root)
        write(self.root, "meta/migrations/applied.tsv", "id\tdate\tschema\n0001_bump\t2026-10-31\t%s\n" % WANT)
        self.assertEqual(migrate.pending_migrations(self.root), [])               # recorded, but kb.toml still old
        run(self.root)
        self.assertEqual(migrate._kb_toml_version(self.root), WANT)
        self.assertEqual(g(self.root, "status", "--porcelain").stdout, "")
        self.assertEqual(g(self.root, "log", "--format=%s", "-1").stdout.strip(), f"chore(schema): schema {WANT}")

    def test_single_quoted_version_and_another_table_first(self):
        make_repo(self.root, toml='[other]\nschema_version = "9.9"\n\n[kb]\nid = "x"\nschema_version = \'0.1\'\n')
        run(self.root)
        text = g(self.root, "show", "HEAD:kb.toml").stdout
        self.assertIn('[other]\nschema_version = "9.9"', text)                    # not the [kb] table: left alone
        self.assertEqual(migrate._kb_toml_version(self.root), WANT)

    def test_an_unreadable_version_raises_instead_of_committing(self):
        make_repo(self.root, toml="[kb]\nid = \"x\"\nschema_version = 0.1\n")
        with self.assertRaises(RuntimeError):
            run(self.root)
        self.assertEqual(g(self.root, "log", "--format=%s", "-1").stdout.strip(), "init")

    def test_the_index_and_log_move_is_committed_and_a_dirty_legacy_index_does_not_block_it(self):
        """Migration 0015 on a kb's main: the root index.md and meta/log.md are deleted, wiki/log.md is created, and all
        of it is committed (a regenerated root index.md, dirty before the run, must not stop the migration)."""
        import shutil
        from kb_distillery.paths import MIGRATIONS_CODE_PATH
        make_repo(self.root, toml=KB_TOML.replace("0.1", "1.6"))
        os.remove(os.path.join(self.root, "meta", "migrations", "0001_bump.py"))
        shutil.copy(os.path.join(MIGRATIONS_CODE_PATH, "0015_okf_index_log.py"),
                    os.path.join(self.root, "meta", "migrations", "0015_okf_index_log.py"))
        write(self.root, "index.md", "| [[a]] | x |\n")
        write(self.root, "meta/log.md", "# Wiki log\n\n## [2026-08-07] setup | first\n\n## [2026-08-08] ingest | second\n")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "kb(catalog): old layout (kb-1.6.1)")
        write(self.root, "index.md", "| [[a]] | regenerated and dirty |\n")
        with patch("kb_distillery.ops.core.run_lint", return_value=None):
            ids = run(self.root)
        self.assertEqual(ids, ["0015_okf_index_log"])
        self.assertEqual(g(self.root, "status", "--porcelain").stdout, "")                  # everything committed
        tree = g(self.root, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
        self.assertNotIn("index.md", tree)
        self.assertNotIn("meta/log.md", tree)
        self.assertIn("wiki/log.md", tree)
        log = g(self.root, "show", "HEAD:wiki/log.md").stdout
        self.assertLess(log.index("### ingest | second"), log.index("### setup | first"))   # newest first
        self.assertTrue(g(self.root, "log", "--format=%s", "-1").stdout.startswith("kb(refine): migrate notes to schema"))

    def test_a_kb_inside_another_repo_still_needs_a_schema_pr(self):
        g(self.root, "init", "-q", "-b", "main")
        inner = os.path.join(self.root, "examples", "demo")
        _kb_files(inner)
        self.assertFalse(migrate.own_repo(inner))
        with self.assertRaises(RuntimeError):
            migrate.run(inner, "main")

    def test_an_own_repo_off_main_is_refused_with_its_own_message(self):
        make_repo(self.root)
        with self.assertRaises(RuntimeError) as cm:
            migrate.run(self.root, "topic")
        self.assertIn("on its main", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

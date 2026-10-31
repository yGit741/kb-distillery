"""`ops chore`: a kb repo's own tooling files are committed by an agent-legal command, and only those."""
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kb.ops import core

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB": "", "KB_ROOT": "", "KB_NO_PUSH": "1"}


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class OpsChore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        write(self.root, "kb.toml", '[kb]\nid = "x"\n')
        write(self.root, "CLAUDE.md", "one\n")
        write(self.root, "wiki/a.md", "---\ntype: idea\n---\n\n# A\n")
        g(self.root, "init", "-q", "-b", "main")
        g(self.root, "config", "user.name", "t")
        g(self.root, "config", "user.email", "t@t")
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "init")
        p = patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)
        lint = patch.object(core, "run_lint")                  # the temp kb.toml is not a full kb; lint has its own tests
        self.lint = lint.start()
        self.addCleanup(lint.stop)

    def chore(self, *a, **k):
        return core.chore(*a, root=self.root, **k)

    def test_it_commits_only_tooling_files_with_the_chore_subject(self):
        write(self.root, "kb.toml", '[kb]\nid = "x"\ntemplate = "t"\n')
        write(self.root, "CLAUDE.md", "two\n")
        write(self.root, "wiki/a.md", "---\ntype: idea\n---\n\n# A, edited\n")      # knowledge: must stay dirty
        self.assertTrue(self.chore("schema", "follow the template"))
        self.assertEqual(g(self.root, "log", "--format=%s", "-1").strip(), "chore(schema): follow the template")
        self.assertEqual(sorted(g(self.root, "show", "--name-only", "--format=", "HEAD").split()), ["CLAUDE.md", "kb.toml"])
        self.assertEqual(g(self.root, "status", "--porcelain", "-uno").strip(), "M wiki/a.md")

    def test_paths_narrow_the_commit(self):
        write(self.root, "kb.toml", '[kb]\nid = "y"\n')
        write(self.root, "CLAUDE.md", "two\n")
        self.chore("hooks", "claude notes", paths=["CLAUDE.md"])
        self.assertEqual(g(self.root, "show", "--name-only", "--format=", "HEAD").split(), ["CLAUDE.md"])
        self.assertEqual(g(self.root, "status", "--porcelain", "-uno").strip(), "M kb.toml")

    def test_a_kb_toml_that_fails_lint_is_not_committed(self):
        self.lint.side_effect = core.OpsError("lint failed - nothing committed")
        write(self.root, "kb.toml", '[kb]\nid = "broken"\n')
        with self.assertRaises(core.OpsError):
            self.chore("schema", "bad")
        self.assertEqual(g(self.root, "rev-list", "--count", "HEAD").strip(), "1")

    def test_lint_runs_only_when_kb_toml_is_in_the_commit(self):
        write(self.root, "CLAUDE.md", "two\n")
        self.chore("hooks", "notes")
        self.lint.assert_not_called()

    def test_a_knowledge_path_is_refused(self):
        write(self.root, "wiki/a.md", "x\n")
        with self.assertRaises(core.OpsError):
            self.chore("schema", "nope", paths=["wiki/a.md"])

    def test_nothing_to_commit_returns_none(self):
        self.assertIsNone(self.chore("schema", "nothing"))
        self.assertEqual(g(self.root, "rev-list", "--count", "HEAD").strip(), "1")

    def test_off_main_is_refused(self):
        g(self.root, "checkout", "-q", "-b", "topic")
        write(self.root, "CLAUDE.md", "two\n")
        with self.assertRaises(core.OpsError):
            self.chore("schema", "x")

    def test_a_folder_that_is_not_a_kb_repo_is_refused(self):
        os.remove(os.path.join(self.root, "kb.toml"))
        with self.assertRaises(core.OpsError):
            self.chore("schema", "x")


if __name__ == "__main__":
    unittest.main()

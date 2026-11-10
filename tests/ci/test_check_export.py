"""scripts/check-export.sh on a tiny temp repo: passes when the owner-only paths are export-ignored and the archive is
clean, fails when one leaks or the archive holds a token-shaped string. No network, no real terms."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "check-export.sh")
ATTRS = "CLAUDE.md export-ignore\n.claude export-ignore\n.claude/** export-ignore\ndocs/archive/** export-ignore\n"


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "needs git and bash")
class CheckExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = tempfile.mkdtemp(dir=self.tmp)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")

    def put(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def run_script(self, terms=""):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "x")
        env = {"PATH": os.environ["PATH"], "HOME": self.home, "PYTHON": sys.executable, "KB_PRIVACY_TERMS": terms}
        return subprocess.run(["bash", SCRIPT, self.repo], capture_output=True, text=True, env=env)

    def base(self):
        self.put(".gitattributes", ATTRS)
        self.put("CLAUDE.md", "owner notes\n")
        self.put(".claude/settings.json", "{}\n")
        self.put("README.md", "hello\n")

    def test_clean_repo_passes(self):
        self.base()
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("check-export: ok", r.stdout)
        self.assertIn("skipping the term check", r.stdout)

    def test_unmarked_owner_path_fails(self):
        self.base()
        self.put(".gitattributes", "CLAUDE.md export-ignore\n")
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".claude is not export-ignored", r.stderr)
        self.assertIn(".claude is in the archive", r.stderr)

    def test_token_in_archive_fails(self):
        self.base()
        self.put("src/a.py", "KEY = 'ghp_" + "a" * 24 + "'\n")
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("src/a.py", r.stderr)

    def test_configured_term_fails_and_ignored_path_is_not_scanned(self):
        self.base()
        self.put("docs/archive/old.md", "owner octocat-private\n")
        self.put("docs/guide.md", "written by octocat-private\n")
        r = self.run_script(terms="octocat-private")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/guide.md", r.stderr)
        self.assertNotIn("docs/archive/old.md", r.stderr)

    def test_baselined_file_is_allowed(self):
        self.base()
        self.put("src/a.py", "KEY = 'ghp_" + "a" * 24 + "'\n")
        self.put("tests/lint/privacy_baseline.txt", "src/a.py\n")
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

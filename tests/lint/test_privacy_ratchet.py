"""No new file may carry personal strings, and the list of old ones only shrinks (see kb_distillery.lint.privacy)."""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from kb_distillery.lint import privacy

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privacy_baseline.txt")


def baseline():
    with open(BASELINE, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip() and not l.startswith("#")}


class PrivacyRatchet(unittest.TestCase):
    def test_a_new_file_must_not_carry_personal_strings(self):
        new = sorted(set(privacy.scan()) - baseline())
        self.assertEqual(new, [], "these files name the owner, a local path, the private host or a token-shaped "
                                  "string: use configuration or a placeholder, not the literal (kb_distillery.lint.privacy)")

    def test_a_cleaned_file_leaves_the_baseline(self):
        if not privacy.load_terms():
            self.skipTest("no personal terms configured (KB_PRIVACY_TERMS or ~/.config/kb-distillery/privacy.toml): "
                          "whether a listed file still matches cannot be judged")
        stale = sorted(baseline() - set(privacy.scan()))
        self.assertEqual(stale, [], "these files no longer match: delete them from "
                                    "tests/lint/privacy_baseline.txt so the list keeps shrinking")


class Scanner(unittest.TestCase):
    def put(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def test_it_flags_each_kind_and_skips_knowledge_and_build_output(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a.py", 'HOME = "/Users/jdoe/x"\n')
            self.put(root, "b.md", "see https://kb.jane-doe-x.workers.dev/x\n")
            self.put(root, "generic.md", "any account: https://kb.acme.workers.dev/x\n")      # Cloudflare's domain alone is fine
            self.put(root, "c.toml", 'key = "sk-ant-api03-' + "A" * 20 + '"\n')
            self.put(root, "clean.py", "x = 1\n")
            self.put(root, "kbs/thesis/wiki/n.md", "/Users/jdoe\n")                 # knowledge: never scanned
            self.put(root, "src/kb_distillery/_webapp/app.js", "jane-doe\n")                         # build output
            self.put(root, ".gitattributes", "docs/archive/** export-ignore\n")
            self.put(root, "docs/archive/p.md", "jane-doe\n")                          # export-ignored history may name the owner
            self.put(root, ".claude/worktrees/w/a.py", "jane-doe\n")                   # another checkout, not this repo's files
            self.assertEqual(sorted(privacy.scan(root, terms=["/Users/jdoe", "jane-doe"])), ["a.py", "b.md", "c.toml"])

    def test_what_ships_is_scanned_including_dot_folders(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, ".claude/skills/s/SKILL.md", "jane-doe\n")
            self.put(root, ".github/workflows/ci.yml", "owner: jane-doe\n")
            self.put(root, "docs/guide.md", "jane-doe\n")
            self.assertEqual(sorted(privacy.scan(root, terms=["jane-doe"])),
                             [".claude/skills/s/SKILL.md", ".github/workflows/ci.yml", "docs/guide.md"])

    def test_this_repos_maintainer_history_is_export_ignored_and_nothing_else_is_exempt(self):
        root = privacy.repo_root()
        self.assertIn("docs/archive", privacy.export_ignored(root))
        if privacy.tracked(root) is None:
            self.skipTest("not a git checkout")
        out = subprocess.run(["git", "-C", root, "check-attr", "export-ignore", "docs/archive/plans/README.md", "docs/ROADMAP.md"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("docs/archive/plans/README.md: export-ignore: set", out)
        self.assertIn("docs/ROADMAP.md: export-ignore: unspecified", out)

    def test_configured_terms_are_found_case_insensitively_and_others_are_not(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a.py", "owner = 'Jane.Doe'\n")
            self.put(root, "b.md", "visit https://kb.acme-secret.workers.dev\n")
            self.put(root, "c.md", "nothing here\n")
            self.assertEqual(sorted(privacy.scan(root, terms=["jane.doe", "acme-secret"])), ["a.py", "b.md"])
            self.assertEqual(privacy.scan(root, terms=["other"]), {})

    def test_a_term_is_plain_text_not_a_pattern(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a.py", "x = 'a+b'\n")
            self.put(root, "b.py", "x = 'aab'\n")
            self.assertEqual(sorted(privacy.scan(root, terms=["a+b"])), ["a.py"])

    def test_without_terms_only_token_shapes_match(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a.py", 'HOME = "/Users/someone"\n')
            self.put(root, "c.toml", 'key = "sk-ant-api03-' + "A" * 20 + '"\n')
            self.assertEqual(sorted(privacy.scan(root, terms=[])), ["c.toml"])


    def test_a_binary_or_unknown_extension_is_not_read(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "img.png", "jane-doe\n")
            self.assertEqual(privacy.scan(root, terms=["jane-doe"]), {})


class Terms(unittest.TestCase):
    def home(self, text=None):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        if text is not None:
            os.makedirs(os.path.join(d.name, ".config", "kb-distillery"))
            with open(os.path.join(d.name, ".config", "kb-distillery", "privacy.toml"), "w") as f:
                f.write(text)
        return mock.patch.dict(os.environ, {"HOME": d.name, "KB_PRIVACY_TERMS": ""})

    def test_the_default_is_empty(self):
        with self.home():
            self.assertEqual(privacy.load_terms(), [])
            self.assertIsNone(privacy.personal_pattern())

    def test_the_env_list_takes_commas_or_pipes_and_beats_the_file(self):
        with self.home('terms = ["from-file"]\n'):
            self.assertEqual(privacy.load_terms(), ["from-file"])
            with mock.patch.dict(os.environ, {"KB_PRIVACY_TERMS": " one, two|three ,, "}):
                self.assertEqual(privacy.load_terms(), ["one", "three", "two"])

    def test_the_file_is_read_when_the_env_is_empty_and_a_broken_file_means_no_terms(self):
        with self.home('terms = ["a", " b ", ""]\n'):
            self.assertEqual(privacy.load_terms(), ["a", "b"])
        with self.home("terms = [broken"):
            self.assertEqual(privacy.load_terms(), [])

    def test_scan_uses_the_configured_terms_by_default(self):
        with tempfile.TemporaryDirectory() as root, self.home():
            path = os.path.join(root, "a.py")
            with open(path, "w") as f:
                f.write("who = 'zed-example'\n")
            self.assertEqual(privacy.scan(root), {})
            with mock.patch.dict(os.environ, {"KB_PRIVACY_TERMS": "zed-example"}):
                self.assertEqual(privacy.scan(root), {"a.py": 1})




if __name__ == "__main__":
    unittest.main()

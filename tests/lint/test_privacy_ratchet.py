"""No new file may carry personal strings, and the list of old ones only shrinks (see kb_distillery.lint.privacy)."""
import os
import tempfile
import unittest

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
            self.put(root, "a.py", 'HOME = "/Users/yonatanm/x"\n')
            self.put(root, "b.md", "see https://kb.yonatan-magen-x.workers.dev/x\n")
            self.put(root, "generic.md", "any account: https://kb.acme.workers.dev/x\n")      # Cloudflare's domain alone is fine
            self.put(root, "c.toml", 'key = "sk-ant-api03-' + "A" * 20 + '"\n')
            self.put(root, "clean.py", "x = 1\n")
            self.put(root, "kbs/thesis/wiki/n.md", "/Users/yonatanm\n")                 # knowledge: never scanned
            self.put(root, "src/kb_distillery/_webapp/app.js", "yonatanm\n")                         # build output
            self.put(root, "docs/plans/p.md", "yonatanm\n")                             # plans name the owner on purpose
            self.assertEqual(sorted(privacy.scan(root)), ["a.py", "b.md", "c.toml"])

    def test_a_binary_or_unknown_extension_is_not_read(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "img.png", "yonatanm\n")
            self.assertEqual(privacy.scan(root), {})


if __name__ == "__main__":
    unittest.main()

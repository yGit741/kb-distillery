"""examples/demo: the public demo knowledge base the engine repo itself tracks."""
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config import kb as kbconfig

CHECKOUT = kbconfig.checkout_root()
DEMO = os.path.join(CHECKOUT, "examples", "demo")
GENERATED = ("meta/corpus.tsv", "meta/coherence-warnings.tsv")


def _lint(root):
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT", "KB_BASES_DIR", "KB_CI")}
    env["PYTHONPATH"] = os.path.join(CHECKOUT, "src")
    return subprocess.run([sys.executable, "-m", "kb_distillery.lint.lint", "--kb", root], cwd=CHECKOUT, env=env,
                          capture_output=True, text=True, check=False)


class DemoKb(unittest.TestCase):
    def test_discovered_by_id_in_the_kbs_folder(self):
        with patch.dict(os.environ, {"KB_BASES_DIR": os.path.join(CHECKOUT, "examples")}):
            self.assertEqual(kbconfig.discover().get("demo"), os.path.realpath(DEMO))

    def test_loads_with_the_folder_name_as_id(self):
        cfg = kbconfig.load(DEMO)
        self.assertEqual(cfg.id, "demo")
        self.assertEqual(cfg.id, os.path.basename(DEMO))
        self.assertEqual(cfg.schema_version, kbconfig.SCHEMA_VERSION)
        self.assertIsNone(cfg.git_root)           # tracked by the engine repo, not a repo of its own

    def test_lints_clean_and_leaves_its_tracked_files_as_they_are(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "demo")
            shutil.copytree(DEMO, copy, ignore=shutil.ignore_patterns(".cache"))
            cp = _lint(copy)
            self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
            self.assertIn("0 errors", cp.stdout)
            from kb_distillery.vault import wikiindex
            indexes = wikiindex.index_files(DEMO)
            self.assertGreater(len(indexes), 1)                      # the root and its section indexes
            self.assertEqual(sorted(wikiindex.index_files(copy)), sorted(indexes))
            for rel in (*GENERATED, *indexes):
                self.assertTrue(filecmp.cmp(os.path.join(DEMO, rel), os.path.join(copy, rel), shallow=False),
                                f"lint rewrote {rel}: commit the regenerated file")


class DemoIsPublicSafe(unittest.TestCase):
    """What git would hold of examples/demo: no caches, tokens, personal paths or addresses."""

    @classmethod
    def setUpClass(cls):
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "examples/demo"],
                             cwd=CHECKOUT, capture_output=True, text=True, check=False).stdout
        cls.files = [f for f in out.split("\0") if f]

    def test_something_is_tracked_and_the_cv_pdf_is_among_it(self):
        self.assertGreater(len(self.files), 20)
        self.assertIn("examples/demo/raw/printed-docs/dana-levi-cv.pdf", self.files)

    def test_no_caches_or_local_state(self):
        bad = [f for f in self.files if re.search(r"(^|/)(\.cache|\.obsidian|\.claude|\.trash|node_modules)(/|$)", f)]
        self.assertEqual(bad, [])

    def test_no_personal_strings_or_secrets_in_the_text_files(self):
        pattern = re.compile(r"/Users/|yonatan|mobileye|gh[ps]_[A-Za-z0-9]{20}|api[_-]?key|BEGIN [A-Z ]*PRIVATE|"
                             r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.(com|org|net|io)", re.I)
        hits = []
        for rel in self.files:
            if rel.endswith(".pdf") or not os.path.isfile(os.path.join(CHECKOUT, rel)):      # a file deleted in the work tree holds nothing to leak
                continue
            with open(os.path.join(CHECKOUT, rel), encoding="utf-8", errors="ignore") as f:
                if pattern.search(f.read()):
                    hits.append(rel)
        self.assertEqual(hits, [])


class LintGate(unittest.TestCase):
    def test_gate_lints_this_checkouts_demo_when_it_has_one(self):
        from kb_distillery.git import ship
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ship.lint_command(tmp)[-2:], ["-m", "kb_distillery.lint.lint"])
            os.makedirs(os.path.join(tmp, "examples", "demo"))
            self.assertEqual(ship.lint_command(tmp)[-2:], ["--kb", os.path.join(tmp, "examples", "demo")])


if __name__ == "__main__":
    unittest.main()

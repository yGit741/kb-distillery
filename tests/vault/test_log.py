"""kb_distillery.vault.log — the one writer of wiki/log.md (OKF shape: `## date` days newest first, `### op | summary` entries)."""
import datetime
import os
import tempfile
import unittest

from kb_distillery.vault import log as kblog


class LogAppendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.path = os.path.join(self.root, "wiki", "log.md")

    def text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_ingest_format_is_byte_for_byte(self):
        kblog.append(self.root, "ingest", "paper-x", ("raw/printed-docs/x.pdf",), when="2026-10-22T01:02:03Z")
        self.assertEqual(self.text(), "# Log\n\n## 2026-10-22\n\n### ingest | paper-x ← `raw/printed-docs/x.pdf`\n")

    def test_summary_only_format(self):
        kblog.append(self.root, "distill", "think/a.md (cleanup) — 2 proposal(s) applied",
                     when=datetime.date(2026, 10, 22))
        self.assertTrue(self.text().endswith("\n### distill | think/a.md (cleanup) — 2 proposal(s) applied\n"))

    def test_creates_missing_file_and_dir(self):
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(kblog.append(self.root, "refine", "split", when="2026-10-22"))
        self.assertTrue(self.text().startswith("# Log\n"))

    def test_appends_to_existing_file_without_trailing_newline(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("# Log")
        kblog.append(self.root, "refine", "a", when="2026-10-22")
        self.assertEqual(self.text(), "# Log\n\n## 2026-10-22\n\n### refine | a\n")

    def test_idempotent_per_op_summary_targets_date(self):
        args = (self.root, "refine", "split", ("a",))
        self.assertTrue(kblog.append(*args, when="2026-10-22"))
        self.assertFalse(kblog.append(*args, when="2026-10-22"))
        self.assertEqual(self.text().count("refine | split"), 1)
        self.assertTrue(kblog.append(*args, when="2026-10-23"))        # another day
        self.assertTrue(kblog.append(self.root, "refine", "split", ("b",), when="2026-10-22"))  # other target
        self.assertEqual(self.text().count("refine | split"), 3)

    def test_date_defaults_to_today(self):
        kblog.append(self.root, "refine", "a")
        self.assertIn(f"## {datetime.date.today().isoformat()}\n\n### refine | a", self.text())

    def test_days_newest_first_and_entries_newest_first(self):
        kblog.append(self.root, "refine", "a", when="2026-10-22")
        kblog.append(self.root, "refine", "c", when="2026-10-24")
        kblog.append(self.root, "refine", "b", when="2026-10-22")
        kblog.append(self.root, "refine", "mid", when="2026-10-23")
        self.assertEqual(self.text(), "# Log\n\n## 2026-10-24\n\n### refine | c\n\n## 2026-10-23\n\n### refine | mid\n\n"
                         "## 2026-10-22\n\n### refine | b\n\n### refine | a\n")

    def test_entry_bodies_survive_an_append(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("# Log\n\n## 2026-10-22\n\n### ingest | a\n\n- body line\n- another\n")
        kblog.append(self.root, "refine", "b", when="2026-10-22")
        self.assertEqual(self.text(), "# Log\n\n## 2026-10-22\n\n### refine | b\n\n### ingest | a\n\n- body line\n- another\n")

    def test_no_frontmatter(self):
        kblog.append(self.root, "refine", "a", when="2026-10-22")
        self.assertFalse(self.text().startswith("---"))

    def test_latest_skips_targeted_entries_on_request(self):
        kblog.append(self.root, "refine", "plain", when="2026-10-22")
        kblog.append(self.root, "ingest", "paper-x", ("raw/x.pdf",), when="2026-10-22")
        self.assertEqual(kblog.latest(self.text()), ("2026-10-22", "ingest | paper-x ← `raw/x.pdf`"))
        self.assertEqual(kblog.latest(self.text(), skip_targeted=True), ("2026-10-22", "refine | plain"))

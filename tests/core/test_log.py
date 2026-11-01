"""kb_distillery.core.log — the one writer of meta/log.md."""
import datetime
import os
import tempfile
import unittest

from kb_distillery.core import log as kblog


class LogAppendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.path = os.path.join(self.root, "meta", "log.md")

    def text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_ingest_format_is_byte_for_byte(self):
        kblog.append(self.root, "ingest", "paper-x", ("raw/printed-docs/x.pdf",), when="2026-10-22T01:02:03Z")
        self.assertEqual(self.text(), "# Log\n\n## [2026-10-22] ingest | paper-x ← `raw/printed-docs/x.pdf`\n")

    def test_summary_only_format(self):
        kblog.append(self.root, "distill", "think/a.md (cleanup) — 2 proposal(s) applied",
                     when=datetime.date(2026, 10, 22))
        self.assertTrue(self.text().endswith("\n## [2026-10-22] distill | think/a.md (cleanup) — 2 proposal(s) applied\n"))

    def test_creates_missing_file_and_dir(self):
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(kblog.append(self.root, "refine", "split", when="2026-10-22"))
        self.assertTrue(self.text().startswith("# Log\n"))

    def test_appends_to_existing_file_without_trailing_newline(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("# Log")
        kblog.append(self.root, "refine", "a", when="2026-10-22")
        self.assertEqual(self.text(), "# Log\n\n## [2026-10-22] refine | a\n")

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
        self.assertIn(f"## [{datetime.date.today().isoformat()}] refine | a", self.text())

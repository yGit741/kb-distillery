"""0015_okf_index_log: index.md and log.md move into the bundle root wiki/, the log in OKF shape, history kept."""
import importlib.util
import os
import tempfile
import unittest

from kb_distillery.core import log as kblog
from kb_distillery.ops import migrate
from kb_distillery.paths import MIGRATIONS_CODE_PATH

spec = importlib.util.spec_from_file_location("m0015", os.path.join(MIGRATIONS_CODE_PATH, "0015_okf_index_log.py"))
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

LEGACY = (
    "---\ntype: meta\n---\n\n# Wiki log\n\nAppend-only activity timeline. Prefix: `## [YYYY-MM-DD] action | title`\n\n"
    "## [2026-08-07] setup | Karpathy alignment\n\n- first bullet\n- second bullet\n\n"
    "## [2026-08-07] ingest | paper-a ← `raw/printed-docs/a.pdf`\n\n"
    "## [2026-08-13] refine | split x\n\nfree text\n\n"
    "## [2026-08-07] ingest | paper-a ← `raw/printed-docs/a.pdf`\n"      # the same line again, a day later in the file
)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", newline="") as f:
        return f.read()


class OkfIndexLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "kb.toml", '[kb]\nid = "t"\nname = "T"\nschema_version = "1.6"\n')
        write(self.root, "wiki/a.md", "---\ntype: idea\n---\n# A\n")
        write(self.root, "index.md", "---\ntype: meta\n---\n\n# Wiki index\n\n| [[a]] | x |\n")
        write(self.root, "meta/log.md", LEGACY)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_log_moves_into_okf_shape_with_every_entry(self):
        rep = mig.apply(self.root)
        got = read(self.root, "wiki/log.md")
        self.assertFalse(os.path.exists(os.path.join(self.root, "meta", "log.md")))
        self.assertTrue(got.startswith("# Log\n\n## 2026-08-13\n"))             # no frontmatter, newest day first
        self.assertEqual(got, "# Log\n\n"
                         "## 2026-08-13\n\n### refine | split x\n\nfree text\n\n"
                         "## 2026-08-07\n\n### ingest | paper-a ← `raw/printed-docs/a.pdf`\n\n"
                         "### ingest | paper-a ← `raw/printed-docs/a.pdf`\n\n"        # equal entries are both kept
                         "### setup | Karpathy alignment\n\n- first bullet\n- second bullet\n")
        self.assertEqual((rep["entries"], rep["days"]), (4, 2))
        self.assertEqual(rep["preamble_dropped"], 5)                            # the frontmatter block (3 lines), title, intro
        self.assertEqual(sum(len(b) for _d, b in kblog.parse(got)), 4)

    def test_the_root_index_is_removed_and_nothing_recreates_it(self):
        rep = mig.apply(self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "index.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki", "index.md")))      # lint writes it, not the migration
        self.assertTrue(rep["index_removed"])
        mig.apply(self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "index.md")))

    def test_idempotent_second_run_changes_nothing(self):
        mig.apply(self.root)
        before = read(self.root, "wiki/log.md")
        rep = mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/log.md"), before)
        self.assertEqual((rep["log_moved"], rep["index_removed"], rep["wrote"]), (False, False, []))

    def test_dry_run_writes_nothing_and_reports(self):
        rep = mig.apply(self.root, dry_run=True)
        self.assertEqual((rep["entries"], rep["index_removed"]), (4, True))
        self.assertEqual(read(self.root, "meta/log.md"), LEGACY)
        self.assertTrue(os.path.exists(os.path.join(self.root, "index.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki", "log.md")))

    def test_an_existing_wiki_log_is_merged_not_overwritten(self):
        write(self.root, "wiki/log.md", "# Log\n\n## 2026-08-13\n\n### refine | newer\n\n## 2026-09-01\n\n### ingest | later\n")
        rep = mig.apply(self.root)
        got = read(self.root, "wiki/log.md")
        self.assertTrue(rep["merged_into_existing"])
        self.assertEqual([d for d, _b in kblog.parse(got)], ["2026-09-01", "2026-08-13", "2026-08-07"])
        self.assertIn("### refine | newer\n\n### refine | split x", got)         # what was already there stays above
        self.assertEqual(rep["entries"], 6)
        again = mig.apply(self.root)                                              # a partial rerun adds no duplicate
        self.assertEqual(read(self.root, "wiki/log.md"), got)
        self.assertFalse(again["log_moved"])

    def test_a_partial_move_is_finished_without_duplicates(self):
        """wiki/log.md written but meta/log.md still there (a crash between the two steps): the rerun completes it."""
        mig.apply(self.root)
        done = read(self.root, "wiki/log.md")
        write(self.root, "meta/log.md", LEGACY)
        mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/log.md"), done)

    def test_a_heading_inside_an_entry_body_cannot_become_an_entry(self):
        write(self.root, "meta/log.md", "# Log\n\n## [2026-08-07] x | y\n\n### inner\n\ntext\n")
        rep = mig.apply(self.root)
        self.assertEqual(rep["demoted_headings"], 1)
        self.assertEqual(rep["entries"], 1)
        self.assertIn("#### inner", read(self.root, "wiki/log.md"))

    def test_nothing_to_move_is_a_noop(self):
        os.remove(os.path.join(self.root, "meta", "log.md"))
        os.remove(os.path.join(self.root, "index.md"))
        rep = mig.apply(self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki", "log.md")))      # never invented
        self.assertEqual((rep["log_moved"], rep["index_removed"]), (False, False))

    def test_a_kb_without_a_wiki_folder_is_handled(self):
        os.remove(os.path.join(self.root, "wiki", "a.md"))
        os.rmdir(os.path.join(self.root, "wiki"))
        mig.apply(self.root)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "wiki", "log.md")))

    def test_runs_through_the_migrate_machinery_and_is_recorded(self):
        ids = migrate._apply(self.root, ["0015_okf_index_log"])
        self.assertEqual(ids, ["0015_okf_index_log"])
        self.assertIn("0015_okf_index_log\t", read(self.root, "meta/migrations/applied.tsv"))
        self.assertEqual(mig.PRODUCES, (1, 7))
        self.assertNotIn("0015_okf_index_log", migrate.pending_migrations(self.root))


if __name__ == "__main__":
    unittest.main()

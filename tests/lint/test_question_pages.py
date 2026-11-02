"""Question pages (schema 1.1): H1 <= 80 chars (error; > 60 warns), `## Question` required."""
import importlib.util
import os
import shutil
import tempfile
import unittest

from kb_distillery.lint import lint
from kb_distillery.paths import MIGRATIONS_CODE_PATH

FM = "---\ntype: question\nlayer: concept\nmaturity: open\n---\n"
SHORT = "Is the jump a sharp threshold?"
MID = "Is every abrupt jump in task success a sharp threshold of a monotone event?"
LONG = "Is every abrupt jump in task success, as a scale parameter grows, a sharp threshold of a monotone event?"


def page(h1, body="\n## Question\n\nThe formal statement.\n\n## My notes\n"):
    return f"{FM}\n# {h1}\n{body}"


class QuestionPageLint(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-lint-q-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "wiki"))
        self.old = lint.ROOT
        lint.ROOT = self.root
        self.addCleanup(setattr, lint, "ROOT", self.old)

    def run_lint(self, slug, text):
        with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        lint.errors.clear()
        lint.warnings.clear()
        lint.check_wiki()
        mine = lambda xs: [x for x in xs if f"{slug}.md" in x]
        return mine(lint.errors), mine(lint.warnings)

    def test_short_title_with_question_section_is_clean(self):
        errs, warns = self.run_lint("q-a", page(SHORT))
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

    def test_title_over_60_warns_and_names_the_section(self):
        self.assertGreater(len(MID), 60)
        self.assertLessEqual(len(MID), 80)
        errs, warns = self.run_lint("q-b", page(MID))
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 1)
        self.assertIn("## Question", warns[0])
        self.assertIn("name", warns[0])

    def test_title_over_80_errors_once(self):
        self.assertGreater(len(LONG), 80)
        errs, warns = self.run_lint("q-c", page(LONG))
        self.assertEqual(len(errs), 1)
        self.assertIn("max 80", errs[0])
        self.assertEqual(warns, [], "an error is not doubled by the warning")

    def test_missing_question_section_errors(self):
        errs, _ = self.run_lint("q-d", page(SHORT, body="\n**Question:** old inline form\n\n## My notes\n"))
        self.assertEqual(len(errs), 1)
        self.assertIn("## Question", errs[0])

    def test_rules_apply_to_questions_only(self):
        errs, warns = self.run_lint("x", f"---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# {LONG}\n")
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])


class QuestionTitleMigration(unittest.TestCase):
    def setUp(self):
        path = os.path.join(MIGRATIONS_CODE_PATH, "0009_question_title.py")
        spec = importlib.util.spec_from_file_location("m0009", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.root = tempfile.mkdtemp(prefix="kb-mig-q-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "wiki"))

    def w(self, name, text):
        with open(os.path.join(self.root, "wiki", name), "w", encoding="utf-8") as f:
            f.write(text)

    def snapshot(self):
        d = os.path.join(self.root, "wiki")
        return {n: open(os.path.join(d, n), encoding="utf-8").read() for n in os.listdir(d)}

    def test_inserts_question_section_reports_long_titles_idempotently(self):
        self.w("q-long.md", page(LONG, body="\n**Question:** x\n\n## My notes\n"))
        self.w("q-ok.md", page(SHORT))
        self.w("idea.md", f"---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# {LONG}\n")
        before = self.snapshot()
        r = self.mod.apply(self.root)
        self.assertEqual(r["pages"], 2)
        self.assertEqual([s for s, _ in r["long_title"]], ["q-long"])
        self.assertEqual(r["missing_question"], ["q-long"])
        after = self.snapshot()
        self.assertEqual(after["q-ok.md"], before["q-ok.md"])
        self.assertEqual(after["idea.md"], before["idea.md"])
        self.assertEqual(after["q-long.md"],
                         f"{FM}\n# {LONG}\n\n## Question\n\n{LONG}\n\n**Question:** x\n\n## My notes\n")
        self.assertEqual(after["q-long.md"].split("\n---\n")[0], before["q-long.md"].split("\n---\n")[0])
        r2 = self.mod.apply(self.root)                                  # idempotent
        self.assertEqual(r2["missing_question"], [])
        self.assertEqual(self.snapshot(), after)

    def test_produces_the_current_schema(self):
        from kb_distillery.core.schema import SCHEMA_VERSION
        self.assertLessEqual(tuple(self.mod.PRODUCES), tuple(SCHEMA_VERSION))   # later migrations may follow


if __name__ == "__main__":
    unittest.main()

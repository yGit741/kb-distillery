"""description: (schema 1.3 as `summary:`): malformed → error, missing → one aggregated warning, stale → warning."""
import os
import shutil
import tempfile
import unittest

from kb_distillery.core.summary import summary_hash
from kb_distillery.lint import lint

GOOD = "An idea page arguing that norm-based capacity bounds, not raw parameter counts, explain generalization."
BODY = "\n# An idea\n\nLead.\n\n## My notes\n"


def page(extra=""):
    return f"---\ntype: idea\nlayer: concept\nmaturity: seed\n{extra}---\n{BODY}"


class SummaryLint(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-lint-s-")
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
        return ([e for e in lint.errors if "description" in e],
                [w for w in lint.warnings if "description" in w])

    def test_fresh_summary_is_clean(self):
        h = summary_hash(page())
        errs, warns = self.run_lint("a", page(f'description: "{GOOD}"\nsummary_from: {h}\n'))
        self.assertEqual((errs, warns), ([], []))

    def test_missing_is_one_aggregated_warning(self):
        errs, warns = self.run_lint("a", page())
        self.assertEqual(errs, [])
        self.assertEqual(len([w for w in warns if "have no description" in w]), 1)

    def test_malformed_is_error(self):
        errs, _ = self.run_lint("a", page('description: "too short"\n'))
        self.assertTrue(errs)

    def test_stale_warns_unless_mine(self):
        _, warns = self.run_lint("a", page(f'description: "{GOOD}"\nsummary_from: 000000000000\n'))
        self.assertTrue(any("stale" in w for w in warns))
        _, warns = self.run_lint("a", page(f'description: "{GOOD}"\ngenerated: {{by: human:ada}}\n'))
        self.assertFalse(any("stale" in w for w in warns))

"""Schema 1.5 lint: maturity replaces status, OKF `status` is only `draft` at depth listed, generated / created / sources /
related have their OKF shapes, the retired keys are named, title vs the first heading warns."""
import os
import shutil
import tempfile
import unittest

from kb_distillery.lint import lint

BODY = "\n# An idea\n\nLead.\n\n## My notes\n"


def page(extra="", maturity="maturity: seed\n"):
    return f"---\ntype: idea\nlayer: concept\n{maturity}{extra}---\n{BODY}"


class OkfFields(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-lint-okf-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "wiki"))
        self.old = lint.ROOT
        lint.ROOT = self.root
        self.addCleanup(setattr, lint, "ROOT", self.old)

    def run_lint(self, text, slug="a"):
        with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        lint.errors.clear()
        lint.warnings.clear()
        lint.check_wiki()
        return list(lint.errors), list(lint.warnings)

    def test_clean_page(self):
        errs, warns = self.run_lint(page('title: "An idea"\ncreated: 2026-10-08T00:00:00Z\n'
                                         'generated: {by: human:ada, at: 2026-10-08T10:00:00+03:00}\n'
                                         'sources: [{resource: b.md}, {resource: "think:n.md"}]\nrelated: [b.md]\n'))
        self.assertEqual(errs, [])
        self.assertFalse([w for w in warns if "title" in w])

    def test_status_is_the_old_reading_status(self):
        errs, _ = self.run_lint(page(maturity="status: seed\n"))
        self.assertTrue(any("maturity:" in e for e in errs) and any("OKF `status`" in e for e in errs))

    def test_draft_status_only_at_depth_listed(self):
        errs, _ = self.run_lint(page("status: draft\n"))
        self.assertTrue(any("OKF `status`" in e for e in errs))

    def test_shapes(self):
        for extra, needle in [("generated: {at: 2026-10-08T10:00:00Z}\n", "generated:"),
                              ("generated: {by: ada}\n", "generated:"),
                              ("created: 2026-10-08\n", "created:"),
                              ("sources: [b]\n", "sources:"),
                              ("related: [b]\n", "related:")]:
            errs, _ = self.run_lint(page(extra))
            self.assertTrue(any(needle in e for e in errs), extra)

    def test_retired_keys_name_their_replacement(self):
        errs, _ = self.run_lint(page('summary: "x"\nsummary_by: me\ndate: 2026-10-08\n'))
        for old, new in (("summary", "description"), ("summary_by", "generated"), ("date", "created")):
            self.assertTrue(any(f"`{old}:` is retired" in e and new in e for e in errs), old)

    def test_title_must_follow_the_first_heading(self):
        _, warns = self.run_lint(page('title: "Another"\n'))
        self.assertTrue(any("differs from the first heading" in w for w in warns))

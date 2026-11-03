#!/usr/bin/env python3
"""okf-check parity: okf_check.py and its TypeScript port (web/src/lib/okf/checkBundle.ts) give one verdict.

Every case in tests/fixtures/okf-bundles/<case>/ is a bundle (`bundle/`, mounted as the kb's `wiki/`) and the report both
checkers must produce (`expected.json`: pages, errors, warnings). This test runs okf_check on each; checkBundle.test.ts runs
the port on the same files against the same JSON, so a rule changed on one side fails the other until it follows.

To add a case: put the files under `<case>/bundle/`, run `OKF_PARITY_WRITE=1 pytest tests/lint/test_okf_check_parity.py`,
read the new expected.json and commit it. The write mode only creates a missing file; a changed rule has to be reviewed by
deleting the old expected.json on purpose.
"""
import json
import os
import shutil
import tempfile
import unittest

from kb_distillery.lint import okf_check

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "okf-bundles")
RULES = {"type", "status", "sources", "timestamp", "wikilink", "link", "boundary", "read"}
NO_PAGES = "the bundle has no pages (no .md files besides index.md / log.md)"


def cases():
    return sorted(n for n in os.listdir(FIXTURES) if os.path.isdir(os.path.join(FIXTURES, n)))


def report(case):
    """What the import preview shows for the bundle: the same lines `distill kb import` builds from okf_check."""
    root = tempfile.mkdtemp(prefix="kb-okf-parity-")
    try:
        shutil.copytree(os.path.join(FIXTURES, case, "bundle"), os.path.join(root, "wiki"))
        findings, count = okf_check.check(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    errors = [f"{rel}: [{rule}] {msg}" for rel, items in sorted(findings.items()) for rule, msg in items]
    if not count and not errors:
        errors.append(NO_PAGES)
    return {"pages": count, "errors": errors, "warnings": []}


def expected(case):
    with open(os.path.join(FIXTURES, case, "expected.json"), encoding="utf-8") as f:
        return json.load(f)


class OkfParity(unittest.TestCase):
    def test_every_case_has_an_expected_report(self):
        self.assertTrue(cases())
        for case in cases():
            if os.environ.get("OKF_PARITY_WRITE") and not os.path.exists(os.path.join(FIXTURES, case, "expected.json")):
                with open(os.path.join(FIXTURES, case, "expected.json"), "w", encoding="utf-8") as f:
                    json.dump(report(case), f, indent=2, ensure_ascii=False)
                    f.write("\n")
            self.assertTrue(os.path.isfile(os.path.join(FIXTURES, case, "bundle", "..", "expected.json")), case)
            self.assertTrue(os.path.isdir(os.path.join(FIXTURES, case, "bundle")), case)

    def test_okf_check_matches_the_expected_reports(self):
        for case in cases():
            with self.subTest(case=case):
                self.assertEqual(report(case), expected(case))

    def test_the_cases_cover_every_rule(self):
        seen = {line.split("]")[0].split("[")[-1] for case in cases() for line in expected(case)["errors"]}
        self.assertEqual(RULES - seen, set())
        self.assertTrue(any(not expected(case)["errors"] for case in cases()), "no good bundle")


if __name__ == "__main__":
    unittest.main()

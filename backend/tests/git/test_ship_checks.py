"""Lane -> checks gate of `ship pr` / `ship merge` (no LLM; subprocess mocked)."""
import subprocess
import unittest
from unittest.mock import patch

from kb.git import ship


def _cp(code=0, out=""):
    return subprocess.CompletedProcess([], code, stdout=out, stderr="")


def names(paths):
    return [n for n, _ in ship.checks_for(paths)]


class ChecksForTests(unittest.TestCase):
    def test_backend_only_runs_nothing(self):
        self.assertEqual(names(["backend/src/kb/git/ship.py", "wiki/x.md"]), [])

    def test_frontend(self):
        self.assertEqual(names(["frontend/src/App.tsx"]), ["web-check"])

    def test_api_router(self):
        self.assertEqual(names(["backend/src/kb/api/routers/x.py"]), ["api-schema-check"])

    def test_dashboard(self):
        self.assertEqual(names(["backend/src/kb/dashboard/graph.html"]), ["test-e2e"])

    def test_frontend_api_runs_both(self):
        self.assertEqual(names(["frontend/src/api/schema.d.ts"]), ["web-check", "api-schema-check"])


class RunChecksTests(unittest.TestCase):
    def test_backend_only_spawns_nothing(self):
        with patch.object(ship.subprocess, "run") as run:
            self.assertTrue(ship.run_checks(paths=["backend/src/kb/git/ship.py"]))
            run.assert_not_called()

    def test_stale_schema_fails(self):
        with patch.object(ship.subprocess, "run", return_value=_cp(1, "schema.d.ts is stale")) as run:
            self.assertFalse(ship.run_checks(paths=["backend/src/kb/api/app.py"]))
            self.assertEqual(run.call_args.args[0], ["pixi", "run", "api-schema-check"])

    def test_passing_check(self):
        with patch.object(ship.subprocess, "run", return_value=_cp(0)):
            self.assertTrue(ship.run_checks(paths=["frontend/src/a.ts"]))

    def test_skip_reason_bypasses(self):
        with patch.object(ship.subprocess, "run") as run:
            self.assertTrue(ship.run_checks(skip_reason="flaky", paths=["frontend/src/a.ts"]))
            run.assert_not_called()

    def test_e2e_skipped_without_playwright(self):
        with patch.object(ship, "e2e_available", return_value=False), \
                patch.object(ship.subprocess, "run") as run:
            self.assertTrue(ship.run_checks(paths=["backend/src/kb/dashboard/x.html"]))
            run.assert_not_called()

    def test_pr_body_records_skip(self):
        self.assertIn("flaky", ship.pr_body(["chore(x): y"], skipped_checks="flaky"))


if __name__ == "__main__":
    unittest.main()

"""release.yml structure: runs on v* tags only, pushes to GHCR only on a tag, PyPI job present but off, minimal permissions."""
import re
import unittest

from tests.ci.test_workflows import load, steps, triggers

ALLOWED_WRITE = {"contents", "packages"}
TAG_ONLY = "startsWith(github.ref, 'refs/tags/v')"


class ReleaseWorkflow(unittest.TestCase):
    def setUp(self):
        self.wf = load("release.yml")

    def uses(self, prefix):
        return next(s for _, s in steps(self.wf) if s.get("uses", "").startswith(prefix))

    def test_triggers_only_on_v_tags(self):
        t = triggers(self.wf)
        self.assertEqual(set(t), {"push"})
        self.assertEqual(t["push"], {"tags": ["v*"]})

    def test_web_bundle_no_longer_races_it_on_tags(self):
        self.assertNotIn("push", triggers(load("web-bundle.yml")))

    def test_permissions_are_minimal(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        for name, job in self.wf["jobs"].items():
            for scope in (job.get("permissions") or {}):
                self.assertIn(scope, ALLOWED_WRITE, f"{name}: permission {scope}")
        self.assertEqual(self.wf["jobs"]["release"]["permissions"], {"contents": "write"})
        self.assertEqual(self.wf["jobs"]["docker"]["permissions"], {"contents": "read", "packages": "write"})
        self.assertNotIn("permissions", self.wf["jobs"]["pypi"])

    def test_ghcr_push_only_on_a_tag_multi_arch_from_the_dockerfile(self):
        w = self.uses("docker/build-push-action@")["with"]
        self.assertEqual(w["platforms"], "linux/amd64,linux/arm64")
        self.assertEqual(w["file"], "./Dockerfile")
        self.assertIn(TAG_ONLY, w["push"])
        self.assertEqual(self.uses("docker/metadata-action@")["with"]["images"], "ghcr.io/${{ github.repository }}")
        login = self.uses("docker/login-action@")
        self.assertEqual(login["with"]["registry"], "ghcr.io")
        self.assertIn(TAG_ONLY, login["if"])

    def test_pypi_job_is_present_but_disabled(self):
        pypi = self.wf["jobs"]["pypi"]
        self.assertIs(pypi["if"], False)
        self.assertTrue(any(s.get("uses", "").startswith("pypa/gh-action-pypi-publish@") for s in pypi["steps"]))

    def test_job_order_gates_then_build_then_release_then_image(self):
        jobs = self.wf["jobs"]
        self.assertEqual(jobs["build"]["needs"], "gates")
        self.assertEqual(jobs["release"]["needs"], "build")
        self.assertEqual(jobs["docker"]["needs"], "release")

    def test_notes_come_from_the_changelog_and_gates_run_the_ci_tasks(self):
        text = "\n".join(s.get("run", "") for _, s in steps(self.wf))
        self.assertIn("kb_distillery.git.release --notes", text)
        self.assertIn("--notes-file", text)
        for task in ("lint-skills", "lint-imports", "ruff", "web-check", "test-wheel", "build-wheel"):
            self.assertRegex(text, rf"pixi run {re.escape(task)}\b")


if __name__ == "__main__":
    unittest.main()

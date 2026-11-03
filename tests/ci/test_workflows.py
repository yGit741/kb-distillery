"""The GitHub workflows parse, pin what they use and never echo or deploy with a secret (they cannot be run here)."""
import os
import re
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, ".github", "workflows")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$")     # a version tag or a full commit sha
DEPLOY = re.compile(r"deploy|publish|wrangler|share\s+--", re.I)
LEAK = re.compile(r"\becho\b.*\$\{\{\s*secrets\.|\bprintenv\b|\bset\s+-x\b|^\s*env\s*$|secrets\.\w+.*\|\s*(tee|cat)", re.I | re.M)


def load(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def workflows():
    return sorted(n for n in os.listdir(DIR) if n.endswith((".yml", ".yaml")))


def triggers(wf):
    return wf.get("on", wf.get(True))        # YAML 1.1 reads the bare key `on` as the boolean True


def steps(wf):
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            yield job_name, step


class WorkflowShape(unittest.TestCase):
    def test_there_are_workflows(self):
        self.assertTrue({"ci.yml", "secret-scan.yml"} <= set(workflows()))

    def test_each_has_triggers_and_jobs_with_steps(self):
        for name in workflows():
            wf = load(name)
            self.assertIsNotNone(triggers(wf), f"{name}: no `on`")
            self.assertTrue(wf.get("jobs"), f"{name}: no `jobs`")
            for job_name, job in wf["jobs"].items():
                self.assertTrue(job.get("runs-on"), f"{name}/{job_name}: no runs-on")
                self.assertTrue(job.get("steps"), f"{name}/{job_name}: no steps")
                for step in job["steps"]:
                    self.assertTrue("uses" in step or "run" in step, f"{name}/{job_name}: a step with neither uses nor run")

    def test_every_action_is_pinned_to_a_tag_or_sha(self):
        for name in workflows():
            for job, step in steps(load(name)):
                if "uses" in step:
                    self.assertRegex(step["uses"], PINNED, f"{name}/{job}: `{step['uses']}` is not pinned to a tag or sha")

    def test_no_secret_is_echoed_or_interpolated_into_a_script(self):
        for name in workflows():
            for job, step in steps(load(name)):
                script = step.get("run", "")
                self.assertNotRegex(script, LEAK, f"{name}/{job}: a step may print a secret")
                self.assertNotIn("secrets.", script, f"{name}/{job}: pass secrets through `env:`, not into the script text")


PR_TRIGGERS = {"pull_request", "pull_request_target"}
GITHUB_HOSTED = re.compile(r"^(ubuntu|macos|windows)-(latest|\d+(\.\d+)?(-arm64|-xlarge|-large)?)$")
# the only self-hosted runner a job may name: picked while the repo is private, GitHub-hosted once it is public
BY_VISIBILITY = ("${{ github.event.repository.private && fromJSON('[\"self-hosted\",\"macOS\",\"ARM64\"]') || 'macos-latest' }}")


def runs_on_is_safe_for_forks(runs_on) -> bool:
    """True when a job can only land on a self-hosted runner while the repo is private."""
    return runs_on == BY_VISIBILITY or (isinstance(runs_on, str) and bool(GITHUB_HOSTED.match(runs_on)))


class RunnerSafety(unittest.TestCase):
    def test_no_pull_request_job_can_use_self_hosted_when_the_repo_is_public(self):
        checked = 0
        for name in workflows():
            wf = load(name)
            if not PR_TRIGGERS & set(triggers(wf) or ()):
                continue
            for job_name, job in wf["jobs"].items():
                checked += 1
                self.assertTrue(runs_on_is_safe_for_forks(job["runs-on"]),
                                f"{name}/{job_name}: runs-on {job['runs-on']!r} may reach a self-hosted runner from a fork pull request; "
                                "use the visibility expression or a GitHub-hosted label")
        self.assertGreaterEqual(checked, 5)       # ci.yml (4 jobs) + secret-scan.yml

    def test_the_guard_itself_rejects_self_hosted_labels(self):
        for bad in (["self-hosted", "macOS", "ARM64"], "self-hosted", ["macos-latest"],
                    "${{ fromJSON('[\"self-hosted\"]') }}", "${{ github.event.repository.private || 'macos-latest' }}"):
            self.assertFalse(runs_on_is_safe_for_forks(bad), bad)
        for good in ("ubuntu-latest", "macos-latest", "macos-14", BY_VISIBILITY):
            self.assertTrue(runs_on_is_safe_for_forks(good), good)

    def test_deploy_main_never_runs_on_pull_requests(self):
        wf = load("deploy-main.yml")
        self.assertFalse(PR_TRIGGERS & set(triggers(wf)), "deploy-main (self-hosted, holds deploy credentials) must not run on pull requests")
        self.assertTrue(set(triggers(wf)) <= {"push", "schedule", "workflow_dispatch"}, set(triggers(wf)))


class PushAndPullRequestChecks(unittest.TestCase):
    def test_ci_runs_on_push_and_pull_request_and_keeps_kb_ci(self):
        wf = load("ci.yml")
        self.assertTrue({"push", "pull_request"} <= set(triggers(wf)))
        self.assertEqual(set(wf["jobs"]), {"python", "web", "wheel", "worker"})
        for name, job in wf["jobs"].items():
            self.assertEqual(job["runs-on"], BY_VISIBILITY, name)       # self-hosted while private (free minutes), GitHub-hosted once public
        job = wf["jobs"]["python"]
        self.assertEqual(str(job["env"]["KB_CI"]), "1")
        runs = [s["run"] for s in job["steps"] if "run" in s]
        self.assertIn("pixi run test", runs)
        self.assertTrue(any("test_privacy_ratchet" in r for r in runs))
        for name, task in (("web", "pixi run web-check"), ("wheel", "pixi run test-wheel"), ("worker", "pixi run test-worker")):
            self.assertIn(task, [s["run"] for s in wf["jobs"][name]["steps"] if "run" in s], name)

    def test_secret_scan_runs_gitleaks_on_push_and_pull_request(self):
        wf = load("secret-scan.yml")
        self.assertTrue({"push", "pull_request"} <= set(triggers(wf)))
        uses = [s["uses"] for _, s in steps(wf) if "uses" in s]
        self.assertTrue(any(u.startswith("gitleaks/gitleaks-action@v") for u in uses))
        checkout = next(s for _, s in steps(wf) if s.get("uses", "").startswith("actions/checkout"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)               # the whole history, not just the tip
        self.assertEqual(wf["permissions"], {"contents": "read"})

    def test_the_check_workflows_never_deploy_or_publish(self):
        for name in ("ci.yml", "secret-scan.yml"):
            for job, step in steps(load(name)):
                self.assertNotRegex(step.get("run", ""), DEPLOY, f"{name}/{job}: a check must not deploy or publish")


if __name__ == "__main__":
    unittest.main()

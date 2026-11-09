"""The GitHub workflows parse, pin what they use, run only on GitHub-hosted runners, gate every pull request and
merge-queue group through one fan-in check (`all-green`), cover every tests/ dir in exactly one pytest shard, and never
echo or deploy with a secret (they cannot be run here)."""
import os
import re
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, ".github", "workflows")
TESTS = os.path.join(ROOT, "tests")
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


def runs(job):
    return [s["run"] for s in job["steps"] if "run" in s]


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


PR_TRIGGERS = {"pull_request", "pull_request_target", "merge_group"}
GITHUB_HOSTED = re.compile(r"^(ubuntu|macos|windows)-(latest|\d+(\.\d+)?(-arm64|-xlarge|-large)?)$")


def runs_on_is_safe_for_forks(runs_on) -> bool:
    """True only for a plain GitHub-hosted label: a fork's pull request must never reach a self-hosted machine."""
    return isinstance(runs_on, str) and bool(GITHUB_HOSTED.match(runs_on))


class RunnerSafety(unittest.TestCase):
    def test_no_pull_request_job_can_use_self_hosted(self):
        checked = 0
        for name in workflows():
            wf = load(name)
            if not PR_TRIGGERS & set(triggers(wf) or ()):
                continue
            for job_name, job in wf["jobs"].items():
                checked += 1
                self.assertTrue(runs_on_is_safe_for_forks(job["runs-on"]),
                                f"{name}/{job_name}: runs-on {job['runs-on']!r} may reach a self-hosted runner from a fork pull request; "
                                "use a GitHub-hosted label")
        self.assertGreaterEqual(checked, 7)       # ci.yml (6 jobs) + secret-scan.yml

    def test_the_guard_itself_rejects_self_hosted_labels_and_expressions(self):
        for bad in (["self-hosted", "macOS", "ARM64"], "self-hosted", ["macos-latest"],
                    "${{ fromJSON('[\"self-hosted\"]') }}", "${{ github.event.repository.private || 'macos-latest' }}",
                    "${{ github.event.repository.private && fromJSON('[\"self-hosted\",\"macOS\",\"ARM64\"]') || 'macos-latest' }}"):
            self.assertFalse(runs_on_is_safe_for_forks(bad), bad)
        for good in ("ubuntu-latest", "macos-latest", "macos-14"):
            self.assertTrue(runs_on_is_safe_for_forks(good), good)

    @unittest.skipUnless(os.path.isfile(os.path.join(DIR, "deploy-main.yml")), "owner workflow: export-ignored from the public repo")
    def test_deploy_main_never_runs_on_pull_requests(self):
        wf = load("deploy-main.yml")
        self.assertFalse(PR_TRIGGERS & set(triggers(wf)), "deploy-main (self-hosted, holds deploy credentials) must not run on pull requests")
        self.assertTrue(set(triggers(wf)) <= {"push", "schedule", "workflow_dispatch"}, set(triggers(wf)))


CI_JOBS = {"lint", "tests", "web", "checks", "wheel", "worker", "all-green"}
LANE_CHECKS = ("pixi run api-schema-check", "pixi run flags-check", "pixi run test-e2e", "pixi run test-ui-principles")
LINT_TASKS = ("pixi run lint-skills", "pixi run licenses", "pixi run lint-imports", "pixi run lint", "pixi run okf-check", "pixi run ruff")


SERIAL_MARK = re.compile(r"@pytest\.mark\.serial\b")


def tested_dirs():
    """Every tests/<dir> that holds a test_*.py somewhere below it (fixtures, testdata and the node e2e dir do not)."""
    out = set()
    for d in sorted(os.listdir(TESTS)):
        path = os.path.join(TESTS, d)
        if not os.path.isdir(path):
            continue
        for _, _, files in os.walk(path):
            if any(f.startswith("test_") and f.endswith(".py") for f in files):
                out.add(f"tests/{d}")
                break
    return out


def shard_dirs(paths):
    """The tests/<dir> set a shard's pytest arguments cover: listed dirs, or everything under `tests` minus its --ignore=s."""
    tokens = paths.split()
    ignored = {t[len("--ignore="):] for t in tokens if t.startswith("--ignore=")}
    covered = set()
    for root in (t for t in tokens if not t.startswith("--")):
        covered |= tested_dirs() - ignored if root == "tests" else {root}
    return covered


def serial_files():
    """Test files that carry `pytest.mark.serial`, relative to the repo root."""
    out = []
    for dirpath, _, files in os.walk(TESTS):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8") as fh:
                    if SERIAL_MARK.search(fh.read()):
                        out.append(os.path.relpath(path, ROOT))
    return out


class CiGates(unittest.TestCase):
    """ci.yml is the gate: it runs on every pull request and merge-queue group and `all-green` is the one required check."""

    def setUp(self):
        self.wf = load("ci.yml")
        self.jobs = self.wf["jobs"]

    def test_runs_on_pull_requests_merge_groups_and_pushes_to_main_only(self):
        on = triggers(self.wf)
        self.assertTrue({"pull_request", "merge_group", "workflow_dispatch"} <= set(on), set(on))
        self.assertEqual(on["push"], {"branches": ["main"]})       # a PR branch push runs CI once (the pull_request event), not twice

    def test_jobs_and_runners(self):
        self.assertEqual(set(self.jobs), CI_JOBS)
        for name, job in self.jobs.items():
            self.assertEqual(job["runs-on"], "ubuntu-latest", name)
        for name in ("lint", "tests", "web"):
            self.assertEqual(str(self.jobs[name]["env"]["KB_CI"]), "1", name)

    def test_lint_job_runs_every_cheap_gate(self):
        lint = runs(self.jobs["lint"])
        for task in LINT_TASKS:
            self.assertTrue(any(r == task or r.startswith(task + " ") for r in lint), f"{task} missing from the lint job: {lint}")
        for task in ("pixi run lint", "pixi run okf-check"):       # a runner has no kb selected: lint the demo kb, as the ship gate does
            self.assertTrue(any(r.startswith(task + " -- --kb examples/demo") for r in lint), lint)
        self.assertTrue(any("test_privacy_ratchet" in r for r in lint))

    def test_pytest_shards_cover_every_tests_dir_exactly_once(self):
        includes = self.jobs["tests"]["strategy"]["matrix"]["include"]
        owner = {}
        for inc in includes:
            for d in shard_dirs(inc["paths"]):
                self.assertNotIn(d, owner, f"{d} is in shard {owner.get(d)} and in shard {inc['shard']}")
                owner[d] = inc["shard"]
        self.assertEqual(set(owner), tested_dirs(), "every tests/<dir> with tests belongs to exactly one shard")
        # one shard starts at `tests` itself, so the top-level tests/test_*.py invariants run too
        self.assertEqual(sum(inc["paths"].split()[0] == "tests" for inc in includes), 1)
        self.assertFalse(self.jobs["tests"]["strategy"].get("fail-fast", True), "a red shard must not cancel the others")

    def test_shards_run_in_parallel_and_the_serial_pass_where_its_tests_live(self):
        tests = runs(self.jobs["tests"])
        self.assertTrue(any("-n auto" in r and '-m "not serial"' in r and "${{ matrix.paths }}" in r for r in tests), tests)
        self.assertTrue(any("-m serial" in r and "${{ matrix.serial }}" in r for r in tests), tests)
        serial_roots = [inc["serial"] for inc in self.jobs["tests"]["strategy"]["matrix"]["include"] if inc.get("serial")]
        self.assertTrue(serial_files(), "the suite has a `serial` test; this check needs one")
        for path in serial_files():
            self.assertTrue(any(path.startswith(root.rstrip("/") + "/") for root in serial_roots),
                            f"{path} carries mark.serial but no shard runs the serial pass over it: {serial_roots}")

    def test_all_green_fans_in_every_job(self):
        job = self.jobs["all-green"]
        self.assertEqual(set(job["needs"]), CI_JOBS - {"all-green"})
        self.assertEqual(str(job["if"]).strip(), "always()")            # it reports even when a needed job failed
        self.assertTrue(any("success" in r for r in runs(job)))         # and goes red unless every result is success

    def test_a_merge_group_run_is_never_cancelled(self):
        c = self.wf["concurrency"]
        self.assertIn("github.ref", c["group"])
        self.assertIn("github.event_name", c["group"])                 # a main push and a merge group never share a group
        self.assertIsNot(c["cancel-in-progress"], True)
        self.assertIn("pull_request", str(c["cancel-in-progress"]))     # only a newer push to the same PR cancels

    def test_web_wheel_and_worker_tasks(self):
        for name, task in (("web", "pixi run web-check"), ("wheel", "pixi run test-wheel"), ("worker", "pixi run test-worker")):
            self.assertIn(task, runs(self.jobs[name]), name)

    def test_web_check_is_skipped_only_on_a_pull_request_without_app_changes(self):
        """A Python-only PR need not pay the Vite build; a merge-group run (the real merge) and a main push always do."""
        steps_ = self.jobs["web"]["steps"]
        gate = next(s for s in steps_ if s.get("id") == "app")
        self.assertIn("github.event_name }}\" = \"pull_request\"", gate["run"])
        self.assertIn("git diff --quiet", gate["run"])
        self.assertIn("web/", gate["run"])
        for task in ("pixi run web-install", "pixi run web-check"):
            step = next(s for s in steps_ if s.get("run") == task)
            self.assertEqual(step["if"], "steps.app.outputs.skip != '1'", task)

    def test_the_lane_checks_ship_no_longer_runs_locally_run_in_ci(self):
        """`ship pr` stopped running checks_for's lanes locally (CI is the gate): every one of them is a CI step."""
        checks = runs(self.jobs["checks"])
        for task in LANE_CHECKS:
            self.assertTrue(any(task in r for r in checks), f"{task} missing from the checks job: {checks}")
        self.assertIn("pixi run web-build", checks)                                                           # the browser suites serve the built app
        # the e2e suites join index.mjs to $PLAYWRIGHT_MODULE (a package dir) and skip when it is missing: a skip must fail the job
        self.assertTrue(self.jobs["checks"]["env"]["PLAYWRIGHT_MODULE"].endswith("node_modules/playwright"))
        for suite in ("test-e2e", "test-ui-principles"):
            step = next(r for r in checks if f"pixi run {suite}" in r)
            self.assertIn("skip", step, f"{suite}: a skipped suite must fail the step")


class SecretScan(unittest.TestCase):
    def test_secret_scan_runs_gitleaks_on_push_and_pull_request(self):
        wf = load("secret-scan.yml")
        self.assertTrue({"push", "pull_request"} <= set(triggers(wf)))
        uses = [s["uses"] for _, s in steps(wf) if "uses" in s]
        self.assertTrue(any(u.startswith("gitleaks/gitleaks-action@v") for u in uses))
        checkout = next(s for _, s in steps(wf) if s.get("uses", "").startswith("actions/checkout"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)               # the whole history, not just the tip
        self.assertEqual(wf["permissions"], {"contents": "read", "pull-requests": "read"})   # read-only; the action lists PR commits

    def test_the_check_workflows_never_deploy_or_publish(self):
        for name in ("ci.yml", "secret-scan.yml"):
            for job, step in steps(load(name)):
                self.assertNotRegex(step.get("run", ""), DEPLOY, f"{name}/{job}: a check must not deploy or publish")


if __name__ == "__main__":
    unittest.main()

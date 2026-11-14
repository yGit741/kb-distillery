"""The GitHub workflows parse, pin what they use, run only on GitHub-hosted runners, gate every pull request and
merge-queue group through one fan-in check (`all-green`), cover every tests/ dir in exactly one pytest shard, and never
echo or deploy with a secret (they cannot be run here)."""
import json
import os
import re
import subprocess
import tempfile
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
        self.assertGreaterEqual(checked, 7)       # ci.yml (7 jobs) + secret-scan.yml

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
        self.assertFalse(PR_TRIGGERS & set(triggers(wf)), "deploy-main (holds deploy credentials) must not run on pull requests")
        self.assertTrue(set(triggers(wf)) <= {"push", "schedule", "workflow_dispatch"}, set(triggers(wf)))
        deploy = next(s for _, s in steps(wf) if str(s.get("name", "")).startswith("Build main and deploy"))
        self.assertIn("github.ref == 'refs/heads/main'", deploy["if"])      # a dispatch from another branch never deploys it


CI_JOBS = {"changes", "lint", "tests", "web", "checks", "wheel", "worker", "docker", "install-linux", "install-macos",
           "all-green"}
MACOS_JOBS = {"install-macos"}     # macOS is a supported platform: the installer runs on it, the suite nightly
PLATFORM_JOBS = {"docker": "docker", "install-macos": "macos"}     # job -> its `changes` output; skipped on a PR that touches none of its files
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
            self.assertEqual(job["runs-on"], "macos-latest" if name in MACOS_JOBS else "ubuntu-latest", name)
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

    def all_green(self, event, **results):
        """Run the fan-in step as the runner does, with every job a success except `results`; True when it is green."""
        needs = {name: {"result": "success"} for name in CI_JOBS - {"all-green"}}
        needs.update({name.replace("_", "-"): {"result": r} for name, r in results.items()})
        step = self.jobs["all-green"]["steps"][-1]
        self.assertIn("toJSON(needs)", step["env"]["NEEDS"])
        cp = subprocess.run(["bash", "-c", step["run"]], env={**os.environ, "NEEDS": json.dumps(needs), "EVENT": event},
                            capture_output=True, text=True, check=False)
        return cp.returncode == 0

    def test_all_green_accepts_a_skip_only_for_the_platform_jobs_on_a_pull_request(self):
        self.assertTrue(self.all_green("pull_request"))
        self.assertTrue(self.all_green("pull_request", docker="skipped", install_macos="skipped"))
        for event in ("merge_group", "push", "workflow_dispatch"):       # the real merge always runs them
            self.assertTrue(self.all_green(event))
            self.assertFalse(self.all_green(event, docker="skipped"), event)
            self.assertFalse(self.all_green(event, install_macos="skipped"), event)
        for job in ("lint", "tests", "web", "checks", "wheel", "worker", "install_linux", "changes"):
            self.assertFalse(self.all_green("pull_request", **{job: "skipped"}), job)
        for bad in ("failure", "cancelled"):
            self.assertFalse(self.all_green("pull_request", docker=bad), bad)
            self.assertFalse(self.all_green("pull_request", tests=bad), bad)

    def test_the_platform_jobs_run_on_a_pull_request_only_when_it_touches_their_files(self):
        changes = self.jobs["changes"]
        script = "\n".join(runs(changes))
        self.assertIn('[ "$EVENT" != pull_request ] ||', script)        # any other event runs both
        self.assertIn("git diff --quiet", script)
        lines = {out: next(l for l in script.split("\n") if l.strip().startswith("if touched") and marker in l)
                 for out, marker in (("docker", "Dockerfile"), ("macos", "install.sh"))}
        for path in ("Dockerfile", ".dockerignore", ".github/scripts/docker-smoke.sh"):
            self.assertIn(path, lines["docker"])
        for out, line in lines.items():                                 # the dependency files and the workflow reach both
            for path in (".github/workflows/ci.yml", "pyproject.toml", "pixi.toml", "pixi.lock"):
                self.assertIn(path, line, out)
            self.assertIn(f'echo "{out}=1" >> "$GITHUB_OUTPUT"', script)
        for job, out in PLATFORM_JOBS.items():
            self.assertEqual(self.jobs[job]["needs"], "changes", job)
            self.assertEqual(self.jobs[job]["if"], f"needs.changes.outputs.{out} == '1'", job)
            self.assertEqual(changes["outputs"][out], "${{ steps.diff.outputs.%s }}" % out)
        for name, job in self.jobs.items():                             # no other job may be skipped as a whole
            if name not in PLATFORM_JOBS and name != "all-green":
                self.assertNotIn("if", job, name)

    def test_the_changes_job_reads_the_diff_of_a_real_repository(self):
        """The `touched` helper, run as the runner does: a PR that edits only Python skips both, install.sh wakes macOS only."""
        script = "\n".join(runs(self.jobs["changes"]))
        with tempfile.TemporaryDirectory() as d:
            def git(*args):
                subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)

            def outputs(event, *edited):
                git("checkout", "-q", "-B", "pr", "origin/main")
                for rel in edited:
                    with open(os.path.join(d, rel), "a") as f:
                        f.write("x\n")
                if edited:
                    git("add", "-A")
                    git("commit", "-q", "-m", "edit")
                out = os.path.join(d, ".out")
                open(out, "w").close()
                subprocess.run(["bash", "-e", "-c", script], cwd=d, check=True, capture_output=True,
                               env={**os.environ, "EVENT": event, "BASE": "main", "GITHUB_OUTPUT": out})
                with open(out) as f:
                    return set(f.read().split())

            git("init", "-q", "-b", "main")
            for rel in ("Dockerfile", "install.sh", "pixi.lock", "a.py"):
                with open(os.path.join(d, rel), "w") as f:
                    f.write("x\n")
            with open(os.path.join(d, ".gitignore"), "w") as f:
                f.write(".out\n")
            git("add", "-A")
            git("commit", "-q", "-m", "init")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            self.assertEqual(outputs("pull_request", "a.py"), set())
            self.assertEqual(outputs("pull_request", "install.sh"), {"macos=1"})
            self.assertEqual(outputs("pull_request", "Dockerfile"), {"docker=1"})
            self.assertEqual(outputs("pull_request", "pixi.lock"), {"docker=1", "macos=1"})
            for event in ("merge_group", "push", "workflow_dispatch"):
                self.assertEqual(outputs(event), {"docker=1", "macos=1"}, event)

    def test_the_docker_job_waits_for_the_image_to_be_healthy(self):
        self.assertIn(".github/scripts/docker-smoke.sh kb-distillery:ci", runs(self.jobs["docker"]))
        script = open(os.path.join(ROOT, ".github", "scripts", "docker-smoke.sh")).read()
        self.assertIn('wait_for "$UP" healthy', script)
        self.assertIn('wait_for "$DOWN" unhealthy', script)     # a down server must turn the check red

    def test_the_installer_runs_on_macos_and_linux(self):
        for name in ("install-linux", "install-macos"):
            self.assertTrue(any(r.startswith("./install.sh --no-open") for r in runs(self.jobs[name])), name)

    def test_the_suite_runs_nightly_on_both_macs_and_the_arm64_image_is_checked(self):
        wf = load("platforms-nightly.yml")
        self.assertFalse(PR_TRIGGERS & set(triggers(wf)), "the slow platform checks stay off pull requests")
        self.assertEqual(wf["jobs"]["tests-macos"]["runs-on"], "macos-latest")
        self.assertEqual(wf["jobs"]["tests-macos-intel"]["runs-on"], "macos-15-intel")
        self.assertIn(".github/scripts/docker-smoke.sh kb-distillery:ci", runs(wf["jobs"]["docker-arm64"]))
        self.assertIn("schedule", triggers(wf))
        arm = wf["jobs"]["docker-arm64"]
        self.assertEqual(arm["needs"], "wheel")                          # the arm64 image installs the wheel built on ubuntu
        upload = next(s for s in wf["jobs"]["wheel"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact"))
        download = next(s for s in arm["steps"] if s.get("uses", "").startswith("actions/download-artifact"))
        self.assertEqual(upload["with"]["name"], download["with"]["name"])
        self.assertEqual(download["with"]["path"], "dist")
        for name, job in wf["jobs"].items():
            self.assertIn("timeout-minutes", job, f"{name}: a hung nightly job must not hold a runner for 6 hours")

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

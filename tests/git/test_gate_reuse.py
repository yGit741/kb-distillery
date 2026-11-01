"""ship gate reuse: a gate that passed on the same content is not rerun; cheap refusals come before any gate."""
import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.git import gate_cache, ship


def _g(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


def _write(root, rel, text="# x"):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "a") as f:
        f.write(text + "\n")


class RepoCase(unittest.TestCase):
    """A tmp repo on infra/gate-demo with three fake gates that count their runs and a lint that rewrites index.md."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = os.path.realpath(self.tmp.name)
        self.root = os.path.join(t, "repo")
        self.counter = os.path.join(t, "runs.txt")
        os.makedirs(self.root)
        _g(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            _g(self.root, "config", k, v)
        _write(self.root, ".gitignore", "__pycache__/\n.pytest_cache/")
        for rel in ("src/kb_distillery/git/a.py", "tests/git/test_a.py", "tests/test_top.py", "tests/conftest.py",
                    "index.md", "examples/demo/index.md", "examples/demo/meta/corpus.tsv", "notes/n.txt"):
            _write(self.root, rel, "def test_ok():\n    pass" if os.path.basename(rel).startswith("test_") else "# x")
        _g(self.root, "add", "-A")
        _g(self.root, "commit", "-q", "-m", "chore: init (retro)")
        _g(self.root, "checkout", "-q", "-b", "infra/gate-demo")
        env = patch.dict(os.environ, {"KB": "kb-one", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.runs_patch = [
            patch.object(ship, "GATES", [(n, self._gate(n)) for n in ("tests", "lint-skills", "lint")]),
            patch.object(ship, "lint_command", lambda root=None: self._gate("lint", regen=True)),
            patch.object(ship, "frontend_changed", lambda root=None: False),
        ]
        for p in self.runs_patch:
            p.start()
            self.addCleanup(p.stop)

    def _gate(self, name, regen=False):
        code = f"open({self.counter!r}, 'a').write({name!r} + '\\n')"
        if regen:   # lint rewrites generated files, the demo kb's too
            code += f"\nopen('index.md', 'a').write('regen\\n')\nopen('examples/demo/index.md', 'a').write('regen\\n')"
        return [sys.executable, "-c", code]

    def runs(self):
        try:
            with open(self.counter) as f:
                return f.read().split()
        except OSError:
            return []

    def gates(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = ship.run_gates(self.root, **kw)
        self.assertTrue(ok, out.getvalue())
        return out.getvalue()


class ReuseTests(RepoCase):
    def test_second_run_on_unchanged_tree_is_reused(self):
        self.gates()
        self.assertEqual(sorted(self.runs()), ["lint", "lint-skills", "tests"])
        out = self.gates()
        self.assertEqual(len(self.runs()), 3)
        for name in ("tests", "lint-skills", "lint"):
            self.assertRegex(out, rf"gate: {name} reused \([0-9a-f]{{7}}\)")

    def test_a_pass_from_another_day_is_not_reused(self):
        self.gates()
        real = gate_cache.time.strftime
        with patch.object(gate_cache.time, "strftime", lambda fmt, *a: "2099-01-01" if fmt == "%Y-%m-%d" else real(fmt, *a)):
            self.gates()
        self.assertEqual(len(self.runs()), 6)

    def test_edit_is_a_miss(self):
        self.gates()
        _write(self.root, "src/kb_distillery/git/a.py", "changed")
        self.gates()
        self.assertEqual(len(self.runs()), 6)

    def test_new_untracked_file_is_a_miss(self):
        self.gates()
        _write(self.root, "src/kb_distillery/git/new.py")
        self.gates()
        self.assertEqual(len(self.runs()), 6)

    def test_gitignored_file_is_not_part_of_the_fingerprint(self):
        _write(self.root, ".gitignore", "junk/")
        self.gates()
        _write(self.root, "junk/big.bin")
        self.gates()
        self.assertEqual(len(self.runs()), 3)

    def test_generated_files_changing_is_a_hit(self):
        self.gates()                                   # the lint gate itself rewrote index.md and the demo's
        _write(self.root, "meta/corpus.tsv", "regenerated")
        _write(self.root, "examples/demo/meta/corpus.tsv", "regenerated")
        _write(self.root, "examples/demo/meta/coherence-warnings.tsv", "regenerated")
        self.gates()
        self.assertEqual(len(self.runs()), 3)

    def test_kb_change_is_a_miss(self):
        self.gates()
        with patch.dict(os.environ, {"KB": "kb-two"}):
            self.gates()
        self.assertEqual(len(self.runs()), 6)

    def test_skip_tests_keeps_todays_behaviour(self):
        self.gates(skip_tests=True)
        self.assertEqual(sorted(self.runs()), ["lint", "lint-skills"])

    def test_same_sha_uncommitted_and_committed(self):
        _write(self.root, "src/kb_distillery/git/a.py", "work")
        before = ship._fingerprint(self.root)
        _g(self.root, "add", "-A")
        _g(self.root, "commit", "-q", "-m", "feat(git): work")
        self.assertEqual(ship._fingerprint(self.root), before)

    def test_a_failing_gate_is_not_recorded(self):
        with patch.object(ship, "GATES", [("tests", [sys.executable, "-c", "raise SystemExit(1)"])]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(ship.run_gates(self.root))
        self.assertFalse(os.path.isdir(os.path.join(self.root, gate_cache.REUSE_DIR)))

    def test_checks_are_reused_too(self):
        out = io.StringIO()
        with patch.object(ship, "checks_for", lambda paths: [("web-check", [sys.executable, "-c", "pass"])]), \
                contextlib.redirect_stdout(out):
            self.assertTrue(ship.run_checks(self.root, paths=["web/a.ts"]))
            self.assertTrue(ship.run_checks(self.root, paths=["web/a.ts"]))
        self.assertIn("check: web-check reused", out.getvalue())


class ScopeTests(RepoCase):
    def touch_git_pkg(self):
        _write(self.root, "src/kb_distillery/git/a.py", "edit")

    def test_subset_pass_is_not_reused_by_a_full_run(self):
        self.touch_git_pkg()                                      # in subset mode the tests gate is a real pytest run
        out = self.gates(scope="subset")
        self.assertIn("tests subset", out)
        self.assertIn("gate: tests ok", out)
        self.assertIn("gate: tests reused", self.gates(scope="subset"))   # a subset run reuses a subset pass
        out = self.gates(scope="full")                            # ... pr/merge do not
        self.assertIn("gate: tests ok", out)
        self.assertIn("gate: lint reused", out)                   # lint has no subset: one pass serves both
        self.assertEqual(self.runs().count("lint"), 1)
        self.assertIn("gate: tests reused", self.gates(scope="full"))     # a full pass is reused by a full run

    def test_unmappable_change_runs_full(self):
        _write(self.root, "pixi.toml")
        out = self.gates(scope="subset")
        self.assertNotIn("tests subset", out)
        self.assertEqual(self.runs().count("tests"), 1)          # the fake (full) tests gate ran
        self.assertIn("gate: tests reused", self.gates(scope="full"))   # and it was recorded as a full pass


class SelectionTests(RepoCase):
    def sel(self, *paths):
        return gate_cache.test_subset(list(paths), self.root)

    def test_mirror_changed_tests_and_top_level_invariants(self):
        _write(self.root, "tests/git/test_new.py")
        got = self.sel("src/kb_distillery/git/ship.py", "tests/git/test_new.py")
        self.assertEqual(got, ["tests/git", "tests/test_top.py"])
        _write(self.root, "tests/lint/test_x.py")
        self.assertEqual(self.sel("tests/lint/test_x.py"), ["tests/lint/test_x.py", "tests/test_top.py"])

    def test_generated_files_do_not_force_a_full_run(self):
        got = gate_cache.test_subset(["src/kb_distillery/git/a.py", "examples/demo/index.md"], self.root,
                                     ignore=ship.is_generated)
        self.assertEqual(got, ["tests/git", "tests/test_top.py"])

    def test_top_level_tests_always_run(self):
        self.assertEqual(self.sel("AGENTS.md"), ["tests/test_top.py"])

    def test_full_fallback_on_config_and_unmappable_changes(self):
        for p in ("pixi.toml", "pyproject.toml", "tests/conftest.py", "tests/git/conftest.py", "pixi.lock",
                  "src/kb_distillery/paths.py", "src/kb_distillery/nomirror/x.py", "tests/fixtures/data.json",
                  "src/kb_distillery/kits/base/skills/x/SKILL.md", ".claude/skills/x/SKILL.md", "web/src/a.ts"):
            self.assertIsNone(self.sel("src/kb_distillery/git/ship.py", p), p)


class RefusalTests(RepoCase):
    def commit(self, msg="feat(git): thing"):
        out = io.StringIO()
        with patch.object(ship, "run_gates", return_value=True) as gates, contextlib.redirect_stdout(out):
            rc = ship.cmd_commit(msg, root=self.root)
        return rc, gates, out.getvalue()

    def test_unrelated_staged_file_refuses_before_any_gate(self):
        _write(self.root, "src/kb_distillery/git/a.py", "mine")
        _write(self.root, "wiki/other.md")
        _g(self.root, "add", "wiki/other.md")
        rc, gates, out = self.commit()
        self.assertEqual(rc, 1)
        self.assertIn("unrelated changes are staged", out)
        gates.assert_not_called()

    def test_nothing_to_commit_before_any_gate(self):
        rc, gates, out = self.commit()
        self.assertEqual(rc, 0)
        self.assertIn("nothing to commit", out)
        gates.assert_not_called()

    def test_a_hand_edit_of_a_demo_page_before_the_gates_is_committed(self):
        _write(self.root, "examples/demo/index.md", "hand edit")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ship.cmd_commit("feat(git): thing", root=self.root), 0)
        self.assertEqual(_g(self.root, "show", "--name-only", "--format=", "HEAD").splitlines(), ["examples/demo/index.md"])

    def test_policy_refusal_before_any_gate(self):
        _write(self.root, "src/kb_distillery/git/a.py", "mine")
        rc, gates, _ = self.commit("not a conventional message")
        self.assertEqual(rc, 1)
        gates.assert_not_called()

    def test_lint_side_effects_never_enter_the_commit_and_pr_reuses_lint(self):
        _write(self.root, "src/kb_distillery/git/a.py", "mine")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ship.cmd_commit("feat(git): thing", root=self.root), 0)
        files = _g(self.root, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertEqual(files, ["src/kb_distillery/git/a.py"])
        self.assertIn("tests subset", out.getvalue())
        # pr: tests reran as a full run, lint and lint-skills were reused (same content, generated files left out)
        out = self.gates(scope="full")
        self.assertIn("gate: tests ok", out)
        self.assertIn("gate: lint reused", out)
        self.assertIn("gate: lint-skills reused", out)


class FingerprintTests(RepoCase):
    def index_state(self):
        with open(os.path.join(self.root, ".git", "index"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    @staticmethod
    def temp_indexes():
        return {n for n in os.listdir(tempfile.gettempdir()) if n.startswith("ship-index-")}

    def test_real_index_is_untouched(self):
        _write(self.root, "staged.py")
        _g(self.root, "add", "staged.py")
        _write(self.root, "untracked.py")
        before, status = self.index_state(), _g(self.root, "status", "--porcelain")
        # a private temp dir: other lanes' runs create ship-index-* in the shared system temp and raced this check
        with tempfile.TemporaryDirectory() as private, patch.object(tempfile, "tempdir", private):
            self.assertEqual(self.temp_indexes(), set())
            self.assertIsNotNone(gate_cache.tree_sha(self.root, ["index.md"]))
            self.assertEqual(self.temp_indexes(), set())      # tree_sha leaves no ship-index-* behind
        self.assertEqual(self.index_state(), before)
        self.assertEqual(_g(self.root, "status", "--porcelain"), status)


class XdistRefusalTests(RepoCase):
    """The tests gate runs with -n: without pytest-xdist in the shared env, refuse before running any gate."""

    def _with_n(self):
        gates = [(n, self._gate(n)) for n in ("tests", "lint-skills", "lint")]
        gates[0] = ("tests", gates[0][1] + ["-n", "6"])      # `python -c <code> -n 6`: runs, extra args ignored
        return patch.object(ship, "GATES", gates)

    def _run(self, spec):
        out = io.StringIO()
        with self._with_n(), patch("importlib.util.find_spec", return_value=spec), contextlib.redirect_stdout(out):
            ok = ship.run_gates(self.root)
        return ok, out.getvalue()

    def test_missing_xdist_refuses_before_any_gate(self):
        ok, out = self._run(None)
        self.assertFalse(ok)
        self.assertIn("pixi install", out)
        self.assertIn("PRIMARY checkout", out)
        self.assertEqual(self.runs(), [])                    # not even lint-skills ran

    def test_xdist_present_runs_the_gates(self):
        ok, out = self._run(object())
        self.assertTrue(ok, out)
        self.assertEqual(sorted(self.runs()), ["lint", "lint-skills", "tests"])

    def test_a_reused_tests_gate_needs_no_xdist(self):
        self._run(object())
        ok, out = self._run(None)
        self.assertTrue(ok, out)
        self.assertIn("gate: tests reused", out)

    def test_mocked_runner_never_hits_the_check(self):
        out = io.StringIO()
        with self._with_n(), patch("importlib.util.find_spec", return_value=None), \
                patch.object(ship, "_REAL_RUN", object()), contextlib.redirect_stdout(out):
            self.assertTrue(ship._xdist_ok(ship.GATES, {"tests": "full"}, {}, self.root, None))
        self.assertNotIn("pixi install", out.getvalue())


class RecordLocationTests(RepoCase):
    def test_records_land_only_under_the_given_root(self):
        real = os.path.join(ship.ROOT, gate_cache.REUSE_DIR)
        before = sorted(os.listdir(real)) if os.path.isdir(real) else None
        self.gates()
        after = sorted(os.listdir(real)) if os.path.isdir(real) else None
        self.assertEqual(before, after)
        mine = os.listdir(os.path.join(self.root, gate_cache.REUSE_DIR))
        self.assertEqual(len(mine), 3)

    def test_a_mocked_runner_records_and_reuses_nothing(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(ship.subprocess, "run", return_value=ok), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(ship.run_gates(self.root))
        self.assertFalse(os.path.isdir(os.path.join(self.root, gate_cache.REUSE_DIR)))

    def test_gate_logs_of_a_tmp_root_stay_in_it(self):
        self.gates()
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".cache", "ship-gates")))


if __name__ == "__main__":
    unittest.main()

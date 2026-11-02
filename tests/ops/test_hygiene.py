#!/usr/bin/env python3
"""Tests for src/kb_distillery/ops/hygiene.py — nightly git/ops hygiene checks — and its hook in ops.core.sync."""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.git import ship
from kb_distillery.ops import core, hygiene

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB_NO_HYGIENE": "1"}
NOW = datetime.datetime(2026, 10, 22, 22, 0, tzinfo=datetime.timezone.utc)


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


def kinds(findings):
    return sorted(f.kind for f in findings)


class Repo(unittest.TestCase):
    """bare remote + clone on main with one pushed commit."""

    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.remote = os.path.join(self.tmp.name, "remote.git")
        self.root = os.path.join(self.tmp.name, "kb")
        g(self.tmp.name, "init", "-q", "--bare", "-b", "main", self.remote)
        g(self.tmp.name, "clone", "-q", self.remote, self.root)
        g(self.root, "config", "user.name", "t")
        g(self.root, "config", "user.email", "t@t")
        self.wt_dir = os.path.join(self.root, ".claude", "worktrees")
        with open(os.path.join(self.root, ".gitignore"), "w") as f:
            f.write(".claude/worktrees/\nmeta/.ops/\nmeta/.ingest/\n.cache/\n")
        self.commit(".", None, "chore(init): first")
        g(self.root, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()

    def commit(self, rel, text, msg, cwd=None):
        cwd = cwd or self.root
        if text is not None:
            full = os.path.join(cwd, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(text + "\n")
        g(cwd, "add", "--", rel)
        g(cwd, "commit", "-q", "-m", msg)

    def worktree(self, name, branch):
        path = os.path.join(self.wt_dir, name)
        os.makedirs(self.wt_dir, exist_ok=True)
        g(self.root, "worktree", "add", "-q", "-b", branch, path, "main")
        g(path, "config", "user.name", "t")
        g(path, "config", "user.email", "t@t")
        return path

    def merge_to_main(self, branch):
        g(self.root, "merge", "-q", "--no-ff", "-m", f"merge {branch} (#1)", branch)
        g(self.root, "push", "-q", "origin", "main")


class WorktreeChecks(Repo):
    def test_merged_worktree_is_stale(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        self.merge_to_main("infra/feat")
        found = hygiene.check_worktrees(self.root, NOW)
        self.assertEqual(kinds(found), ["stale-worktree"])
        self.assertEqual(found[0].fix, hygiene.PRUNE_FIX)
        self.assertIn("infra/feat", found[0].detail)

    def test_merged_but_dirty_worktree_keeps_the_edit_in_the_fix(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        self.merge_to_main("infra/feat")
        with open(os.path.join(path, "meta", "y.py"), "w") as f:
            f.write("y = 2\n")
        found = hygiene.check_worktrees(self.root, NOW)
        self.assertEqual(kinds(found), ["stale-worktree"])
        self.assertIn("1 uncommitted files", found[0].detail)
        self.assertIn(path, found[0].fix)

    def test_live_worktree_with_uncommitted_tooling_is_dirty(self):
        path = self.worktree("live", "infra/live")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)       # ahead of main → live, not stale
        with open(os.path.join(path, "meta", "z.py"), "w") as f:
            f.write("z = 3\n")
        found = hygiene.check_worktrees(self.root, NOW)
        self.assertEqual(kinds(found), ["dirty-worktree"])
        self.assertIn("meta/z.py", found[0].detail)

    def test_generated_files_do_not_make_a_worktree_dirty(self):
        path = self.worktree("live", "infra/live")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        for rel in ("wiki/index.md", "meta/corpus.tsv"):
            os.makedirs(os.path.dirname(os.path.join(path, rel)), exist_ok=True)
            with open(os.path.join(path, rel), "w") as f:
                f.write("generated\n")
        self.assertEqual(hygiene.check_worktrees(self.root, NOW), [])

    def test_session_worktree_branch_is_reported(self):
        path = self.worktree("sess", "worktree-sess")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        found = hygiene.check_worktrees(self.root, NOW)
        self.assertEqual(kinds(found), ["session-worktree"])
        self.assertIn("prune --drop worktree-sess", found[0].fix)

    def test_worktree_gone_from_disk(self):
        import shutil
        path = self.worktree("gone", "infra/gone")
        shutil.rmtree(path)
        self.assertEqual(hygiene.check_worktrees(self.root, NOW), [])      # reported by check_stale instead
        with patch.object(ship, "open_prs", return_value=[]):
            found = hygiene.check_stale(self.root, NOW)
        self.assertEqual(kinds(found), ["missing-worktree"])
        self.assertIn("git worktree prune", found[0].fix)

    def test_clean_repo_has_no_worktree_findings(self):
        self.assertEqual(hygiene.check_worktrees(self.root, NOW), [])


class BranchChecks(Repo):
    def test_merged_local_branch_without_worktree(self):
        g(self.root, "checkout", "-q", "-b", "infra/old")
        self.commit("meta/o.py", "o = 1", "feat(o): old")
        g(self.root, "checkout", "-q", "main")
        self.merge_to_main("infra/old")
        found = hygiene.check_branches(self.root, NOW)
        self.assertEqual([(f.kind, f.fix) for f in found], [("unpruned-branch", hygiene.PRUNE_FIX)])
        self.assertIn("local branch infra/old", found[0].detail)

    def test_merged_remote_branch(self):
        g(self.root, "checkout", "-q", "-b", "infra/pushed")
        self.commit("meta/p.py", "p = 1", "feat(p): pushed")
        g(self.root, "push", "-q", "origin", "infra/pushed")
        g(self.root, "checkout", "-q", "main")
        self.merge_to_main("infra/pushed")
        g(self.root, "branch", "-D", "infra/pushed")
        found = hygiene.check_branches(self.root, NOW)
        self.assertEqual([f.detail for f in found], ["remote branch infra/pushed is already in main"])

    def test_worktree_held_branch_is_left_to_the_worktree_check(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        self.merge_to_main("infra/feat")
        self.assertEqual(hygiene.check_branches(self.root, NOW), [])

    def test_unmerged_branch_is_kept(self):
        g(self.root, "checkout", "-q", "-b", "infra/wip")
        self.commit("meta/w.py", "w = 1", "feat(w): wip")
        g(self.root, "checkout", "-q", "main")
        self.assertEqual(hygiene.check_branches(self.root, NOW), [])


class MainSyncChecks(Repo):
    def test_in_sync(self):
        self.assertEqual(hygiene.check_main_sync(self.root, NOW), [])

    def test_ahead_is_an_error(self):
        self.commit("wiki/a.md", "a", "kb(refine): a (kb-1.0.1)")
        found = hygiene.check_main_sync(self.root, NOW)
        self.assertEqual([(f.severity, f.kind, f.fix) for f in found], [("error", "unpushed-steps", hygiene.SYNC_FIX)])
        self.assertIn("1 commit(s) ahead", found[0].detail)

    def test_behind_is_a_warning(self):
        other = os.path.join(self.tmp.name, "other")
        g(self.tmp.name, "clone", "-q", self.remote, other)
        g(other, "config", "user.name", "t")
        g(other, "config", "user.email", "t@t")
        self.commit("wiki/b.md", "b", "kb(refine): b (kb-1.0.1)", cwd=other)
        g(other, "push", "-q", "origin", "main")
        g(self.root, "fetch", "-q", "origin")
        found = hygiene.check_main_sync(self.root, NOW)
        self.assertEqual([(f.severity, f.kind) for f in found], [("warn", "behind-origin")])

    def test_no_origin_main_is_silent(self):
        g(self.root, "remote", "remove", "origin")
        self.assertEqual(hygiene.check_main_sync(self.root, NOW), [])


class SessionChecks(Repo):
    def _session(self, rel, data):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            json.dump(data, f)

    def test_old_ingest_distill_ops_and_researcher_sessions(self):
        old = (NOW - datetime.timedelta(hours=30)).isoformat()
        fresh = (NOW - datetime.timedelta(hours=2)).isoformat()
        self._session("meta/.ingest/abc/session.json", {"status": "open", "sha1": "abc", "raw": "raw/papers/x.pdf", "opened_at": old})
        self._session("meta/.ingest/def/session.json", {"status": "open", "sha1": "def", "raw": "raw/papers/y.pdf", "opened_at": fresh})
        self._session("meta/.ingest/ghi/session.json", {"status": "closed", "sha1": "ghi", "opened_at": old})
        self._session("meta/.distill/t1/session.json", {"status": "open", "think_slug": "t1", "think_path": "think/t1.md", "opened_at": old})
        self._session("meta/.ops/current.json", {"op": "refine", "target": "x", "started": old, "baseline": {}})
        self._session("meta/.researcher/lior-wolf/session.json", {"status": "open", "opened_at": old})
        found = hygiene.check_sessions(self.root, NOW)
        self.assertEqual(kinds(found), ["stale-session"] * 4)
        details = " | ".join(f.detail for f in found)
        for needle in ("ingest abc", "distill think/t1.md", "ops refine x", "researcher lior-wolf"):
            self.assertIn(needle, details)
        self.assertNotIn("def", details)
        fixes = " | ".join(f.fix for f in found)
        self.assertIn("kb_distillery.ingest abort abc", fixes)
        self.assertIn("pixi run ops -- commit", fixes)

    def test_session_without_timestamp_uses_file_mtime(self):
        self._session("meta/.ingest/abc/session.json", {"status": "open", "sha1": "abc"})
        path = os.path.join(self.root, "meta", ".ingest", "abc", "session.json")
        old = time.time() - 3 * 86400
        os.utime(path, (old, old))
        found = hygiene.check_sessions(self.root, datetime.datetime.now(datetime.timezone.utc))
        self.assertEqual(kinds(found), ["stale-session"])

    def test_no_sessions(self):
        self.assertEqual(hygiene.check_sessions(self.root, NOW), [])


class PrChecks(unittest.TestCase):
    def test_idle_prs_only(self):
        rows = [{"number": 3, "branch": "infra/a", "title": "A", "age": "9d", "hours": 9 * 24, "updated_hours": 80},
                {"number": 4, "branch": "infra/b", "title": "B", "age": "9d", "hours": 9 * 24, "updated_hours": 5},
                {"number": 5, "branch": "infra/c", "title": "C", "age": "?", "hours": None, "updated_hours": None}]
        with tempfile.TemporaryDirectory() as tmp:
            g(tmp, "init", "-q")
            with patch.object(ship, "open_prs", return_value=rows):
                found = hygiene.check_stale(tmp, NOW)
        self.assertEqual(kinds(found), ["idle-pr"])
        self.assertIn("PR #3", found[0].detail)

    def test_gh_unavailable_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            g(tmp, "init", "-q")
            with patch.object(ship, "open_prs", return_value=[]):
                self.assertEqual(hygiene.check_stale(tmp, NOW), [])


class SiteChecks(Repo):
    def _status(self, **kw):
        from kb_distillery.publish.cloudflare.contracts import StatusFile
        path = os.path.join(self.root, ".cache", "share", "status.json")
        data = {"state": "deployed", "sha": g(self.root, "rev-parse", "main"), "kb_version": "1.0.1",
                "at": NOW.isoformat(), "error": None, "url": "https://kb.example"}
        data.update(kw)
        StatusFile(path).write(**data)
        return path

    def test_no_status_file(self):
        self.assertEqual(hygiene.check_site(self.root, NOW), [])

    def test_failed_deploy_is_an_error(self):
        self._status(state="failed", error="wrangler deploy exited 1")
        found = hygiene.check_site(self.root, NOW)
        self.assertEqual([(f.severity, f.kind, f.fix) for f in found], [("error", "deploy-failed", hygiene.DEPLOY_FIX)])
        self.assertIn("wrangler deploy exited 1", found[0].detail)

    def test_refused_no_access_is_an_error(self):
        self._status(state="refused-no-access", error="auth gate down")
        self.assertEqual(kinds(hygiene.check_site(self.root, NOW)), ["deploy-failed"])

    def test_site_at_main_is_fine(self):
        self._status()
        self.assertEqual(hygiene.check_site(self.root, NOW), [])

    def test_site_behind_main_for_a_day_is_stale(self):
        old_sha = g(self.root, "rev-parse", "main")
        self.commit("wiki/c.md", "c", "kb(refine): c (kb-1.0.2)")
        self._status(sha=old_sha, at=(NOW - datetime.timedelta(hours=30)).isoformat())
        found = hygiene.check_site(self.root, NOW)
        self.assertEqual(kinds(found), ["site-stale"])
        self.assertIn("1 commit(s) behind main", found[0].detail)

    def test_site_behind_main_but_fresh_deploy_is_fine(self):
        old_sha = g(self.root, "rev-parse", "main")
        self.commit("wiki/c.md", "c", "kb(refine): c (kb-1.0.2)")
        self._status(sha=old_sha, at=(NOW - datetime.timedelta(hours=1)).isoformat())
        self.assertEqual(hygiene.check_site(self.root, NOW), [])

    def test_site_sha_not_on_main(self):
        self._status(sha="0" * 40)
        found = hygiene.check_site(self.root, NOW)
        self.assertEqual(kinds(found), ["site-stale"])
        self.assertIn("not on main", found[0].detail)


class SnapshotChecks(unittest.TestCase):
    def test_orphans(self):
        from kb_distillery.publish.site import snapshots
        plan = {"orphans": ["snapshot-20261001-x"], "unknown": [], "foreign": [], "ok": ["snapshot-20261002-y"]}
        with patch.object(snapshots, "prune_plan", return_value=plan):
            found = hygiene.check_snapshots("/nowhere", NOW)
        self.assertEqual([(f.kind, f.detail) for f in found], [("orphan-snapshot", "snapshot-20261001-x has no reachable manifest")])
        self.assertEqual(found[0].fix, "pixi run share -- prune --apply")

    def test_offline_or_no_credentials_is_silent(self):
        from kb_distillery.publish.cloudflare import cf_api
        from kb_distillery.publish.site import snapshots
        with patch.object(snapshots, "prune_plan", side_effect=cf_api.CloudflareError("no credentials")):
            self.assertEqual(hygiene.check_snapshots("/nowhere", NOW), [])


class OtherLaneAndNightly(Repo):
    def test_other_lane_files(self):
        with open(os.path.join(self.root, "stray.txt"), "w") as f:
            f.write("?\n")
        found = hygiene.check_other_lane(self.root, NOW)
        self.assertEqual(kinds(found), ["other-lane"])
        self.assertIn("stray.txt", found[0].detail)
        self.assertEqual(found[0].severity, "warn")

    def test_other_lane_clean(self):
        self.assertEqual(hygiene.check_other_lane(self.root, NOW), [])

    def test_nightly_not_installed(self):
        with patch.object(core, "nightly_status", return_value={"installed": False, "loaded": False, "last_run": None,
                                                                "summary": "NOT INSTALLED", "hint": "pixi run install-sync"}):
            found = hygiene.check_nightly(self.root, NOW)
        self.assertEqual([(f.kind, f.fix) for f in found], [("nightly-not-installed", "pixi run install-sync")])
        with patch.object(core, "nightly_status", return_value={"installed": True, "loaded": True, "last_run": "x",
                                                                "summary": "ok", "hint": None}):
            self.assertEqual(hygiene.check_nightly(self.root, NOW), [])


class Quarantine(Repo):
    def _fill(self, nbytes):
        d = os.path.join(self.root, "_quarantine", "x")
        os.makedirs(d)
        with open(os.path.join(d, "big.bin"), "wb") as f:
            f.truncate(nbytes)

    def test_large_quarantine_warns(self):
        self._fill(3 * 1024 * 1024)
        found = hygiene.check_quarantine(self.root, NOW, limit_mb=2)
        self.assertEqual(kinds(found), ["quarantine-large"])
        self.assertEqual(found[0].severity, "warn")
        self.assertIn("3 MB", found[0].detail)
        self.assertTrue(os.path.exists(os.path.join(self.root, "_quarantine", "x", "big.bin")))

    def test_small_or_missing_quarantine_clean(self):
        self.assertEqual(hygiene.check_quarantine(self.root, NOW), [])
        self._fill(1024)
        self.assertEqual(hygiene.check_quarantine(self.root, NOW), [])


class Runner(unittest.TestCase):
    def test_slow_check_times_out_and_the_rest_still_run(self):
        def sleepy(root, now):
            time.sleep(1.5)
            return [hygiene.Finding("error", "never", "should not appear")]

        def quick(root, now):
            return [hygiene.Finding("warn", "quick", "ran")]

        report = hygiene.run("/nowhere", budget=5, check_cap=0.2, checks=[("sleepy", sleepy), ("quick", quick)])
        self.assertEqual(kinds(report.findings), ["check-timeout", "quick"])
        self.assertIn("sleepy timed out", report.findings[0].detail)
        self.assertEqual(report.checks, ["quick"])

    def test_budget_exhausted_skips_remaining_checks(self):
        def sleepy(root, now):
            time.sleep(1.0)
            return []

        report = hygiene.run("/nowhere", budget=0.3, checks=[("a", sleepy), ("b", lambda r, n: [])])
        self.assertEqual(kinds(report.findings), ["check-skipped", "check-timeout"])

    def test_a_raising_check_is_isolated(self):
        def broken(root, now):
            raise RuntimeError("boom")

        report = hygiene.run("/nowhere", budget=5, checks=[("broken", broken), ("ok", lambda r, n: [])])
        self.assertEqual([(f.kind, f.severity) for f in report.findings], [("check-error", "warn")])
        self.assertIn("RuntimeError: boom", report.findings[0].detail)
        self.assertEqual(report.checks, ["ok"])

    def test_report_text_json_and_fingerprint(self):
        f1 = hygiene.Finding("error", "unpushed-steps", "main is 2 commit(s) ahead", "pixi run daily-sync")
        f2 = hygiene.Finding("warn", "stale-worktree", "x merged", "pixi run ship -- prune --apply")
        a = hygiene.Report(findings=[f2, f1], checks=["a"], elapsed=0.1)
        b = hygiene.Report(findings=[f1, f2], checks=["a"], elapsed=9.9)
        self.assertEqual(a.fingerprint(), b.fingerprint())            # order and timing don't matter
        self.assertEqual(a.kinds(), ["unpushed-steps", "stale-worktree"])  # errors first
        text = a.text()
        self.assertTrue(text.startswith("hygiene: 1 error(s), 1 warning(s)"))
        self.assertIn("[ERROR] unpushed-steps", text)
        self.assertIn("fix: pixi run daily-sync", text)
        d = json.loads(json.dumps(a.as_dict()))
        self.assertEqual((d["errors"], d["warnings"], len(d["findings"])), (1, 1, 2))
        self.assertEqual(hygiene.Report(checks=["a", "b"]).text(), "hygiene: clean (2 checks, 0.0s)")

    def test_real_checks_on_a_clean_temp_repo(self):
        """The full CHECKS list runs end to end (network-y checks mocked away)."""
        from kb_distillery.publish.cloudflare import cf_api
        from kb_distillery.publish.site import snapshots
        r = Repo()
        r.setUp()
        try:
            with patch.object(ship, "open_prs", return_value=[]), \
                    patch.object(snapshots, "prune_plan", side_effect=cf_api.CloudflareError("offline")), \
                    patch.object(core, "nightly_status", return_value={"installed": True, "loaded": True, "last_run": "x",
                                                                       "summary": "ok", "hint": None}):
                report = hygiene.run(r.root, budget=30)
            self.assertEqual(report.findings, [], report.text())
            self.assertEqual(report.checks, [name for name, _ in hygiene.CHECKS])
        finally:
            r.tearDown()


class SyncHook(Repo):
    """ops.core.sync runs hygiene after the sync; hygiene can never change the sync's outcome."""

    def setUp(self):
        super().setUp()
        self.env2 = patch.dict(os.environ, {"KB_NO_HYGIENE": ""})
        self.env2.start()
        _lint = patch("kb_distillery.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test
        _lint.start()
        self.addCleanup(_lint.stop)
        self.commit("meta/stub.py", "x = 1", "chore(init): tooling stub")
        g(self.root, "push", "-q", "origin", "main")

    def tearDown(self):
        self.env2.stop()
        super().tearDown()

    def test_hygiene_crash_does_not_fail_sync(self):
        with patch.object(hygiene, "run", side_effect=RuntimeError("hygiene exploded")):
            self.assertEqual(core.sync(push=False, root=self.root), 0)

    def test_clean_sync_runs_hygiene_and_reports(self):
        from kb_distillery.ops import notify
        report = hygiene.Report(checks=["x"])
        with patch.object(hygiene, "run", return_value=report) as run, \
                patch.object(notify, "notify_report", return_value="clean") as nr:
            self.assertEqual(core.sync(push=False, root=self.root), 0)
        run.assert_called_once()
        self.assertEqual(nr.call_args.kwargs["sync_failed"], False)

    def test_sync_exception_is_emailed_then_reraised(self):
        from kb_distillery.ops import notify
        with patch.object(core, "_sync", side_effect=RuntimeError("push exploded")), \
                patch.object(hygiene, "run", return_value=hygiene.Report()), \
                patch.object(notify, "notify_report", return_value="sent") as nr, \
                patch.object(notify, "log_tail", return_value="log line\n"):
            with self.assertRaises(RuntimeError):
                core.sync(push=False, root=self.root)
        self.assertTrue(nr.call_args.kwargs["sync_failed"])
        self.assertIn("push exploded", nr.call_args.kwargs["error"])
        self.assertEqual(nr.call_args.kwargs["tail"], "log line\n")

    def test_ops_error_skip_becomes_a_finding(self):
        from kb_distillery.ops import notify
        with patch.object(core, "_sync", side_effect=core.OpsError("lint failed — nothing committed")), \
                patch.object(hygiene, "run", return_value=hygiene.Report()), \
                patch.object(notify, "notify_report", return_value="sent") as nr:
            self.assertEqual(core.sync(push=False, root=self.root), 0)    # exit code unchanged
        report = nr.call_args.args[0]
        self.assertEqual([(f.severity, f.kind) for f in report.findings], [("error", "sync-skipped")])

    def test_dry_run_skips_hygiene(self):
        with patch.object(hygiene, "run") as run:
            core.sync(dry_run=True, root=self.root)
        run.assert_not_called()

    def test_env_switch_disables_hygiene(self):
        with patch.dict(os.environ, {"KB_NO_HYGIENE": "1"}), patch.object(hygiene, "run") as run:
            core.sync(push=False, root=self.root)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

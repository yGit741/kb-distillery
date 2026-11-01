#!/usr/bin/env python3
"""Tests for src/kb_distillery/git/staleness.py — the stale-work rules, `ship prune --stale` and the hygiene check."""
import datetime
import os
import shutil
import unittest

from kb_distillery.git import ship, staleness
from kb_distillery.ops import hygiene
from tests.ops.test_hygiene import Repo, g, kinds

HOUR = datetime.timedelta(hours=1)


def now_plus(hours):
    return datetime.datetime.now(datetime.timezone.utc) + hours * HOUR


class Rules(Repo):
    def live(self, name):
        path = self.worktree(name, f"infra/{name}")
        self.commit("meta/x.py", f"x = '{name}'", f"feat(x): {name}", cwd=path)
        return path

    def test_unmerged_branch_idle_for_48h_without_pr_is_stale(self):
        self.live("old")
        self.assertEqual(staleness.scan(self.root, now_plus(47), prs=[]), [])          # 47 h: not yet
        items = staleness.scan(self.root, now_plus(49), prs=[])
        self.assertEqual([(i["kind"], i["branch"], i["ahead"]) for i in items], [("idle-branch", "infra/old", 1)])

    def test_open_pr_shields_the_branch_but_idles_itself_after_3_days(self):
        self.live("pr")
        pr = [{"number": 7, "branch": "infra/pr", "title": "feat(x): pr", "updated_hours": 80}]
        items = staleness.scan(self.root, now_plus(60), prs=pr)              # tip 60 h old, PR updated 80 h ago
        self.assertEqual(items, [])                                         # newest activity wins: 60 h < 72 h
        items = staleness.scan(self.root, now_plus(75), prs=pr)
        self.assertEqual([(i["kind"], i["pr"]) for i in items], [("idle-pr", 7)])

    def test_recent_pr_comment_counts_as_activity(self):
        self.live("pr")
        pr = [{"number": 7, "branch": "infra/pr", "title": "t", "updated_hours": 2}]
        self.assertEqual(staleness.scan(self.root, now_plus(100), prs=pr), [])

    def test_started_never_used_branch_is_stale_after_48h(self):
        self.worktree("unused", "infra/unused")
        self.assertEqual(staleness.scan(self.root, now_plus(47), prs=[]), [])
        items = staleness.scan(self.root, now_plus(49), prs=[])
        self.assertEqual([(i["kind"], i["branch"], i["ahead"]) for i in items], [("idle-branch", "infra/unused", 0)])
        self.assertIn("never committed", items[0]["detail"])

    def test_merged_branch_is_left_to_plain_prune(self):
        self.live("done")
        self.merge_to_main("infra/done")
        self.assertEqual(staleness.scan(self.root, now_plus(100), prs=[]), [])

    def test_missing_and_detached_worktrees(self):
        gone = self.worktree("gone", "infra/gone")
        shutil.rmtree(gone)
        det = os.path.join(self.wt_dir, "det")
        g(self.root, "worktree", "add", "-q", "--detach", det, "main")
        self.assertEqual([i["kind"] for i in staleness.scan(self.root, now_plus(0), prs=[])],
                         ["missing-worktree"])                       # a fresh detached worktree is live work
        self.assertEqual(sorted(i["kind"] for i in staleness.scan(self.root, now_plus(49), prs=[])),
                         ["detached-worktree", "idle-branch", "missing-worktree"])   # infra/gone: never used

    def test_hygiene_fixes_cover_every_kind(self):
        self.assertEqual(set(hygiene.STALE_FIX), set(staleness.KINDS))

    def test_hygiene_reports_the_same_items(self):
        self.live("old")
        pr = [{"number": 9, "branch": "infra/other", "title": "t", "updated_hours": 100}]
        from unittest.mock import patch
        with patch.object(ship, "open_prs", return_value=pr):
            found = hygiene.check_stale(self.root, now_plus(49))
        self.assertEqual(kinds(found), ["idle-branch", "idle-pr"])
        self.assertIn("prune --stale", found[0].fix)


class PruneStale(Repo):
    def setUp(self):
        super().setUp()
        self.idle = self.worktree("idle", "infra/idle")
        self.commit("meta/a.py", "a = 1", "feat(a): idle work", cwd=self.idle)
        self.dirty = self.worktree("dirty", "infra/dirty")
        self.commit("meta/b.py", "b = 1", "feat(b): dirty work", cwd=self.dirty)
        with open(os.path.join(self.dirty, "meta", "wip.py"), "w") as f:
            f.write("wip\n")
        g(self.root, "push", "-q", "origin", "infra/idle")
        self.later = now_plus(72)
        self.idle_sha = g(self.root, "rev-parse", "infra/idle")

    def patch_name(self):
        return f"stale-infra-idle-{self.idle_sha[:9]}.patch"

    def run_prune(self, apply, root=None):
        return staleness.cmd_prune_stale(apply=apply, root=root or self.root, now=self.later, prs=[])

    def test_dry_run_changes_nothing(self):
        self.run_prune(apply=False)
        self.assertTrue(os.path.isdir(self.idle))
        self.assertIn("infra/idle", g(self.root, "branch", "--list"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "_quarantine")))

    def test_apply_quarantines_then_removes_and_keeps_dirty(self):
        self.run_prune(apply=True)
        self.assertFalse(os.path.exists(self.idle))
        branches = g(self.root, "branch", "--list")
        self.assertNotIn("infra/idle", branches)
        self.assertIn("infra/idle", g(self.root, "ls-remote", "--heads", "origin"))   # origin kept: a PR is never closed
        with open(os.path.join(self.root, "_quarantine", self.patch_name())) as f:
            self.assertIn("feat(a): idle work", f.read())
        self.assertTrue(os.path.exists(os.path.join(self.dirty, "meta", "wip.py")))   # dirty: untouched
        self.assertTrue(os.path.exists(os.path.join(self.root, "_quarantine", self.patch_name()[:-6] + ".bundle")))
        self.assertIn("infra/dirty", branches)

    def test_apply_never_removes_the_current_worktree(self):
        self.run_prune(apply=True, root=self.idle)
        self.assertTrue(os.path.isdir(self.idle))
        self.assertIn("infra/idle", g(self.root, "branch", "--list"))

    def test_idle_pr_is_listed_never_closed(self):
        pr = [{"number": 4, "branch": "infra/idle", "title": "t", "updated_hours": 200}]
        plan = staleness.plan(staleness.scan(self.root, self.later, prs=pr))
        self.assertEqual(sorted((i["kind"], i["branch"], a) for i, a, _ in plan),
                         [("idle-branch", "infra/dirty", "keep"), ("idle-pr", "infra/idle", "list")])

    def test_summary_line(self):
        line = staleness.summary(staleness.scan(self.root, self.later, prs=[]))
        self.assertIn("infra/idle (idle-branch)", line)
        self.assertIn("prune --stale", line)


if __name__ == "__main__":
    unittest.main()

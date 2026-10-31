#!/usr/bin/env python3
"""Tests for git lanes: schema.lane_of, daily_sync.changed_paths, backend/src/kb/git/ship.py."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.paths import vault_root
ROOT = vault_root()

from kb.maintenance import daily_sync
from kb.git import ship
from kb.core.schema import lane_of


class LaneOfTests(unittest.TestCase):
    def test_knowledge(self):
        for p in ("wiki/x.md", "think/a.md", "raw/web/clip.md", "index.md",
                  "meta/corpus.tsv", "meta/log.md", "meta/chats/conv-1.json"):
            self.assertEqual(lane_of(p), "knowledge", p)

    def test_tooling(self):
        for p in ("backend/src/kb/dashboard/serve.py", "skills/x/SKILL.md", "tools/launch.sh",
                  "pixi.toml", "AGENTS.md", "tools/hooks/block-git-write.sh", ".claude/settings.json",
                  ".obsidian/app.json", "frontend/src/main.tsx", "frontend/dist/index.html"):
            self.assertEqual(lane_of(p), "tooling", p)

    def test_other(self):
        for p in ("Untitled.md", "wiki_archive.zip", ".playwright-mcp/page.png", "indexes.md"):
            self.assertEqual(lane_of(p), "other", p)

    def test_prefix_needs_separator(self):
        self.assertEqual(lane_of("wikiwhatever.md"), "other")
        self.assertEqual(lane_of("meta/log.md.bak"), "tooling")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class ChangedPathsTests(unittest.TestCase):
    def test_groups_by_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git(tmp, "init", "-q")
            for rel in ("wiki/a.md", "meta/tool.py", "junk.txt", "meta/log.md"):
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
                with open(os.path.join(tmp, rel), "w") as f:
                    f.write("x")
            lanes = daily_sync.changed_paths(tmp)
            self.assertEqual(sorted(lanes["knowledge"]), ["meta/log.md", "wiki/a.md"])
            self.assertEqual(lanes["tooling"], ["meta/tool.py"])
            self.assertEqual(lanes["other"], ["junk.txt"])


class ShipTests(unittest.TestCase):
    LANES = {"knowledge": ["wiki/a.md"], "tooling": ["meta/tool.py"], "other": ["junk.txt"]}

    def test_requires_message(self):
        with patch("kb.git.ship.changed_paths", return_value=self.LANES):
            with self.assertRaises(SystemExit):
                ship.main([])

    def test_nothing_to_ship(self):
        lanes = dict(self.LANES, tooling=[])
        with patch("kb.git.ship.changed_paths", return_value=lanes), \
             patch("kb.git.ship.run_git") as git:
            self.assertEqual(ship.main(["feat(ship): x"]), 0)
            git.assert_not_called()

    def test_gate_failure_blocks_commit(self):
        with patch("kb.git.ship.changed_paths", return_value=self.LANES), \
             patch("kb.git.ship.has_open_sessions", return_value=([], [])), \
             patch("kb.git.ship.subprocess.run", return_value=subprocess.CompletedProcess([], 1)), \
             patch("kb.git.ship.run_git") as git:
            self.assertEqual(ship.main(["feat(ship): x"]), 1)
            git.assert_not_called()

    def test_stages_tooling_only(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        with patch("kb.git.ship.changed_paths", return_value=self.LANES), \
             patch("kb.git.ship.has_open_sessions", return_value=([], [])), \
             patch("kb.git.ship.subprocess.run", return_value=ok), \
             patch("kb.git.ship.run_git", return_value=ok) as git:
            self.assertEqual(ship.main(["feat(ship): x", "--no-push"]), 0)
            add, commit = git.call_args_list
            self.assertEqual(add.args[0], ["add", "-A", "--", "meta/tool.py"])
            self.assertEqual(commit.args[0], ["commit", "-m", "feat(ship): x", "--", "meta/tool.py"])


FAKE_GH = """#!/bin/bash
# fake gh: records calls; 'pr view' succeeds once 'pr create' ran; the hold label lives in a file
log="$FAKE_GH_DIR/calls.log"
echo "$*" >> "$log"
if [ "$1 $2" = "pr view" ]; then
  [ -f "$FAKE_GH_DIR/created" ] || exit 1
  labels=""; [ -f "$FAKE_GH_DIR/held" ] && labels='{"name": "hold"}'
  head=$(cat "$FAKE_GH_DIR/head" 2>/dev/null)
  echo '{"number": 7, "url": "https://example/pr/7", "title": "feat(ops): add thing", "state": "OPEN", "headRefOid": "'"$head"'", "labels": ['"$labels"']}'
  exit 0
fi
if [ "$1" = "api" ]; then
  case "$*" in *"/reviews"*) cat "$FAKE_GH_DIR/reviews.jsonl" 2>/dev/null; exit 0;; esac
fi
if [ "$1 $2" = "pr create" ]; then
  touch "$FAKE_GH_DIR/created"; case "$*" in *"--label hold"*) touch "$FAKE_GH_DIR/held";; esac
  echo "https://example/pr/7"; exit 0
fi
if [ "$1 $2" = "pr comment" ] && [ -n "$FAKE_COMMENT_FAIL" ]; then
  echo "boom" >&2; exit 1
fi
if [ "$1 $2" = "pr edit" ]; then
  case "$*" in *"--remove-label hold"*) rm -f "$FAKE_GH_DIR/held";; *"--add-label hold"*) touch "$FAKE_GH_DIR/held";; esac
fi
exit 0
"""


def _g(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


class PrFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.remote = os.path.join(t, "remote.git")
        self.repo = os.path.join(t, "repo")
        _g(t, "init", "-q", "--bare", "-b", "main", self.remote)
        _g(t, "clone", "-q", self.remote, self.repo)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            _g(self.repo, "config", k, v)
        with open(os.path.join(self.repo, ".gitignore"), "w") as f:
            f.write(".claude/worktrees/\n")
        self._write(self.repo, "meta/tool.py")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "chore: init (retro)")
        _g(self.repo, "push", "-q", "-u", "origin", "main")
        self.ghdir = os.path.join(t, "gh")
        os.makedirs(self.ghdir)
        gh = os.path.join(self.ghdir, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.env = patch.dict(os.environ, {"GH_BIN": gh, "FAKE_GH_DIR": self.ghdir,
                                           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def _write(root, rel, text="x"):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a") as f:
            f.write(text + "\n")

    def _start(self, feature="ops-thing"):
        self.assertEqual(ship.cmd_start(feature, worktree=True, root=self.repo), 0)
        return os.path.join(self.repo, ".claude", "worktrees", feature)

    def test_start_refused_in_primary(self):
        self.assertEqual(ship.cmd_start("x", root=self.repo), 1)

    def test_start_worktree_creates_branch(self):
        wt = self._start()
        self.assertEqual(ship.current_branch(wt), "infra/ops-thing")
        self.assertTrue(ship.is_linked_worktree(wt))
        self.assertEqual(os.path.realpath(ship.primary_checkout(wt)), os.path.realpath(self.repo))

    def test_start_worktree_links_the_primary_pixi_env(self):
        import contextlib, io
        os.makedirs(os.path.join(self.repo, ".pixi", "envs"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            wt = self._start("pixi-link")
        link = os.path.join(wt, ".pixi")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(self.repo, ".pixi")))
        self.assertIn(f"PYTHONPATH={wt}/backend/src".replace("/private", ""), buf.getvalue().replace("/private", ""))

    def test_start_worktree_without_primary_pixi_makes_no_link(self):
        wt = self._start("no-pixi")
        self.assertFalse(os.path.lexists(os.path.join(wt, ".pixi")))

    def test_commit_policy_and_lanes(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        self._write(wt, "wiki/a.md")
        self.assertEqual(ship.cmd_commit("bad message", root=wt, gates=False), 1)
        self.assertEqual(ship.cmd_commit("feat(ops): add thing", root=wt, gates=False), 0)
        files = _g(wt, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(files, ["meta/tool.py"])

    def test_schema_commit_takes_notes_and_the_manifest_but_not_index(self):
        wt = self._start("books")
        for rel in ("backend/src/kb/core/schema.py", "wiki/a.md", "index.md", "meta/corpus.tsv"):
            self._write(wt, rel)
        self.assertEqual(ship.cmd_commit("schema(books): add hub", root=wt, gates=False), 0)
        files = set(_g(wt, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(files, {"backend/src/kb/core/schema.py", "wiki/a.md", "meta/corpus.tsv"})   # migrated dispositions

    def test_feature_commit_never_takes_generated_files(self):
        wt = self._start("plain")
        for rel in ("meta/tool.py", "index.md", "meta/corpus.tsv"):
            self._write(wt, rel)
        self.assertEqual(ship.cmd_commit("feat(ops): add thing", root=wt, gates=False), 0)
        self.assertEqual(_g(wt, "show", "--name-only", "--format=", "HEAD").split(), ["meta/tool.py"])

    def test_schema_merge_refuses_clashing_local_note(self):
        wt = self._start("books")
        self._write(wt, "backend/src/kb/core/schema.py")
        self._write(wt, "wiki/b.md", "migrated")
        ship.cmd_commit("schema(books): add hub", root=wt, gates=False)
        self._write(self.repo, "wiki/b.md", "my own edit")       # differs → clash
        self.assertEqual(ship.cmd_merge(local=True, pr_number=5, title="schema(books): add hub",
                                        root=wt, gates=False), 1)
        with open(os.path.join(self.repo, "wiki/b.md"), "w") as f:
            f.write("migrated\n")                                  # identical → fine
        self._write(self.repo, "wiki/unrelated.md", "elsewhere")  # unrelated dirt → fine
        self.assertEqual(ship._knowledge_clashes(wt, self.repo, "origin/main"), [])

    def test_merge_syncs_main_over_regenerated_files(self):
        self._write(self.repo, "index.md", "v1")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "kb(catalog): a (kb-0.7.1)\n\nKB-Version: 0.7.1\nKB-Op: catalog\nKB-Target: a")
        _g(self.repo, "push", "-q", "origin", "main")
        wt = self._start("sync")
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self._write(self.repo, "index.md", "v2")   # main moves on and changes a generated file
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "kb(catalog): b (kb-0.7.2)\n\nKB-Version: 0.7.2\nKB-Op: catalog\nKB-Target: b")
        self._write(self.repo, "meta/other.py")    # and a tooling merge lands, so a sync is due
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "feat(ops): other (#6)")
        _g(self.repo, "push", "-q", "origin", "main")
        self._write(wt, "index.md", "regenerated by lint in the worktree")
        rc = ship.cmd_merge(local=True, pr_number=8, title="feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(rc, 0)

    def test_sync_merges_main_and_leaves_conflicts_to_resolve(self):
        wt = self._start("sync-conflict")
        self._write(wt, "meta/tool.py", "mine")
        self.assertEqual(ship.cmd_commit("feat(ops): mine", root=wt, gates=False), 0)
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 0)          # main has not moved
        self._write(self.repo, "meta/tool.py", "theirs")
        self._write(self.repo, "meta/other.py", "theirs too")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "feat(ops): theirs (#9)")
        _g(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 1)          # conflict in meta/tool.py
        self.assertEqual(ship.cmd_sync(cont=True, root=wt, gates=False), 1)   # still unresolved
        with open(os.path.join(wt, "meta/tool.py"), "w") as f:
            f.write("x\nmine\ntheirs\n")
        _g(wt, "add", "meta/tool.py")
        self.assertEqual(ship.cmd_sync(cont=True, root=wt, gates=False), 0)
        self.assertEqual(len(_g(wt, "rev-list", "--parents", "-n1", "HEAD").split()), 3)   # a merge commit
        self.assertTrue(os.path.isfile(os.path.join(wt, "meta/other.py")))
        self.assertEqual(_g(wt, "log", "-1", "--format=%s"), "Merge branch 'main' into infra/sync-conflict")

    def test_sync_abort_and_dirty_tree(self):
        wt = self._start("sync-abort")
        self._write(self.repo, "meta/other.py", "theirs")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "feat(ops): theirs (#9)")
        _g(self.repo, "push", "-q", "origin", "main")
        self._write(wt, "meta/tool.py", "uncommitted")
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 1)          # commit first
        self.assertEqual(ship.cmd_sync(abort=True, root=wt, gates=False), 0)

    def test_commit_handles_already_staged_deletion(self):
        wt = self._start("cleanup")
        _g(wt, "rm", "-q", "meta/tool.py")  # staged deletion, file gone from disk and index
        self.assertEqual(ship.cmd_commit("chore(git): remove old tool", root=wt, gates=False), 0)
        self.assertEqual(_g(wt, "show", "--name-status", "--format=", "HEAD"), "D\tmeta/tool.py")

    def test_pr_then_merge_via_gh_never_squashes(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)  # idempotent
        self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)
        calls = open(os.path.join(self.ghdir, "calls.log")).read()
        self.assertEqual(calls.count("pr create"), 1)
        merge_line = [l for l in calls.splitlines() if l.startswith("pr merge")][0]
        self.assertIn("--merge", merge_line)
        self.assertNotIn("--squash", merge_line)
        self.assertIn("feat(ops): add thing (#7)", merge_line)

    def test_pr_and_merge_post_events(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)
        self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)
        posted = [l.split(" · ")[1] for l in open(os.path.join(self.ghdir, "calls.log")).read().splitlines()
                  if l.startswith("pr comment 7 --body kb-event v1")]
        self.assertEqual(posted, ["claimed", "queued", "checks-passed", "merged"])
        claimed = [l for l in open(os.path.join(self.ghdir, "calls.log")) if "· claimed ·" in l][0]
        self.assertIn("branch=infra/ops-thing dirs=meta", claimed)

    def test_comment_failure_never_fails_merge(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        with patch.dict(os.environ, {"FAKE_COMMENT_FAIL": "1"}):
            self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)
        calls = open(os.path.join(self.ghdir, "calls.log")).read()
        self.assertEqual(calls.count("pr merge"), 1)
        self.assertEqual(calls.count("pr comment"), 8)   # 4 events × (try + one retry)

    def test_plain_pr_is_not_held_and_merges_without_approval(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)
        self.assertFalse(os.path.exists(os.path.join(self.ghdir, "held")))

    def test_held_pr_refuses_merge_until_approved(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False, hold=True), 0)
        self.assertEqual(ship.cmd_merge(root=wt, gates=False), 1)
        self.assertNotIn("pr merge", open(os.path.join(self.ghdir, "calls.log")).read())
        self.assertEqual(ship.cmd_approve(7, root=wt), 0)
        self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)

    # ---- C2: the owner's GitHub Approve review lifts the hold ----
    def _held(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(root=wt, gates=False, hold=True), 0)
        head = _g(wt, "rev-parse", "HEAD")
        with open(os.path.join(self.ghdir, "head"), "w") as f:
            f.write(head)
        return wt, head

    def _reviews(self, *rows):
        import json
        with open(os.path.join(self.ghdir, "reviews.jsonl"), "w") as f:   # gh api --paginate --jq '.[]'
            f.writelines(json.dumps({"user": {"login": u}, "state": st, "commit_id": sha}) + "\n" for u, st, sha in rows)

    def _calls(self):
        return open(os.path.join(self.ghdir, "calls.log")).read()

    def test_owner_approval_at_head_lifts_hold_and_merges(self):
        wt, head = self._held()
        self._reviews(("yGit741", "APPROVED", head))
        with patch.object(ship.app_token, "owner_login", return_value="yGit741"):
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)
        calls = self._calls()
        self.assertIn(f"--match-head-commit {head}", calls)
        self.assertLess(calls.index("pr merge"), calls.index("--remove-label hold"))   # label lifted only after the merge
        self.assertIn("kb-event", calls.split("--remove-label hold")[1])

    def test_owner_approval_on_old_sha_is_refused(self):
        wt, head = self._held()
        self._reviews(("yGit741", "APPROVED", "0" * 40))
        with patch.object(ship.app_token, "owner_login", return_value="yGit741"):
            self.assertEqual(ship.review_approval(7, head, wt)[0], "stale")
            self.assertIn("re-approve: new commits since your review", ship.review_approval(7, head, wt)[1])
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 1)
        self.assertNotIn("pr merge", self._calls())

    def test_approval_by_another_login_or_the_bot_never_counts(self):
        wt, head = self._held()
        self._reviews(("someone", "APPROVED", head), ("thesis-knowledge-base[bot]", "APPROVED", head))
        with patch.object(ship.app_token, "owner_login", return_value="yGit741"):
            self.assertEqual(ship.review_approval(7, head, wt)[0], "none")
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 1)
        self.assertNotIn("pr merge", self._calls())

    def test_latest_owner_verdict_wins(self):
        wt, head = self._held()
        self._reviews(("yGit741", "APPROVED", head), ("yGit741", "COMMENTED", head),
                      ("yGit741", "CHANGES_REQUESTED", head))
        with patch.object(ship.app_token, "owner_login", return_value="yGit741"):
            self.assertEqual(ship.review_approval(7, head, wt)[0], "none")

    def test_no_app_config_keeps_the_old_behaviour(self):
        wt, head = self._held()
        self._reviews(("yGit741", "APPROVED", head))
        with patch.object(ship.app_token, "owner_login", return_value=None):
            self.assertEqual(ship.review_approval(7, head, wt)[0], "off")
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 1)
            self.assertEqual(ship.cmd_approve(7, root=wt), 0)
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)

    def test_approval_labels_for_status(self):
        with patch.object(ship, "review_approval", return_value=("ok", "")):
            self.assertEqual(ship.approval_label(7, "abc"), "approved ✓ (sha ok)")
        with patch.object(ship, "review_approval", return_value=("stale", "")):
            self.assertEqual(ship.approval_label(7, "abc"), "approved on old sha")
        with patch.object(ship, "review_approval", return_value=("none", "")):
            self.assertEqual(ship.approval_label(7, "abc"), "awaiting review")

    def test_approve_is_reachable_from_the_cli(self):
        with patch.object(ship, "cmd_approve", return_value=0) as approve:
            self.assertEqual(ship.main(["approve", "101"]), 0)
        approve.assert_called_once_with(101)

    def test_schema_pr_is_always_held(self):
        self.assertIsNone(ship._hold_reason(["feat(ops): add thing"]))
        self.assertIn("schema", ship._hold_reason(["schema(books): add hub"]))
        self.assertIn("paradigm", ship._hold_reason(["feat(x): y", "paradigm(schema): z"]))

    def test_merge_local_creates_merge_commit(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        rc = ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(rc, 0)
        self.assertEqual(_g(self.repo, "log", "-1", "--format=%s"), "feat(ops): add thing (#3)")
        self.assertEqual(len(_g(self.repo, "log", "-1", "--format=%P").split()), 2)
        self.assertEqual(_g(self.remote, "rev-parse", "main"), _g(self.repo, "rev-parse", "main"))

    def test_merge_removes_its_worktree_and_branch(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self._write(wt, "index.md", "regenerated")  # lint output: never a reason to keep the worktree
        self.assertEqual(ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing", root=wt, gates=False), 0)
        self.assertFalse(os.path.exists(wt))
        self.assertNotIn("infra/ops-thing", _g(self.repo, "branch", "--list"))
        self.assertEqual(ship.stale_worktrees(self.repo), [])

    def test_merge_keeps_a_dirty_worktree(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self._write(wt, "meta/unfinished.py", "not committed")
        self.assertEqual(ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing", root=wt, gates=False), 0)
        self.assertTrue(os.path.exists(os.path.join(wt, "meta/unfinished.py")))
        self.assertIn("infra/ops-thing", _g(self.repo, "branch", "--list"))
        stale = ship.stale_worktrees(self.repo)
        self.assertEqual([(r["branch"], r["merged"], r["dirty"]) for r in stale],
                         [("infra/ops-thing", True, ["meta/unfinished.py"])])

    def test_prune_removes_merged_clean_worktrees_only(self):
        clean = self._start("clean")            # started, never used
        dirty = self._start("dirty")
        self._write(dirty, "meta/wip.py", "uncommitted")
        live = self._start("live")
        self._write(live, "meta/tool.py")
        ship.cmd_commit("feat(ops): live work", root=live, gates=False)
        _g(self.repo, "branch", "worktree-session")   # a Claude session branch with nothing on it
        ship.cmd_prune(apply=False, root=self.repo)
        self.assertTrue(os.path.exists(clean))        # dry run
        ship.cmd_prune(apply=True, root=self.repo)
        self.assertFalse(os.path.exists(clean))
        self.assertTrue(os.path.exists(dirty))
        self.assertTrue(os.path.exists(live))
        branches = _g(self.repo, "branch", "--list")
        self.assertNotIn("infra/clean", branches)
        self.assertNotIn("worktree-session", branches)
        self.assertIn("infra/dirty", branches)
        self.assertIn("infra/live", branches)

    def test_prune_never_removes_the_current_worktree(self):
        wt = self._start("here")
        ship.cmd_prune(apply=True, root=wt)
        self.assertTrue(os.path.exists(wt))
        self.assertIn("infra/here", _g(self.repo, "branch", "--list"))

    def test_session_worktree_is_reported_until_it_becomes_a_pr(self):
        path = os.path.join(self.repo, ".claude", "worktrees", "session")
        _g(self.repo, "worktree", "add", "-q", path, "-b", "worktree-session")
        self._write(path, "meta/draft.py", "draft")
        rows = ship.stale_worktrees(self.repo)
        self.assertEqual([(r["branch"], r["merged"], r["dirty"]) for r in rows],
                         [("worktree-session", True, ["meta/draft.py"])])
        self.assertEqual(ship.cmd_start("session-feature", root=path), 0)   # rename → infra/
        self.assertEqual([r["branch"] for r in ship.stale_worktrees(self.repo)], ["infra/session-feature"])
        ship.cmd_commit("feat(ops): draft", root=path, gates=False)
        self.assertEqual(ship.stale_worktrees(self.repo), [])               # live infra work

    def test_commit_keeps_an_untracked_file_untracked(self):
        wt = self._start("untrack")
        self._write(wt, ".obsidian/appearance.json", "{}")
        _g(wt, "add", "-A")
        _g(wt, "commit", "-q", "-m", "chore(obsidian): track appearance")
        with open(os.path.join(wt, ".gitignore"), "a") as f:
            f.write(".obsidian/appearance.json\n")
        _g(wt, "rm", "-q", "--cached", ".obsidian/appearance.json")
        self.assertEqual(ship.cmd_commit("chore(obsidian): untrack appearance", root=wt, gates=False), 0)
        self.assertEqual(_g(wt, "show", "--name-status", "--format=", "HEAD").split("\n"),
                         ["M\t.gitignore", "D\t.obsidian/appearance.json"])
        self.assertTrue(os.path.exists(os.path.join(wt, ".obsidian/appearance.json")))

    def test_schema_merge_snapshots_and_bumps(self):
        self._write(self.repo, "wiki/a.md")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m",
           "kb(digest): a (kb-0.7.3)\n\nKB-Version: 0.7.3\nKB-Op: digest\nKB-Target: a")
        _g(self.repo, "push", "-q", "origin", "main")
        wt = self._start("books")
        self._write(wt, "backend/src/kb/core/schema.py")
        self.assertEqual(ship.cmd_commit("schema(books): hub", root=wt, gates=False), 0)
        with patch.object(ship, "SCHEMA_VERSION", (0, 9)):  # wrong bump: 0.7 → 0.9
            self.assertEqual(ship.cmd_merge(local=True, pr_number=4, title="schema(books): hub",
                                            root=wt, gates=False), 1)
        with patch.object(ship, "SCHEMA_VERSION", (0, 8)):
            rc = ship.cmd_merge(local=True, pr_number=4, title="schema(books): hub", root=wt, gates=False)
        self.assertEqual(rc, 0)
        self.assertIn("KB-Version: 0.8.0", _g(self.repo, "log", "-1", "--format=%B"))
        self.assertEqual(_g(self.repo, "cat-file", "-t", "kb-0.7.3"), "tag")
        # the migrated baseline is tagged too, so pre/post snapshots bracket the migration
        self.assertEqual(_g(self.repo, "cat-file", "-t", "kb-0.8.0"), "tag")
        self.assertEqual(_g(self.repo, "rev-parse", "kb-0.8.0^{commit}"), _g(self.repo, "rev-parse", "main"))
        self.assertEqual(_g(self.repo, "tag", "-l", "--format=%(contents:subject)", "kb-0.8.0"), "post-books")
        self.assertEqual(_g(self.remote, "rev-parse", "kb-0.8.0^{commit}"), _g(self.repo, "rev-parse", "main"))

    def test_first_schema_merge_uses_declared_schema(self):
        wt = self._start("books")
        self._write(wt, "backend/src/kb/core/schema.py")
        ship.cmd_commit("schema(books): hub", root=wt, gates=False)
        with patch.object(ship, "SCHEMA_VERSION", (0, 8)):  # no knowledge version on main yet
            self.assertEqual(ship.cmd_merge(local=True, pr_number=4, title="schema(books): hub",
                                            root=wt, gates=False), 0)
        self.assertIn("KB-Version: 0.8.0", _g(self.repo, "log", "-1", "--format=%B"))

    def test_pr_title_below_highest_commit_type_refused(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("fix(ops): repair thing", root=wt, gates=False)
        self._write(wt, "meta/tool2.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_pr(title="fix(ops): thing", root=wt, gates=False), 1)
        self.assertEqual(ship.cmd_pr(title="feat(ops): thing", root=wt, gates=False), 0)

    def test_merge_body_lists_commits(self):
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self.assertEqual(ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing",
                                        root=wt, gates=False), 0)
        self.assertEqual(_g(self.repo, "log", "-1", "--format=%b").strip(), "- feat(ops): add thing")

    def test_kb_only_main_moves_need_no_sync_merge(self):
        wt = self._start("nosync")
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        self._write(self.repo, "wiki/z.md", "z")
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "kb(catalog): z (kb-0.7.1)\n\nKB-Version: 0.7.1\nKB-Op: catalog\nKB-Target: z")
        _g(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(ship.cmd_merge(local=True, pr_number=9, title="feat(ops): add thing",
                                        root=wt, gates=False), 0)
        merges = _g(self.repo, "log", "--merges", "--format=%s", "-5")
        self.assertNotIn("Merge branch 'main'", merges)
        self.assertIn("feat(ops): add thing (#9)", merges)


class ShipTagTests(unittest.TestCase):
    """`ship tag` and the no-remote base ref, in throwaway repos with no origin."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(self._tmp.name)
        env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        _git(self.repo, "init", "-q", "-b", "main")
        self.first = self._commit("a.txt")

    def _commit(self, name):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(name)
        _git(self.repo, "add", name)
        _git(self.repo, "commit", "-q", "-m", f"chore(t): {name}")
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout.strip()

    def _tag(self, name, **kw):
        return ship.cmd_tag(name, repo=self.repo, **kw)

    def test_creates_annotated_tag(self):
        self.assertEqual(self._tag("pre-distillery"), 0)
        kind = subprocess.run(["git", "cat-file", "-t", "pre-distillery"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(kind.stdout.strip(), "tag")

    def test_at_an_older_commit(self):
        self._commit("b.txt")
        self.assertEqual(self._tag("old", at=self.first), 0)
        sha = subprocess.run(["git", "rev-parse", "old^{commit}"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(sha.stdout.strip(), self.first)

    def test_refuses_kb_snapshot_names_and_bad_names(self):
        self.assertEqual(self._tag("kb-1.0.0"), 1)
        self.assertEqual(self._tag("Bad Name"), 1)

    def test_refuses_existing_tag(self):
        self.assertEqual(self._tag("once"), 0)
        self.assertEqual(self._tag("once"), 1)

    def test_refuses_dirty_tracked_tree(self):
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("changed")
        self.assertEqual(self._tag("dirty"), 1)

    def test_refuses_off_main(self):
        _git(self.repo, "checkout", "-q", "-b", "side")
        self.assertEqual(self._tag("side-tag"), 1)

    def test_refuses_rev_not_on_main(self):
        _git(self.repo, "checkout", "-q", "-b", "side")
        off = self._commit("side.txt")
        _git(self.repo, "checkout", "-q", "main")
        self.assertEqual(self._tag("x", at=off), 1)

    def test_refuses_a_subfolder_of_a_repo(self):
        os.makedirs(os.path.join(self.repo, "sub"))
        self.assertEqual(ship.cmd_tag("sub-tag", repo=os.path.join(self.repo, "sub")), 1)

    def test_base_ref_falls_back_to_main_without_origin(self):
        self.assertEqual(ship._base_ref(self.repo), "main")

    def test_branch_files_sees_committed_work_without_origin(self):
        _git(self.repo, "checkout", "-q", "-b", "infra/x")
        self._commit("frontend_new.txt")
        self.assertIn("frontend_new.txt", ship.branch_files(self.repo))

    def test_drop_writes_a_non_empty_patch_without_origin(self):
        _git(self.repo, "checkout", "-q", "-b", "infra/gone")
        self._commit("work.txt")
        _git(self.repo, "checkout", "-q", "main")
        self.assertEqual(ship.cmd_drop("infra/gone", root=self.repo), 0)
        patch_file = os.path.join(self.repo, "_quarantine", "dropped-infra-gone.patch")
        with open(patch_file) as f:
            self.assertIn("work.txt", f.read())

    def test_guard_allows_the_tag_subcommand(self):
        from kb.git import git_guard
        self.assertTrue(git_guard.is_allowlisted("pixi run ship tag pre-distillery"))

    def test_docs_is_a_tooling_lane(self):
        self.assertEqual(lane_of("docs/ROADMAP.md"), "tooling")


if __name__ == "__main__":
    unittest.main()


class PruneDeadRawLinksTests(unittest.TestCase):
    def test_removes_only_dangling_symlinks_under_raw(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as wt, tempfile.TemporaryDirectory() as primary:
            raw = os.path.join(wt, "raw", "papers")
            os.makedirs(raw)
            real = os.path.join(primary, "ok.pdf")
            open(real, "w").close()
            open(os.path.join(raw, "regular.pdf"), "w").close()
            os.symlink(real, os.path.join(raw, "valid.pdf"))
            os.symlink(os.path.join(primary, "moved.pdf"), os.path.join(raw, "dead.pdf"))
            os.symlink(os.path.join(primary, "gone.pdf"), os.path.join(wt, "outside.pdf"))
            with mock.patch.object(ship, "is_linked_worktree", return_value=True):
                self.assertEqual(ship.prune_dead_raw_links(wt), 1)
            self.assertTrue(os.path.isfile(os.path.join(raw, "regular.pdf")))
            self.assertTrue(os.path.islink(os.path.join(raw, "valid.pdf")))
            self.assertFalse(os.path.lexists(os.path.join(raw, "dead.pdf")))
            self.assertTrue(os.path.islink(os.path.join(wt, "outside.pdf")))
            with mock.patch.object(ship, "is_linked_worktree", return_value=False):  # primary: untouched
                os.symlink("/nonexistent", os.path.join(raw, "dead2.pdf"))
                self.assertEqual(ship.prune_dead_raw_links(wt), 0)

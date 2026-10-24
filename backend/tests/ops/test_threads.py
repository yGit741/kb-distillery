#!/usr/bin/env python3
"""Tests for backend/src/kb/ops/threads.py (open work threads), backend/src/kb/ops/runlog.py (structured run log)
and backend/src/kb/ops/nightly_report.py (the nightly report Doc), on throwaway git repos."""
import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.paths import vault_root
ROOT = vault_root()

from kb.git import ship
from kb.ops import hygiene, nightly_report, runlog, threads
from kb.report import render_html, render_text
from tests.ops.test_hygiene import NOW, Repo, g

PR = {"number": 7, "branch": "infra/feat", "title": "feat(x): one", "age": "2h", "hours": 2}


def by_id(ts):
    return {t.id: t for t in ts}


class Threads(Repo):
    def collect(self, prs=()):
        now = datetime.datetime.now(datetime.timezone.utc)
        with patch.object(ship, "open_prs", return_value=list(prs)):
            return threads.collect(self.root, now)

    def test_clean_repo_has_no_threads(self):
        self.assertEqual(self.collect(), [])

    def test_pr_branch_and_worktree_join_into_one_thread(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        ts = self.collect([PR])
        self.assertEqual([t.id for t in ts], ["pr:7"])
        t = ts[0]
        self.assertEqual((t.kind, t.state, t.branch, t.path), ("pr", "active", "infra/feat", ".claude/worktrees/feat"))
        self.assertEqual(t.pieces["pr"], "#7")
        self.assertIn("cd .claude/worktrees/feat && pixi run ship -- merge", t.next)

    def test_old_pr_is_stale(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        t = self.collect([dict(PR, hours=24 * 9)])[0]
        self.assertEqual((t.state, t.status), ("stale", "warn"))

    def test_branch_without_pr(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        t = by_id(self.collect())["branch:infra/feat"]
        self.assertEqual(t.state, "active")
        self.assertIn("no PR yet", t.title)
        self.assertIn("pixi run ship -- pr", t.next)

    def test_just_started_branch_is_live_work_not_merged(self):
        path = self.worktree("fresh", "infra/fresh")
        with open(os.path.join(path, "meta.txt"), "w") as f:
            f.write("wip\n")
        t = by_id(self.collect())["branch:infra/fresh"]
        self.assertEqual((t.state, t.kind), ("active", "branch"))
        self.assertIn("nothing committed yet", t.title)
        self.assertEqual(hygiene.check_worktrees(self.root, NOW), [])     # and hygiene agrees

    def test_merged_leftover_worktree(self):
        path = self.worktree("feat", "infra/feat")
        self.commit("meta/x.py", "x = 1", "feat(x): one", cwd=path)
        self.merge_to_main("infra/feat")
        t = by_id(self.collect())["merged:infra/feat"]
        self.assertEqual((t.state, t.next), ("stale", threads.PRUNE_FIX))

    def test_unpushed_and_uncommitted_on_main(self):
        self.commit("wiki/a.md", "a", "kb(refine): a (kb-0.0.1)")
        with open(os.path.join(self.root, "wiki", "b.md"), "w") as f:
            f.write("b\n")
        ts = by_id(self.collect())
        self.assertEqual(ts["main:unpushed"].state, "blocked")
        self.assertEqual(ts["main:unpushed"].pieces["ahead"], 1)
        self.assertEqual(ts["dirty:knowledge"].notes, ["wiki/b.md"])
        order = [t.state for t in self.collect()]
        self.assertEqual(order, sorted(order, key=threads.STATE_RANK.get))   # blocked → stale → active

    def test_a_failing_collector_becomes_a_thread(self):
        def boom(root, now):
            raise RuntimeError("gh exploded")
        ts = threads.collect(self.root, NOW, collectors=[("prs", boom)])
        self.assertEqual([(t.kind, t.state) for t in ts], [("error", "blocked")])
        self.assertIn("gh exploded", ts[0].title)

    def test_age_label(self):
        self.assertEqual([threads.age_label(h) for h in (None, 0.2, 5, 50)], ["?", "12m", "5h", "2d"])


class RunLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_records_steps_and_reads_newest_first(self):
        for i in range(3):
            runlog.Run(self.tmp.name, now=NOW + datetime.timedelta(days=i)).step("sync", rc=0).set(notify="sent").finish("ok")
        runs = runlog.read(self.tmp.name)
        self.assertEqual([r["started"][:10] for r in runs], ["2026-10-24", "2026-10-23", "2026-10-22"])
        self.assertEqual(runs[0]["steps"][0]["name"], "sync")
        self.assertEqual((runs[0]["status"], runs[0]["notify"]), ("ok", "sent"))
        self.assertIn("duration", runs[0])

    def test_trim_and_corrupt_lines(self):
        for i in range(20):
            runlog.append(self.tmp.name, {"started": str(i)}, max_runs=8)
        with open(runlog.path(self.tmp.name), "a") as f:
            f.write("{not json\n")
        runs = runlog.read(self.tmp.name, n=100)
        self.assertLessEqual(len(runs), 10)
        self.assertEqual(runs[0]["started"], "19")

    def test_parse_transcript(self):
        text = ("=== Thu Oct 22 01:50:39 IDT 2026\nEverything up-to-date\n"
                "hygiene: 0 error(s), 4 warning(s) (9 checks, 4.7s)\nnotify: sent 'x' to me\n"
                "=== Thu Oct 22 22:00:05 IDT 2026\nhygiene: 2 error(s), 1 warning(s) (9 checks)\n"
                "notify: same report already sent at x — not resent\n"
                "=== Fri Oct 23 22:00:00 IDT 2026\nhygiene: clean (9 checks, 1.0s)\n")
        runs = runlog.parse_transcript(text)
        self.assertEqual([(r["status"], r.get("notify")) for r in runs],
                         [("warn", "sent"), ("error", "throttled"), ("ok", None)])
        self.assertEqual(runs[1]["hygiene"]["errors"], 2)
        self.assertTrue(runs[0]["started"].startswith("2026-10-22T01:50:39"))


class Report(unittest.TestCase):
    def thread(self, **kw):
        base = dict(id="pr:7", kind="pr", title="PR #7 feat(x): one", state="active", status="ok",
                    next="pixi run ship -- merge", age_hours=2, branch="infra/feat", path=".claude/worktrees/feat",
                    pieces={"pr": "#7", "branch": "infra/feat"})
        base.update(kw)
        return threads.Thread(**base)

    def build(self, findings=(), ts=(), sync=None):
        report = hygiene.Report(findings=list(findings), checks=["a"], started=NOW.isoformat())
        doc = nightly_report.build(ROOT, report, list(ts), now=NOW, sync=sync, version="kb-0.12.57",
                                   site={}, vault={"inbox": 3, "queued": 10, "partial": 1, "digested": 40},
                                   steps=[{"kind": "kb", "kb_version": "0.12.57", "op": "digest", "target": "paper-x",
                                           "short": "abc", "summary": ""}])
        return report, doc

    def test_clean_night(self):
        report, doc = self.build(ts=[self.thread()])
        self.assertEqual(doc.status, "ok")
        self.assertEqual(doc.sections[0].blocks[0].title, "All clear")
        self.assertEqual(nightly_report.subject(doc, report), "[thesis-kb] ✓ all clear · 1 open thread")
        self.assertNotIn("needs", [s.id for s in doc.sections])

    def test_findings_attach_to_their_thread_and_raise_its_colour(self):
        f = hygiene.Finding("warn", "dirty-worktree", "infra/feat at .claude/worktrees/feat: 2 uncommitted files", "x")
        loose = hygiene.Finding("error", "deploy-failed", "last deploy failed: fetch failed", "pixi run share -- deploy-main")
        report, doc = self.build([f, loose], [self.thread()])
        cards = [c for s in doc.sections if s.id == "threads" for b in s.blocks for c in b.items]
        self.assertEqual(cards[0].status, "warn")
        self.assertIn("2 uncommitted files", cards[0].notes[0])
        needs = [i for s in doc.sections if s.id == "needs" for b in s.blocks for i in b.items]
        self.assertEqual([i.label for i in needs], ["deploy-failed"])          # only the unattached one
        self.assertEqual(doc.status, "error")
        self.assertEqual(nightly_report.subject(doc, report),
                         "[thesis-kb] ✗ 1 thing needs you · deploy-failed, dirty-worktree")

    def test_failed_sync_leads_and_carries_the_log(self):
        report, doc = self.build(sync={"failed": True, "error": "Traceback …\nRuntimeError: push exploded"})
        self.assertEqual(doc.sections[0].blocks[0].title, "Nightly sync failed")
        needs = [i for s in doc.sections if s.id == "needs" for b in s.blocks for i in b.items]
        self.assertEqual(needs[0].detail, "RuntimeError: push exploded")
        report, doc = nightly_report.build(ROOT, report, [], now=NOW, sync={"failed": True, "error": "boom"},
                                           log_tail="\x1b[31mred line\x1b[0m\n", version="", site={}, vault={},
                                           steps=[]), None
        self.assertEqual(report.sections[-1].id, "log")
        self.assertEqual(report.sections[-1].blocks[0].text, "red line")

    def test_renders_in_both_formats(self):
        f = hygiene.Finding("warn", "stale-worktree", "infra/feat at .claude/worktrees/feat is merged into main", "x")
        _report, doc = self.build([f], [self.thread(state="stale", status="warn")])
        html, text = render_html.render(doc), render_text.render(doc)
        self.assertIn("PR #7 feat(x): one", html)
        self.assertIn("kb-0.12.57", text)
        self.assertNotIn("is merged into main", text)       # a restating finding adds no note
        json.dumps(doc.as_dict())


if __name__ == "__main__":
    unittest.main()

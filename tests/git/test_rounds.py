"""kb_distillery.git.rounds: open, tick on merge, status output, failures never break ship."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

from kb_distillery.git import events, git_guard, rounds, ship
from tests.git import test_ship
from tests.needs_git import needs_git

# issue body lives in $FAKE_GH_DIR/issue.md, issue comments in comments.txt; pr flow as in test_ship
FAKE_GH = r"""#!/bin/bash
d="$FAKE_GH_DIR"; echo "$*" >> "$d/calls.log"
[ -n "$FAKE_ISSUE_FAIL" ] && [ "$1" = "issue" ] && { echo "boom" >&2; exit 1; }
case "$1 $2" in
  "issue create")
    while [ $# -gt 0 ]; do [ "$1" = "--body" ] && printf '%s' "$2" > "$d/issue.md"; shift; done
    echo "https://github.com/o/r/issues/42"; exit 0;;
  "issue view")
    python3 -c 'import json,sys; print(json.dumps({"body": open(sys.argv[1]).read()}))' "$d/issue.md"; exit 0;;
  "issue edit")
    while [ $# -gt 0 ]; do [ "$1" = "--body" ] && printf '%s' "$2" > "$d/issue.md"; shift; done; exit 0;;
  "issue comment")
    while [ $# -gt 0 ]; do [ "$1" = "--body" ] && echo "$2" >> "$d/comments.txt"; shift; done; exit 0;;
  "pr view")
    [ -f "$d/created" ] || exit 1
    state=OPEN; [ -f "$d/merged" ] && state=MERGED
    echo '{"number": 7, "url": "https://example/pr/7", "title": "feat(ops): add thing", "state": "'"$state"'", "labels": [], "body": "Round: #42\n", "mergeable": "MERGEABLE", "autoMergeRequest": {"enabledAt": "now"}, "statusCheckRollup": []}'; exit 0;;
  "pr create") touch "$d/created"; echo "https://example/pr/7"; exit 0;;
  "pr merge") touch "$d/merged"; exit 0;;     # --auto: GitHub merges once CI is green (here: at once)
esac
[ "$1" = "api" ] && { cat "$d/comments.txt" 2>/dev/null; exit 0; }
exit 0
"""


class PureTests(unittest.TestCase):
    def test_body_and_tick(self):
        body = rounds.render_body("Phase 2", ["a-b", "c"])
        self.assertIn(rounds.MARKER, body)
        self.assertEqual(rounds.checklist(body), [("a-b", False, ""), ("c", False, "")])
        ticked = rounds.tick(body, "c", 9)
        self.assertEqual(rounds.checklist(ticked), [("a-b", False, ""), ("c", True, "(#9)")])
        self.assertEqual(rounds.tick(ticked, "c", 9), ticked)            # idempotent (deployed after merged)
        extra = rounds.tick(body, "late", 3)                              # unknown feature gets appended
        self.assertIn("- [x] late (#3)", extra)

    def test_round_from_pr_body(self):
        self.assertEqual(rounds.round_from_pr_body("Round: #12\n\n## Summary"), 12)
        self.assertIsNone(rounds.round_from_pr_body("## Summary"))
        self.assertIn("Round: #5", ship.pr_body(["feat(x): y"], round_no=5))
        self.assertNotIn("Round:", ship.pr_body(["feat(x): y"]))

    def test_guard(self):
        self.assertTrue(git_guard.is_allowlisted('pixi run ship -- round open "x" --features a,b'))
        self.assertTrue(git_guard.is_allowlisted("pixi run ship -- round status 4"))
        self.assertTrue(git_guard.violation("gh issue edit 4 --body x"))


@needs_git
class RoundFlowTests(unittest.TestCase):
    setUp = test_ship.PrFlowTests.setUp
    tearDown = test_ship.PrFlowTests.tearDown
    _write = staticmethod(test_ship.PrFlowTests._write)
    _start = test_ship.PrFlowTests._start

    def _fake(self):
        with open(os.path.join(self.ghdir, "gh"), "w") as f:
            f.write(FAKE_GH)

    def _open(self):
        self._fake()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ship.main(["round", "open", "Phase 2", "--features", "ops-thing,other"]), 0)
        self.assertTrue(buf.getvalue().startswith("#42 Phase 2"))
        calls = open(os.path.join(self.ghdir, "calls.log")).read()
        self.assertIn("label create round", calls)
        self.assertIn("--label round", calls)

    def _issue(self):
        return open(os.path.join(self.ghdir, "issue.md")).read()

    def test_open_start_merge_ticks_and_status(self):
        self._open()
        self.assertEqual(ship.cmd_start("ops-thing", worktree=True, root=self.repo, round_no=42), 0)
        wt = os.path.join(self.repo, ".claude", "worktrees", "ops-thing")
        self.assertEqual(rounds.branch_round("infra/ops-thing", wt), 42)
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ship.cmd_pr(root=wt, gates=False), 0)
            self.assertEqual(ship.cmd_merge(root=wt, gates=False), 0)
        calls = open(os.path.join(self.ghdir, "calls.log")).read()
        self.assertIn("Round: #42", calls)                               # pr body
        self.assertEqual(rounds.checklist(self._issue()),
                         [("ops-thing", True, "(#7)"), ("other", False, "")])
        evs = [e["event"] for e in events.read(42)]
        self.assertEqual(evs, ["claimed", "merged"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ship.main(["round", "status", "42"]), 0)
        out = buf.getvalue().splitlines()
        self.assertEqual(out[0], "round #42: 1/2 done")
        self.assertRegex(out[1], r"^\[x\] ops-thing +merged \S+ pr=#7$")
        self.assertRegex(out[2], r"^\[ \] other +-$")

    def test_round_failures_never_break_merge(self):
        self._open()
        wt = os.path.join(self.repo, ".claude", "worktrees", "ops-thing")
        ship.cmd_start("ops-thing", worktree=True, root=self.repo, round_no=42)
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        with patch.dict(os.environ, {"FAKE_ISSUE_FAIL": "1"}), contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing",
                                            root=wt, gates=False), 0)
        self.assertIn("note: round #42", buf.getvalue())
        self.assertEqual(test_ship._g(self.repo, "log", "-1", "--format=%s"), "feat(ops): add thing (#3)")

    def test_no_round_no_issue_calls(self):
        self._fake()
        wt = self._start()
        self._write(wt, "meta/tool.py")
        ship.cmd_commit("feat(ops): add thing", root=wt, gates=False)
        with contextlib.redirect_stdout(io.StringIO()):
            ship.cmd_merge(local=True, pr_number=3, title="feat(ops): add thing", root=wt, gates=False)
        log = os.path.join(self.ghdir, "calls.log")
        calls = open(log).read() if os.path.exists(log) else ""
        self.assertNotIn("issue", calls)


if __name__ == "__main__":
    unittest.main()

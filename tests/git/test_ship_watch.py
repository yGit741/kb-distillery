"""`ship merge` watching the PR GitHub merges: every exit of `_watch_merge` and the post-merge hand-off, with a faked
`gh pr view` (no network, no sleeping)."""
import contextlib
import io
import unittest
from unittest.mock import patch

from kb_distillery.git import ship

ARGS = dict(pr_number=7, branch="infra/x", feature="x", primary="/p", root="/r", round_no=None, kind=None,
            approved_head=None, detail="", no_push=False)


def _open(**over):
    info = {"number": 7, "state": "OPEN", "headRefOid": "abc1234", "autoMergeRequest": {"enabledAt": "t"},
            "statusCheckRollup": [], "mergeable": "MERGEABLE"}
    info.update(over)
    return info


class WatchTests(unittest.TestCase):
    def _watch(self, views, queue_state=lambda n, r: False, **over):
        """Run the watch over a scripted sequence of `gh pr view` answers; returns (rc, printed, gh calls, events)."""
        calls, posted, after = [], [], []
        seq = iter(views)
        clock = {"t": 0.0}

        def fake_view(ref, root, fields=None):
            return next(seq)

        def fake_gh(args, root=None, user=False):
            calls.append(list(args))
            return ship.subprocess.CompletedProcess(args, 0, "", "")

        def fake_sleep(s):
            clock["t"] += s

        def fake_after(*a, **k):
            after.append(a)
            return 0

        out = io.StringIO()
        with patch.object(ship, "_pr_info", fake_view), patch.object(ship, "gh", fake_gh), \
             patch.object(ship.events, "post", lambda *a, **k: posted.append((a[1], k))), \
             patch.object(ship, "_after_merged", fake_after), contextlib.redirect_stdout(out):
            rc = ship._watch_merge(**{**ARGS, **over}, sleep=fake_sleep, clock=lambda: clock["t"], queue_state=queue_state)
        return rc, out.getvalue(), calls, posted, after

    def test_merged_hands_over_to_the_post_merge_steps(self):
        rc, out, calls, posted, after = self._watch([_open(), _open(), _open(state="MERGED")])
        self.assertEqual(rc, 0)
        self.assertEqual(len(after), 1)
        self.assertIn("waiting for CI and the merge queue", out)
        self.assertEqual(out.count("waiting for CI"), 1)                 # announced once, not every poll

    def test_a_red_required_check_exits_with_the_names_and_an_event(self):
        views = [_open(statusCheckRollup=[{"name": "tests (rest)", "status": "COMPLETED", "conclusion": "FAILURE"},
                                           {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
                                           {"context": "gitleaks", "state": "SUCCESS"}])]
        rc, out, calls, posted, after = self._watch(views)
        self.assertEqual(rc, 1)
        self.assertIn("tests (rest)", out)
        self.assertNotIn("lint,", out)
        self.assertEqual([p[0] for p in posted], ["checks-failed"])
        self.assertEqual(posted[0][1].get("stage"), "ci")
        self.assertEqual(after, [])

    def test_leaving_the_queue_is_reported_after_two_polls(self):
        rc, out, *_ = self._watch([_open(autoMergeRequest=None)] * 2 + [_open(state="MERGED")])
        self.assertEqual(rc, 1)
        self.assertIn("left the merge queue", out)

    def test_one_poll_without_auto_merge_is_not_enough(self):
        """Entering the queue clears autoMergeRequest for a moment; a single such answer must not end the watch."""
        rc, out, calls, posted, after = self._watch([_open(autoMergeRequest=None), _open(state="MERGED")])
        self.assertEqual(rc, 0)
        self.assertEqual(len(after), 1)

    def test_a_pr_in_the_queue_is_waited_for_even_without_auto_merge(self):
        views = [_open(autoMergeRequest=None)] * 4 + [_open(state="MERGED")]
        rc, out, calls, posted, after = self._watch(views, queue_state=lambda n, r: True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(after), 1)

    def test_an_unknown_queue_answer_keeps_waiting(self):
        views = [_open(autoMergeRequest=None)] * 4 + [_open(state="MERGED")]
        rc, *_ = self._watch(views, queue_state=lambda n, r: None)
        self.assertEqual(rc, 0)

    def test_a_cancelled_run_is_not_red(self):
        views = [_open(statusCheckRollup=[{"name": "tests (rest)", "conclusion": "CANCELLED"}]), _open(state="MERGED")]
        rc, *_ = self._watch(views)
        self.assertEqual(rc, 0)

    def test_queue_state_reads_graphql(self):
        answers = {"in": '{"data": {"repository": {"pullRequest": {"isInMergeQueue": true, "mergeQueueEntry": {"state": "QUEUED"}}}}}',
                   "out": '{"data": {"repository": {"pullRequest": {"isInMergeQueue": false, "mergeQueueEntry": null}}}}'}
        for key, want in (("in", True), ("out", False)):
            fake = lambda args, root=None, user=False, k=key: ship.subprocess.CompletedProcess(args, 0, answers[k], "")
            with patch.object(ship, "gh", fake):
                self.assertIs(ship._queue_state(7, "/r"), want)
        broken = lambda args, root=None, user=False: ship.subprocess.CompletedProcess(args, 1, "", "boom")
        with patch.object(ship, "gh", broken):
            self.assertIsNone(ship._queue_state(7, "/r"))

    def test_an_approved_head_that_moved_disarms_auto_merge(self):
        rc, out, calls, posted, after = self._watch([_open(headRefOid="def5678")], approved_head="abc1234")
        self.assertEqual(rc, 1)
        self.assertIn(["pr", "merge", "7", "--disable-auto"], calls)
        self.assertIn("re-approve", out)

    def test_closed_without_merging(self):
        rc, out, *_ = self._watch([_open(state="CLOSED")])
        self.assertEqual(rc, 1)
        self.assertIn("closed without merging", out)

    def test_times_out_and_leaves_auto_merge_armed(self):
        with patch.dict(ship.os.environ, {ship.MERGE_WATCH_ENV: "60"}):
            rc, out, calls, *_ = self._watch([_open()] * 10)
        self.assertEqual(rc, 1)
        self.assertIn("has not merged after 1 min", out)
        self.assertNotIn(["pr", "merge", "7", "--disable-auto"], calls)   # a timeout never disarms it

    def test_check_states_reads_check_runs_and_commit_statuses(self):
        info = {"statusCheckRollup": [{"name": "a", "conclusion": "SUCCESS"}, {"context": "b", "state": "FAILURE"}, {}]}
        self.assertEqual(ship._check_states(info), [("a", "SUCCESS"), ("b", "FAILURE"), ("?", "")])

    def test_auto_merge_refusals_are_recognised(self):
        self.assertTrue(ship._auto_merge_unavailable("X Pull request #7 is in clean status"))
        self.assertTrue(ship._auto_merge_unavailable("GraphQL: Auto-merge is not allowed for this repository"))
        self.assertFalse(ship._auto_merge_unavailable("GraphQL: Base branch was modified"))


if __name__ == "__main__":
    unittest.main()

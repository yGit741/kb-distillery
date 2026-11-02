"""kb_distillery.git.events: format round-trip, reader ignores human comments, posting is best-effort."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.git import events, git_guard

FAKE_GH = """#!/bin/bash
echo "$*" >> "$FAKE_GH_DIR/calls.log"
if [ "$1 $2" = "pr comment" ]; then
  [ -n "$FAKE_COMMENT_FAIL" ] && { echo "boom" >&2; exit 1; }
  exit 0
fi
if [ "$1" = "api" ]; then
  cat "$FAKE_GH_DIR/comments.txt"; exit 0
fi
exit 0
"""


class EventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        gh = os.path.join(self.dir, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.env = patch.dict(os.environ, {"GH_BIN": gh, "FAKE_GH_DIR": self.dir})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def calls(self):
        p = os.path.join(self.dir, "calls.log")
        return open(p).read().splitlines() if os.path.exists(p) else []

    def test_round_trip(self):
        line = events.format_event("claimed", "abcdef1234", ts="2026-10-25T03:14Z",
                                   branch="infra/x", dirs="backend,meta")
        self.assertEqual(line, "kb-event v1 · claimed · abcdef1 · branch=infra/x dirs=backend,meta · 2026-10-25T03:14Z")
        e = events.parse_line(line)
        self.assertEqual(e, {"event": "claimed", "sha": "abcdef1", "ts": "2026-10-25T03:14Z",
                             "kv": {"branch": "infra/x", "dirs": "backend,meta"}})

    def test_values_cannot_break_the_line(self):
        e = events.parse_line(events.format_event("checks-passed", "", skip_checks="no node · here"))
        self.assertEqual(e["kv"], {"skip_checks": "no_node_-_here"})
        self.assertEqual(e["sha"], "")

    def test_unknown_event_rejected(self):
        with self.assertRaises(ValueError):
            events.format_event("exploded")

    def test_reader_ignores_human_comments(self):
        with open(os.path.join(self.dir, "comments.txt"), "w") as f:
            f.write("LGTM!\n")
            f.write(events.format_event("queued", "1234567", branch="infra/x") + "\n")
            f.write("> kb-event v1 · merged · quoted by a human\n")
            f.write("kb-event v1 is cool\n")
            f.write(events.format_event("merged", "7654321") + "\n")
        evs = events.read(5)
        self.assertEqual([e["event"] for e in evs], ["queued", "merged"])
        self.assertIn("api repos/{owner}/{repo}/issues/5/comments", self.calls()[0])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            events.cmd_events(5)
        self.assertIn("queued", buf.getvalue())

    def test_post_ok(self):
        self.assertTrue(events.post(5, "deployed", "abc", version="v1"))
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue(self.calls()[0].startswith("pr comment 5 --body kb-event v1 · deployed"))

    def test_post_failure_retries_once_and_never_raises(self):
        with patch.dict(os.environ, {"FAKE_COMMENT_FAIL": "1"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(events.post(5, "merged", "abc"))
        self.assertEqual(len(self.calls()), 2)

    def test_post_missing_binary_never_raises(self):
        with patch.dict(os.environ, {"GH_BIN": "/nonexistent/gh"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(events.post(5, "merged"))

    def test_no_pr_no_call(self):
        self.assertFalse(events.post(None, "queued"))
        self.assertEqual(self.calls(), [])

    def test_guard_still_blocks_direct_comment(self):
        self.assertTrue(git_guard.violation("gh pr comment 5 --body 'kb-event v1 · merged'"))
        self.assertTrue(git_guard.is_allowlisted("pixi run ship -- events 5"))


if __name__ == "__main__":
    unittest.main()

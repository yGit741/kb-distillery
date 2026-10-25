#!/usr/bin/env python3
"""Tests for backend/src/kb/git/merge_nudge.py — the Stop hook that keeps an open PR from going unmentioned."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.paths import vault_root
ROOT = vault_root()

from kb.git import merge_nudge

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

FAKE_GH = """#!/bin/bash
# fake gh: state comes from $FAKE_PR_STATE (OPEN / MERGED / none)
[ "$FAKE_PR_STATE" = "none" ] && exit 1
echo '{"number": 16, "title": "'"$FAKE_PR_TITLE"'", "url": "https://example/pr/16", "state": "'"$FAKE_PR_STATE"'", "labels": ['"$FAKE_PR_LABELS"']}'
"""


def g(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=dict(os.environ, **ENV))


class MergeNudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        g(self.repo, "init", "-q", "-b", "main")
        g(self.repo, "config", "user.name", "t")
        g(self.repo, "config", "user.email", "t@t")
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("x\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-q", "-m", "chore(git): init (retro)")
        gh = os.path.join(self.tmp.name, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.env = patch.dict(os.environ, {"GH_BIN": gh, "FAKE_PR_STATE": "OPEN", "FAKE_PR_TITLE": "",
                                           "FAKE_PR_LABELS": '{"name": "hold"}', **ENV})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _transcript(self, *turns):
        """turns: ("user", text) | ("tool", text) | ("assistant", text) → JSONL path."""
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w") as f:
            for kind, text in turns:
                if kind == "tool":
                    o = {"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}
                elif kind == "user":
                    o = {"type": "user", "message": {"content": text}}
                else:
                    o = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
                f.write(json.dumps(o) + "\n")
        return path

    def _payload(self, transcript, **extra):
        return {"cwd": self.repo, "transcript_path": transcript, **extra}

    def test_silent_on_main(self):
        t = self._transcript(("user", "hi"), ("assistant", "PR is open"))
        self.assertIsNone(merge_nudge.decide(self._payload(t)))

    def test_blocks_once_with_the_nudge_line_when_pr_is_open(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "fix it"), ("assistant", "Opened PR #16."),
                             ("tool", "ok"), ("assistant", "Done, all gates green."))
        out = merge_nudge.decide(self._payload(t))
        self.assertEqual(out["decision"], "block")
        self.assertIn('Awaiting your merge: #16 https://example/pr/16 — approve the review on GitHub, '
                      'or run `! pixi run ship -- approve 16`', out["reason"])
        # second pass of the same stop: never loops
        self.assertIsNone(merge_nudge.decide(self._payload(t, stop_hook_active=True)))

    def test_silent_when_reply_already_carries_the_nudge(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "fix it"), ("assistant", "Done.\n\nAwaiting your merge: #16 https://example/pr/16"))
        self.assertIsNone(merge_nudge.decide(self._payload(t)))

    def test_new_review_wording_of_the_nudge_line_is_accepted(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        pr = {"number": 16, "title": "", "url": "https://example/pr/16"}
        t = self._transcript(("user", "fix it"), ("assistant", "Done.\n\n" + merge_nudge.nudge_line(pr)))
        self.assertIn("approve the review on GitHub", merge_nudge.nudge_line(pr))
        self.assertIsNone(merge_nudge.decide(self._payload(t)))

    def test_nudge_from_an_earlier_reply_does_not_count(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "fix it"), ("assistant", "Awaiting your merge: #16 …"),
                             ("user", "thanks, one more thing"), ("assistant", "Changed it."))
        self.assertEqual(merge_nudge.decide(self._payload(t))["decision"], "block")

    def test_silent_when_the_pr_is_not_held(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "fix it"), ("assistant", "Opened PR #16, merging it."))
        with patch.dict(os.environ, {"FAKE_PR_LABELS": '{"name": "bug"}'}):
            self.assertIsNone(merge_nudge.decide(self._payload(t)))

    def test_silent_when_pr_merged_or_missing_or_gh_broken(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "x"), ("assistant", "y"))
        for state in ("MERGED", "none"):
            with patch.dict(os.environ, {"FAKE_PR_STATE": state}):
                self.assertIsNone(merge_nudge.decide(self._payload(t)), state)
        with patch.dict(os.environ, {"GH_BIN": "/nonexistent/gh"}):
            self.assertIsNone(merge_nudge.decide(self._payload(t)))

    def test_cli_prints_json_only_when_blocking(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        t = self._transcript(("user", "x"), ("assistant", "y"))
        cp = subprocess.run([sys.executable, "-m", "kb.git.merge_nudge"],
                            input=json.dumps(self._payload(t)), capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(json.loads(cp.stdout)["decision"], "block")
        cp = subprocess.run([sys.executable, "-m", "kb.git.merge_nudge"],
                            input=json.dumps({"cwd": self.repo, "transcript_path": t, "stop_hook_active": True}),
                            capture_output=True, text=True)
        self.assertEqual((cp.returncode, cp.stdout.strip()), (0, ""))

    def test_nudge_must_name_the_pr_title(self):
        g(self.repo, "checkout", "-q", "-b", "infra/thing")
        with patch.dict(os.environ, {"FAKE_PR_TITLE": "feat(ops): add thing"}):
            bare = self._transcript(("user", "fix it"), ("assistant", "Awaiting your merge: #16 https://example/pr/16"))
            out = merge_nudge.decide(self._payload(bare))
            self.assertIn("#16 feat(ops): add thing https://example/pr/16", out["reason"])
            named = self._transcript(("user", "fix it"),
                                     ("assistant", "Awaiting your merge: #16 feat(ops): add thing https://example/pr/16"))
            self.assertIsNone(merge_nudge.decide(self._payload(named)))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for backend/src/kb/git/git_guard.py and its .cursor/hooks/block-git-write.sh wrapper."""
import json
import os
import subprocess
import sys
import unittest

from kb.paths import vault_root
ROOT = vault_root()

from kb.git import git_guard

HOOK = os.path.join(ROOT, ".cursor", "hooks", "block-git-write.sh")


def run_hook(payload):
    proc = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=ROOT)
    return proc.returncode, proc.stdout, proc.stderr


class ViolationTests(unittest.TestCase):
    BLOCKED = [
        "git commit -m x",
        "git push origin main",
        "git -C . commit -m x",
        "git -c user.name=x commit -m y",
        "git merge infra/x",
        "git rebase main",
        "git reset --hard HEAD~1",
        "git revert abc",
        "git tag snap-1",
        "git tag -a kb-1.0.0 -m x",
        "git tag -d kb-1.0.0",
        "git branch -D old",
        "git checkout -- wiki/a.md",
        "git checkout .",
        "git stash",
        "git config core.hooksPath /dev/null",
        "git status && git commit -m x",
        "pixi run ship && git push --force",
        "pixi run ship; git push",
        "pixi run ship\ngit push",
        "echo $(git commit -m x)",
        "echo `git push`",
        "cd /tmp && /usr/bin/git push",
        "gh pr create --fill",
        "gh pr merge 3 --squash",
        "gh api repos/x/y/pulls -X POST",
        "gh api repos/x/y -f name=z",
        "gh repo edit --enable-squash-merge=false",
        "git log | xargs git commit",
    ]
    ALLOWED = [
        "git status",
        "git log --oneline -5",
        "git diff main",
        "git show HEAD",
        "git for-each-ref refs/tags",
        "git tag",
        "git tag -l 'kb-*'",
        "git tag --list",
        "git branch",
        "git branch -a",
        "git checkout infra/x",
        "git -C repo log",
        "gh pr view 3",
        "gh pr list",
        "gh api repos/x/y",
        "ls -la",
        "pixi run lint",
        "pixi run ship -- 'fix(git): push bug'",
        "pixi run ship -- commit 'feat(ops): git commit wrapper'",
        "pixi run ops -- undo abc123",
        "pixi run daily-sync",
        "pixi run curate-history -- --dry-run",
        "python3 -m kb.git.ship --status",
        "python3 -m kb.ops log -n 5",
        "/opt/x/bin/python3 -m kb.git.curate_history --plan p.json",
        "grep -n 'git push' backend/src/kb/git/ship.py",
    ]

    def test_blocked(self):
        for cmd in self.BLOCKED:
            self.assertIsNotNone(git_guard.violation(cmd), cmd)

    def test_allowed(self):
        for cmd in self.ALLOWED:
            self.assertIsNone(git_guard.violation(cmd), cmd)

    def test_no_verify_blocked_even_on_readonly(self):
        self.assertIsNotNone(git_guard.violation("git log --no-verify"))

    def test_allowlist_requires_single_invocation(self):
        self.assertTrue(git_guard.is_allowlisted("pixi run ship -- start x"))
        self.assertFalse(git_guard.is_allowlisted("pixi run ship -- x | tee log"))
        self.assertFalse(git_guard.is_allowlisted("pixi run ship > out.txt"))
        self.assertFalse(git_guard.is_allowlisted("pixi run lint"))


class HookWrapperTests(unittest.TestCase):
    def test_claude_blocked_exit_2(self):
        code, _, err = run_hook({"tool_name": "Bash", "tool_input": {"command": "git push"}})
        self.assertEqual(code, 2)
        self.assertIn("blocked", err)

    def test_claude_allowed(self):
        code, _, _ = run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}})
        self.assertEqual(code, 0)

    def test_cursor_deny_json(self):
        code, out, _ = run_hook({"command": "pixi run ship && git push --force"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["permission"], "deny")

    def test_cursor_allow_json(self):
        code, out, _ = run_hook({"command": "pixi run ops -- status"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["permission"], "allow")


if __name__ == "__main__":
    unittest.main()

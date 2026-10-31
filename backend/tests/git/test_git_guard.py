#!/usr/bin/env python3
"""Tests for backend/src/kb/git/git_guard.py and its tools/hooks/block-git-write.sh wrapper."""
import json
import os
import subprocess
import sys
import unittest

from kb.paths import CHECKOUT_ROOT as ROOT   # the hook script is code

from kb.git import git_guard

HOOK = os.path.join(ROOT, "tools", "hooks", "block-git-write.sh")


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
        "pixi run ship -- approve 12",
        "python3 -m kb.git.ship approve 12",
        "python3 backend/src/kb/git/ship.py approve 12",
        "gh issue edit 12 --remove-label hold",
        "gh label delete hold --yes",
        "gh auth login --with-token",
        "gh auth switch -u other",
        "gh auth token",
        "gh auth refresh -s repo",
        "gh auth setup-git",
        "gh auth",
        "gh pr review 3 --approve",
        "gh pr ready 3",
        "gh pr edit 3 --remove-label hold",
        "gh pr edit 3 --add-label hold",
        "security find-generic-password -s gh -w",
        "/usr/bin/security find-internet-password -s github.com",
        "security dump-keychain",
        "security -v find-generic-password -s gh -w",
        "gh -R owner/repo auth token",
        "gh --repo x pr edit 3 --remove-label hold",
        "security export -k login.keychain",
        "cat ~/.config/kb-agents/app.pem",
        "head -1 /Users/x/.config/kb-agents/key.pem",
        "less $HOME/.config/kb-agents/key.pem",
        "cp ~/.config/kb-agents/key.pem /tmp/k",
        "python3 -c \"print(open('/Users/x/.config/kb-agents/key.pem').read())\"",
        "pixi run ship -- pr --notes ~/.config/kb-agents/key.pem",
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
        "gh auth status",
        "pixi run ship -- pr --hold",
        "pixi run ship -- pr --hold --title 'feat(guard): x'",
        "security list-keychains",
        "grep -rn 'kb-agents/' meta/docs",
        "grep -rn security backend/",
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

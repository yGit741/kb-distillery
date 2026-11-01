#!/usr/bin/env python3
"""Tests for src/kb_distillery/git/guard.py — Claude Code and Cursor preToolUse stdin shapes."""
import json
import os
import subprocess
import sys
import unittest

from kb_distillery.paths import vault_root
ROOT = vault_root()
GUARD = ["-m", "kb_distillery.git.guard"]


def run_guard(payload, env=None):
    """Run guard.py with JSON stdin; return (exit_code, stdout, stderr)."""
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("CLAUDE_PROJECT_DIR", ROOT)
    proc = subprocess.run(
        [sys.executable, *GUARD],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=merged,
    )
    return proc.returncode, proc.stdout, proc.stderr


class GuardMainTests(unittest.TestCase):
    def test_claude_write_to_raw_blocked(self):
        path = os.path.join(ROOT, "raw", "foo.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)

    def test_cursor_strreplace_valid_wiki_allowed(self):
        path = os.path.join(ROOT, "wiki", "test-guard-fixture.md")
        code, out, err = run_guard({
            "hook_event_name": "preToolUse",
            "tool_name": "StrReplace",
            "tool_input": {"path": path, "old_string": "a", "new_string": "b"},
            "cwd": ROOT,
        })
        self.assertEqual(code, 0)
        self.assertIn("allow", out)

    def test_cursor_write_to_index_blocked(self):
        path = os.path.join(ROOT, "index.md")
        code, out, err = run_guard({
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": path, "content": "x"},
            "cwd": ROOT,
        })
        self.assertEqual(code, 2)
        self.assertIn("generated", err.lower())
        data = json.loads(out.strip())
        self.assertEqual(data["permission"], "deny")

    def test_worktree_paths_are_judged_inside_the_worktree(self):
        wt = os.path.join(ROOT, ".claude", "worktrees", "feature-x")
        code, out, err = run_guard({
            "tool_name": "Edit",
            "tool_input": {"file_path": os.path.join(wt, ".claude", "skills", "x", "SKILL.md"),
                           "old_string": "a", "new_string": "b"},
            "cwd": ROOT,
        })
        self.assertEqual(code, 0, err)
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": os.path.join(wt, "raw", "foo.md"), "content": "x"},
            "cwd": ROOT,
        })
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)

    def test_read_tool_skipped(self):
        code, out, err = run_guard({
            "tool_name": "Read",
            "tool_input": {"path": os.path.join(ROOT, "wiki", "x.md")},
        })
        self.assertEqual(code, 0)

    def test_write_without_path_fail_closed(self):
        code, out, err = run_guard({
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {},
            "cwd": ROOT,
        })
        self.assertEqual(code, 2)
        self.assertIn("could not parse", err.lower())

    def test_write_root_canvas_blocked(self):
        path = os.path.join(ROOT, "Untitled.canvas")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "{}"},
        })
        self.assertEqual(code, 2)
        self.assertIn("vault root", err.lower())

    def test_write_clippings_blocked(self):
        path = os.path.join(ROOT, "Clippings", "clip.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 2)
        self.assertIn("unexpected location", err.lower())

    def test_write_pixi_toml_allowed(self):
        path = os.path.join(ROOT, "pixi.toml")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "[project]\n"},
        })
        self.assertEqual(code, 0)

    def test_ingest_session_locks_wiki_path(self):
        ingest_dir = os.path.join(ROOT, "meta", ".ingest", "testsha")
        session_path = os.path.join(ingest_dir, "session.json")
        os.makedirs(ingest_dir, exist_ok=True)
        locked = "wiki/locked-by-ingest.md"
        try:
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "open",
                    "sha1": "testsha",
                    "raw": "raw/papers/test.pdf",
                    "new_files": [locked],
                    "modified_files": [],
                }, f)
            path = os.path.join(ROOT, locked.replace("/", os.sep))
            code, out, err = run_guard({
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "x"},
            })
            self.assertEqual(code, 2)
            self.assertIn("locked by ingest", err)
        finally:
            if os.path.isfile(session_path):
                os.remove(session_path)
            if os.path.isdir(ingest_dir):
                os.rmdir(ingest_dir)

    def test_write_parsed_sidecar_allowed(self):
        path = os.path.join(ROOT, "raw", "emails", "2021-06-13-test-thread", "parsed.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 0)

    def test_write_raw_mail_thread_still_blocked(self):
        path = os.path.join(ROOT, "raw", "emails", "2021-06-13-test-thread", "thread.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)

    def test_write_inbox_parsed_blocked(self):
        path = os.path.join(ROOT, "raw", "inbox", "parsed.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)

    def test_write_papers_parsed_blocked(self):
        path = os.path.join(ROOT, "raw", "papers", "misc", "parsed.md")
        code, out, err = run_guard({
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        })
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)


class OpsGuardTests(unittest.TestCase):
    """Free-form wiki writes need an open ops session (warn by default, block in strict mode).

    Runs against a throwaway vault so the result never depends on the real checkout's branch.
    """

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "wiki"))
        self.payload = {"tool_name": "Write", "cwd": self.root,
                        "tool_input": {"file_path": os.path.join(self.root, "wiki", "x.md"), "content": "x"}}

    def tearDown(self):
        self.tmp.cleanup()

    def _guard(self, strict):
        return run_guard(self.payload, env={"KB_OPS_STRICT": strict, "CLAUDE_PROJECT_DIR": self.root})

    def _branch(self, name):
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        with open(os.path.join(self.root, ".git", "HEAD"), "w") as f:
            f.write(f"ref: refs/heads/{name}\n")

    def test_warn_mode_allows_with_hint(self):
        code, _, err = self._guard("0")
        self.assertEqual(code, 0)
        self.assertIn("ops -- begin", err)

    def test_strict_mode_blocks_without_session(self):
        code, _, err = self._guard("1")
        self.assertEqual(code, 2)
        self.assertIn("no open operation", err)

    def test_strict_mode_allows_with_session(self):
        current = os.path.join(self.root, "meta", ".ops", "current.json")
        os.makedirs(os.path.dirname(current))
        with open(current, "w") as f:
            json.dump({"op": "refine", "target": "x"}, f)
        code, _, err = self._guard("1")
        self.assertEqual(code, 0, err)

    def test_infra_branch_flags_wiki_writes(self):
        self._branch("infra/x")
        code, _, err = self._guard("1")
        self.assertEqual(code, 2)
        self.assertIn("infra/x", err)


class GuardSubfolderCwdTests(unittest.TestCase):
    """A shell standing in a subfolder of the checkout must not turn that subfolder into the root."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.realpath(self.tmp.name)
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, "web", "src"))
        os.makedirs(os.path.join(self.repo, "raw"))

    def guard(self, rel, cwd):
        return run_guard({"tool_name": "Write", "cwd": os.path.join(self.repo, cwd) if cwd else self.repo,
                          "tool_input": {"file_path": os.path.join(self.repo, rel), "content": "x"}},
                         env={"CLAUDE_PROJECT_DIR": self.repo})

    def test_a_frontend_file_is_allowed_from_inside_frontend(self):
        code, _, err = self.guard("web/src/x.ts", "web")
        self.assertEqual(code, 0, err)

    def test_same_verdict_from_the_top_and_from_a_subfolder(self):
        self.assertEqual(self.guard("web/src/x.ts", "")[0], self.guard("web/src/x.ts", "web/src")[0])

    def test_raw_is_still_blocked_from_a_subfolder(self):
        code, _, err = self.guard("raw/foo.md", "web")
        self.assertEqual(code, 2)
        self.assertIn("raw/", err)

    def test_a_kb_nested_in_the_repo_stays_its_own_root(self):
        kb = os.path.join(self.repo, "examples", "demo")
        os.makedirs(os.path.join(kb, "raw"))
        with open(os.path.join(kb, "kb.toml"), "w") as f:
            f.write('[kb]\nid = "demo"\n')
        code, _, err = run_guard({"tool_name": "Write", "cwd": kb,
                                  "tool_input": {"file_path": os.path.join(kb, "raw", "foo.md"), "content": "x"}},
                                 env={"CLAUDE_PROJECT_DIR": self.repo})
        self.assertEqual(code, 2)                                      # raw/ inside the kb is still immutable
        self.assertIn("raw/", err)

    def test_the_project_dir_setting_is_used_as_given(self):
        kb = os.path.join(self.repo, "examples", "demo")
        os.makedirs(os.path.join(kb, "raw"))
        code, _, err = run_guard({"tool_name": "Write",
                                  "tool_input": {"file_path": os.path.join(kb, "raw", "foo.md"), "content": "x"}},
                                 env={"CLAUDE_PROJECT_DIR": kb})
        self.assertEqual(code, 2, err)

    def test_a_path_outside_the_checkout_is_not_judged(self):
        other = os.path.join(os.path.dirname(self.repo), "elsewhere.md")
        code, _, _ = run_guard({"tool_name": "Write", "cwd": os.path.join(self.repo, "web"),
                                "tool_input": {"file_path": other, "content": "x"}}, env={"CLAUDE_PROJECT_DIR": self.repo})
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for backend/src/kb/git/guard.py — Claude Code and Cursor preToolUse stdin shapes."""
import json
import os
import subprocess
import sys
import unittest

from kb.paths import vault_root
ROOT = vault_root()
GUARD = ["-m", "kb.git.guard"]


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
            "tool_input": {"file_path": os.path.join(wt, "skills", "x", "SKILL.md"),
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


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for backend/src/kb/metrics — session-log parsing, judge grading, D1 rows, golden task config."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from kb.metrics import d1, golden, judge, sessions, store


def usage(cw=1000, cr=0, out=10, cw1=0):
    return {"input_tokens": 2, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr,
            "output_tokens": out, "cache_creation": {"ephemeral_1h_input_tokens": cw1}}


def assistant(mid, u, tools=(), model="claude-opus-5-5", **kw):
    content = [{"type": "tool_use", "name": n, "input": i} for n, i in tools] or [{"type": "text", "text": "ok"}]
    return {"type": "assistant", "timestamp": kw.get("ts", "2026-10-24T10:00:00Z"), "cwd": "/v", "gitBranch": "main",
            "message": {"id": mid, "model": model, "usage": u, "content": content}}


def human(text, ts="2026-10-24T09:59:00Z"):
    return {"type": "user", "timestamp": ts, "origin": {"kind": "human"}, "message": {"role": "user", "content": text}}


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "-Users-x-local-workspace-personal-knowledge-base")

    def session(self, rows, sid="s1", subagents=()):
        p = os.path.join(self.proj, f"{sid}.jsonl")
        write_jsonl(p, rows)
        for i, sub in enumerate(subagents):
            write_jsonl(os.path.join(self.proj, sid, "subagents", f"agent-{i}.jsonl"), sub)
        return p

    def test_usage_counted_once_per_message_id_and_split_main_sub(self):
        p = self.session([human("hi"), assistant("m1", usage(cw=50000)), assistant("m1", usage(cw=50000)),
                          assistant("m2", usage(cw=10, cr=50000, out=200), ts="2026-10-24T10:30:00Z")],
                         subagents=[[assistant("a1", usage(cw=20000, out=5), model="claude-haiku-5-5")]])
        r = sessions.parse_session(p)
        self.assertEqual(r["calls"], 3)
        self.assertEqual(r["main"]["cw"], 50010)
        self.assertEqual(r["sub"]["cw"], 20000)
        self.assertEqual(r["first_context"], 50002)
        self.assertEqual(r["subagents"], 1)
        self.assertEqual(set(r["models"]), {"claude-opus-5-5", "claude-haiku-5-5"})
        self.assertEqual(r["minutes"], 31.0)
        self.assertGreater(r["usd"], 0)

    def test_task_follows_actions_not_prompt(self):
        p = self.session([human("Better mouse behavior"),
                          assistant("m1", usage(), tools=[("Bash", {"command": "pixi run ship -- start mouse --worktree"})])])
        self.assertEqual(sessions.parse_session(p)["task"], "feature")
        p = self.session([human("look at this paper"),
                          assistant("m1", usage(), tools=[("Bash", {"command": "python3 -m kb.ingest full-digest raw/x.pdf"})])],
                         sid="s2")
        self.assertEqual(sessions.parse_session(p)["task"], "digest")
        p = self.session([human("say ok"), assistant("m1", usage())], sid="s3")
        self.assertEqual(sessions.parse_session(p)["task"], "chat")

    def test_golden_tag_and_human_turns_skip_tool_results(self):
        p = self.session([human("[golden:query-x] what do I know"),
                          {"type": "user", "origin": {"kind": "human"},
                           "message": {"content": [{"type": "tool_result", "content": "x"}]}},
                          assistant("m1", usage())])
        r = sessions.parse_session(p)
        self.assertEqual((r["task"], r["golden"], r["human_turns"]), ("golden", "query-x", 1))

    def test_scan_matches_old_and_new_vault_paths_only(self):
        self.session([human("a"), assistant("m1", usage())])
        old = os.path.join(self.tmp, "-Users-x-OneDrive-Personal-RUNI-Thesis-Knowledge-Base")
        write_jsonl(os.path.join(old, "o.jsonl"), [human("b"), assistant("m9", usage())])
        write_jsonl(os.path.join(self.tmp, "-Users-x-other-project", "z.jsonl"), [human("c"), assistant("m8", usage())])
        self.assertEqual(sorted(r["id"] for r in sessions.scan([self.tmp])), ["o", "s1"])

    def test_price_weights(self):
        t = {"in": 1_000_000, "cw5": 0, "cw1": 0, "cr": 0, "out": 0}
        self.assertEqual(sessions.usd("claude-opus-5-5", t), 4.0)
        self.assertEqual(sessions.usd("claude-sonnet-5-5", t), 2.0)
        self.assertEqual(sessions.usd("claude-haiku-5-5", t), 0.1)


class StoreTest(unittest.TestCase):
    def test_merge_keeps_sessions_whose_logs_are_gone(self):
        root = tempfile.mkdtemp()
        base = {"main": {"in": 0, "cw": 0, "cr": 0, "out": 0}, "sub": {"in": 0, "cw": 0, "cr": 0, "out": 0}}
        store.merge_sessions([{"id": "a", "start": "1", **base}, {"id": "b", "start": "2", **base}], root)
        out = store.merge_sessions([{"id": "b", "start": "2", "x": 1, **base}], root)
        self.assertEqual([r["id"] for r in out], ["a", "b"])
        self.assertEqual(out[1]["x"], 1)


class JudgeTest(unittest.TestCase):
    TASK = {"prompt": "do x", "reference": "x done"}

    def test_parse_tolerates_prose_around_json(self):
        g = judge._parse('Sure.\n{"correct": 4, "complete": 5, "conventions": 3, "pass": true, "why": "ok"}\n')
        self.assertEqual((g["score"], g["pass"]), (4.0, True))
        self.assertIsNone(judge._parse("no json here"))

    def test_disagreement_is_flagged_and_never_passes(self):
        grades = iter([({"score": 4.67, "pass": True}, 0.01), ({"score": 3.0, "pass": True}, 0.01)])
        with patch.object(judge, "_ask", side_effect=lambda *a: next(grades)):
            g = judge.grade(self.TASK, "reply", "diff", [], {"samples": 2})
        self.assertTrue(g["flagged"])
        self.assertFalse(g["pass"])
        self.assertEqual(g["usd"], 0.02)

    def test_agreeing_grades_are_averaged(self):
        grades = iter([({"score": 4.0, "pass": True}, 0), ({"score": 4.67, "pass": True}, 0)])
        with patch.object(judge, "_ask", side_effect=lambda *a: next(grades)):
            g = judge.grade(self.TASK, "reply", "diff", [], {"samples": 2})
        self.assertEqual((g["score"], g["pass"], g["flagged"]), (4.33, True, False))

    def test_failed_checks_reach_the_prompt(self):
        p = judge._prompt(self.TASK, "r", "d" * 70_000, [{"cmd": "pytest", "ok": False, "tail": "AssertionError"}])
        self.assertIn("FAIL `pytest`", p)
        self.assertIn("AssertionError", p)
        self.assertIn("diff cut", p)


class D1Test(unittest.TestCase):
    def test_rows_carry_no_prompt_text_and_batch(self):
        r = {"id": "s", "task": "chat", "first_prompt": "secret thesis idea", "skills": ["a"],
             "main": {"in": 1, "cw": 2, "cr": 3, "out": 4}, "sub": {"in": 0, "cw": 0, "cr": 0, "out": 0},
             "models": {"m": {"in": 1, "cw": 2, "cr": 3, "out": 4}}, "usd": 0.1}
        row = d1.session_row(r)
        self.assertEqual(len(row), len(d1.SESSION_COLS))
        self.assertNotIn("secret thesis idea", json.dumps(row))
        stmts = list(d1.upserts("sessions", d1.SESSION_COLS, [row] * 85))
        per = d1.MAX_PARAMS // len(d1.SESSION_COLS)                  # D1's 100-value limit
        self.assertEqual(len(stmts), -(-85 // per))
        self.assertTrue(all(len(params) <= d1.MAX_PARAMS for _, params in stmts))

    def test_database_id_from_sync_toml(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "meta", "ops"))
        with open(os.path.join(root, d1.SYNC_TOML), "w") as f:
            f.write('[notify]\nemail = "x"\n[metrics]\nd1_database_id = "1234-abcd"\n')
        self.assertEqual(d1.database_id(root), "1234-abcd")


class GoldenTest(unittest.TestCase):
    def test_repo_tasks_load_with_defaults(self):
        tasks, judge_cfg = golden.load_tasks()
        self.assertEqual(len(tasks), 8)
        self.assertEqual({t["kind"] for t in tasks.values()},
                         {"query", "digest", "catalog", "feature", "bugfix", "pipeline", "wiki-edit"})
        for t in tasks.values():
            self.assertTrue(t["prompt"].strip() and t["reference"].strip() and t["checks"], t["id"])
            self.assertEqual(t["model"], "opus")
        self.assertEqual(judge_cfg["samples"], 2)

    def test_env_cannot_push_or_reach_github_or_the_work_gateway(self):
        repo = os.path.join(tempfile.mkdtemp(), "kb-golden-x")
        leaked = {"ANTHROPIC_BASE_URL": "https://gw", "ANTHROPIC_AUTH_TOKEN": "t", "KB_ROOT": "/elsewhere",
                  "PIXI_PROJECT_ROOT": "/runner", "CONDA_PREFIX": "/runner/.pixi/envs/default",
                  "PATH": "/runner/.pixi/envs/default/bin:/usr/bin"}
        with patch.dict(os.environ, leaked):
            env = golden._env("/tmp/sink.git", repo)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertNotIn("KB_ROOT", env)                               # the checkout in use is the vault
        self.assertEqual(env["PYTHONPATH"], os.path.join("backend", "src"))   # relative: its own code runs
        self.assertFalse(any(k.startswith(("PIXI_", "CONDA_")) for k in env))
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["KB_NO_PUSH"], "1")
        self.assertEqual((env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]), ("remote.origin.pushurl", "/tmp/sink.git"))
        self.assertTrue(env["GH_CONFIG_DIR"].endswith("gh-empty"))


class WorkDirTest(unittest.TestCase):
    def g(self, cwd, *args):
        import subprocess
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_picks_the_infra_worktree_with_work_else_the_clone(self):
        repo = tempfile.mkdtemp()
        self.g(repo, "init", "-q", "-b", "main")
        open(os.path.join(repo, "a.txt"), "w").write("a")
        self.g(repo, "add", "a.txt")
        self.g(repo, "commit", "-q", "-m", "base")
        base = self.g(repo, "rev-parse", "HEAD")
        self.assertEqual(golden.work_dir(repo, base), repo)            # no worktree yet
        wt = os.path.join(repo, ".claude", "worktrees", "x")
        self.g(repo, "worktree", "add", "-q", "-b", "infra/x", wt)
        self.assertEqual(golden.work_dir(repo, base), repo)            # a worktree with no work doesn't count
        open(os.path.join(wt, "b.txt"), "w").write("b")
        self.g(wt, "add", "b.txt")
        self.g(wt, "commit", "-q", "-m", "feat")
        self.assertEqual(os.path.realpath(golden.work_dir(repo, base)), os.path.realpath(wt))


if __name__ == "__main__":
    unittest.main()

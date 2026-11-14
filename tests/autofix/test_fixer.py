"""kb_distillery.autofix.fixer: the tool policy, the RESULT line and the script steps around the agent.
No network, no LLM: ship, the agent session, the review and gh are replaced."""
import subprocess

import pytest

from kb_distillery.autofix import detect, fixer, issue

ERR = "git commit failed: kb hook pre-commit: 'distill' is not on PATH"


@pytest.mark.parametrize("name,inp,ok", [
    ("Read", {"file_path": "x"}, True),
    ("Edit", {"file_path": "src/kb_distillery/ops/core.py"}, True),
    ("Edit", {"file_path": "/etc/hosts"}, False),
    ("Write", {"file_path": "examples/demo/wiki/a.md"}, False),
    ("Edit", {"file_path": ".github/workflows/ci.yml"}, False),
    ("Bash", {"command": "pixi run python -m pytest tests/ops -q"}, True),
    ("Bash", {"command": "git diff origin/main"}, True),
    ("Bash", {"command": "git commit -am x"}, False),
    ("Bash", {"command": "cd x && git push"}, False),
    ("Bash", {"command": "/usr/bin/git push origin main"}, False),
    ("Bash", {"command": "git -C . commit -m x"}, False),
    ("Bash", {"command": "python -c 'import subprocess'"}, False),
    ("Bash", {"command": "rm --recursive build"}, False),
    ("Bash", {"command": "git log --oneline -5"}, True),
    ("Bash", {"command": "gh issue list"}, False),
    ("Bash", {"command": "pixi run ship -- merge"}, False),
    ("Bash", {"command": "rm -rf build"}, False),
    ("Bash", {"command": "curl https://example.com"}, False),
    ("Bash", {"command": "echo x > ~/knowledge/k/wiki/a.md"}, False),
    ("WebFetch", {"url": "https://example.com"}, False),
])
def test_tool_policy(tmp_path, name, inp, ok):
    if "file_path" in inp and not inp["file_path"].startswith("/"):
        inp = {"file_path": str(tmp_path / inp["file_path"])}
    assert fixer.decide(name, inp, str(tmp_path))[0] is ok


def test_outcome_line_takes_the_last_result():
    text = "RESULT: gave-up - first\nmore\nRESULT: fixed - resolve distill from the env bin"
    assert fixer.outcome_line(text) == ("fixed", "resolve distill from the env bin")
    assert fixer.outcome_line("no line")[0] == "gave-up"


def test_scope_of():
    assert fixer.scope_of(["tests/x.py", "src/kb_distillery/ops/core.py"]) == "ops"
    assert fixer.scope_of(["README.md"]) == "ops"


class Harness:
    """Replaces ship, the agent, the review, the gate and gh; records every ship call."""

    def __init__(self, monkeypatch, tmp_path, agent_text="RESULT: fixed - x", changed=True, passed=True,
                 gate_reasons=(), commit_rc=0):
        self.calls, self.comments = [], []
        self.wt = tmp_path / "wt"
        self.wt.mkdir()
        if changed:
            (self.wt / "f.py").write_text("x = 1\n")
        subprocess.run(["git", "init", "-q"], cwd=self.wt, check=True)

        def ship(args, cwd, timeout=0):
            self.calls.append(args[0])
            out = {"start": f"worktree ready: {self.wt} on infra/x\n",
                   "pr": "https://github.com/octocat/kb/pull/77\n"}.get(args[0], "")
            rc = commit_rc if args[0] == "commit" else 0
            return subprocess.CompletedProcess(args, rc, out, "")
        monkeypatch.setattr(fixer, "ship", ship)
        monkeypatch.setattr(fixer, "run_agent", lambda prompt, wt, log=print: (agent_text, 1.25, ""))
        monkeypatch.setattr(fixer, "review", lambda f, d: (passed, "ok", [] if passed else ["too broad"], 0.5))
        monkeypatch.setattr(fixer.gate, "measure", lambda wt, base="origin/main": list(gate_reasons))
        monkeypatch.setattr(fixer.issue, "comment", lambda n, t, r: self.comments.append(t) or True)
        monkeypatch.delenv("KB_AUTOFIX_GUARD", raising=False)
        self.state = {}

    def run(self):
        f = detect.Failure("sync", ERR, True)
        return fixer.fix(f, 41, self.state, "/engine", save=lambda: None, log=lambda s: None)


def test_small_fix_merges(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    assert h.run().startswith("merged")
    assert h.calls == ["start", "commit", "review", "pr", "merge"]
    attempt = list(h.state.values())[0]["attempt"]
    assert attempt["pr"] == 77 and attempt["held"] is False and attempt["usd"] == 1.75


def test_dramatic_fix_is_held_and_never_merged(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, gate_reasons=["touches git hooks or ship (scripts/hooks/x)"])
    assert h.run().startswith("held")
    assert "merge" not in h.calls and "held for your approval" in h.comments[-1]


def test_review_concerns_hold_the_pr(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, passed=False)
    assert h.run().startswith("held") and "merge" not in h.calls and "review" not in h.calls


def test_start_failure_does_not_use_up_the_attempt(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    monkeypatch.setattr(fixer, "ship", lambda args, cwd, timeout=0: subprocess.CompletedProcess(args, 1, "", "offline"))
    assert h.run() == "failed: ship start"
    assert "attempt" not in list(h.state.values())[0]


def test_no_change_drops_the_branch(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, agent_text="RESULT: not-engine - a kb data problem", changed=False)
    assert h.run() == "no fix: not-engine"
    assert h.calls == ["start", "prune"]


def test_failed_gates_drop_the_branch(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, commit_rc=1)
    assert h.run() == "failed: commit gates" and h.calls[-1] == "prune"


def test_one_attempt_per_signature(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.run()
    h.calls.clear()
    assert h.run().startswith("skipped: already attempted") and h.calls == []


def test_daily_cap(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_AUTOFIX_DAILY_CAP", "1")
    import datetime
    h.state["other"] = {"attempt": {"at": datetime.date.today().isoformat() + "T01:00:00", "usd": 2.0}}
    assert h.run().startswith("skipped: daily cap") and h.calls == []


def test_default_backend_is_api(monkeypatch):
    monkeypatch.delenv("KB_AUTOFIX_BACKEND", raising=False)
    assert fixer.backend() == "api"
    monkeypatch.setenv("KB_AUTOFIX_BACKEND", "subscription")
    assert fixer.backend() == "subscription"

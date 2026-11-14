"""kb_distillery.autofix: detection, signatures, the issue step and the diff gate. No network, no LLM."""
import json
import subprocess

import pytest

from kb_distillery.autofix import __main__ as cli
from kb_distillery.autofix import detect, gate, issue

PATH_ERR = ("git commit failed: kb hook pre-commit: 'distill' is not on PATH - refusing (fail closed). "
            "Install kb-distillery (pip install kb-distillery) or put its bin folder on PATH.")


def _run(status="error", steps=None, findings=None, started="2026-11-13T22:00:01"):
    return {"kind": "nightly", "started": started, "status": status,
            "steps": steps if steps is not None else [{"name": "sync", "status": "error", "error": PATH_ERR},
                                                      {"name": "hygiene", "status": "error", "checks": 10},
                                                      {"name": "report", "status": "error"}],
            "hygiene": {"findings": findings if findings is not None else
                        [{"severity": "error", "kind": "sync-skipped", "detail": PATH_ERR}]}}


def _write_runs(tmp_path, *runs):
    ops = tmp_path / "kb" / "meta" / ".ops"
    ops.mkdir(parents=True)
    (ops / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs))
    return str(tmp_path / "kb")


class FakeGh:
    def __init__(self, issues=(), fail=False):
        self.issues, self.calls, self.fail = list(issues), [], fail

    def __call__(self, args, root):
        self.calls.append(args)
        if self.fail:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if args[:2] == ["issue", "list"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(self.issues), "")
        if args[:2] == ["issue", "create"]:
            return subprocess.CompletedProcess(args, 0, "https://github.com/octocat/kb/issues/41\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_skipped_sync_is_one_fixable_failure():
    fails = detect.failures(_run())
    assert [(f.step, f.fixable) for f in fails] == [("sync", True)]     # the sync-skipped finding is the same one


def test_green_and_warn_runs_have_no_failures():
    assert detect.failures(_run(status="warn")) == []
    assert detect.failures(None) == []


def test_signature_ignores_dates_paths_and_numbers():
    a = detect.signature("sync", "push failed at /Users/jdoe/x 2026-11-13 abc1234ef")
    b = detect.signature("sync", "push failed at /Users/octocat/y 2026-11-14 0099ffeed")
    assert a == b
    assert a != detect.signature("hygiene", "push failed at /x 1 abc1234ef")


def test_credentials_and_data_findings_are_ticket_only():
    run = _run(steps=[{"name": "sync", "status": "error", "error": "push: Authentication error (HTTP 401)"}],
               findings=[{"severity": "error", "kind": "broken-link", "detail": "wiki/a.md links to b.md"},
                         {"severity": "warn", "kind": "stale", "detail": "x"}])
    fails = detect.failures(run)
    assert [(f.step, f.fixable) for f in fails] == [("sync", False), ("hygiene:broken-link", False)]


def test_crash_in_a_step_is_fixable():
    run = _run(steps=[{"name": "report", "status": "error", "error": "KeyError: 'threads'"}], findings=[])
    assert [(f.step, f.fixable) for f in detect.failures(run)] == [("report", True)]


def test_issue_created_then_reused(tmp_path):
    f = detect.failures(_run())[0]
    gh = FakeGh()
    assert issue.open_or_reuse(f, _run(), str(tmp_path), run_gh=gh) == (41, "created")
    create = next(c for c in gh.calls if c[:2] == ["issue", "create"])
    assert issue.MARK.format(f.signature) in create[create.index("--body") + 1]
    gh = FakeGh(issues=[{"number": 7, "body": "x " + issue.MARK.format(f.signature)}])
    assert issue.open_or_reuse(f, _run(), str(tmp_path), run_gh=gh) == (7, "reused")
    assert not any(c[:2] == ["issue", "create"] for c in gh.calls)


def test_issue_step_never_raises(tmp_path):
    f = detect.failures(_run())[0]
    number, how = issue.open_or_reuse(f, _run(), str(tmp_path), run_gh=FakeGh(fail=True))
    assert number is None and how.startswith("failed")


def test_issue_body_is_scrubbed():
    text = issue.scrub("sent to me@example.com from /Users/jdoe/x id deadbeefdeadbeefdeadbeefdeadbeef")
    assert "me@example.com" not in text and "jdoe" not in text and "deadbeef" not in text


def test_dry_run_writes_nothing(tmp_path):
    kb = _write_runs(tmp_path, _run(status="ok"), _run())
    gh = FakeGh()
    done = cli.nightly(kb, dry_run=True, root=str(tmp_path / "engine"), run_gh=gh)
    assert len(done) == 1 and done[0][2].startswith("dry-run")
    assert all(c[:2] == ["issue", "list"] for c in gh.calls)
    assert not (tmp_path / "engine" / ".cache").exists()


def test_nightly_records_state_and_calls_fixer(tmp_path):
    kb = _write_runs(tmp_path, _run())
    seen = []
    done = cli.nightly(kb, root=str(tmp_path), run_gh=FakeGh(), fix=lambda f, n, s: seen.append((f.step, n)) or "x")
    assert seen == [("sync", 41)] and done[0][2] == "x"
    state = json.loads((tmp_path / ".cache" / "autofix" / "state.json").read_text())
    assert list(state.values())[0]["issue"] == 41


NUMSTAT_SMALL = "3\t1\tsrc/kb_distillery/ops/core.py\n"


def test_gate_small_fix_may_merge():
    assert gate.reasons(NUMSTAT_SMALL, "M\tsrc/kb_distillery/ops/core.py\n") == []


@pytest.mark.parametrize("numstat,status,expect", [
    ("90\t0\tsrc/kb_distillery/ops/core.py\n", "M\tsrc/kb_distillery/ops/core.py", "changed lines"),
    ("".join(f"1\t0\tsrc/kb_distillery/ops/f{i}.py\n" for i in range(6)), "", "files"),
    ("0\t5\tsrc/kb_distillery/ops/old.py\n", "D\tsrc/kb_distillery/ops/old.py", "deletes"),
    ("1\t0\tsrc/kb_distillery/vault/schema.py\n", "", "schema"),
    ("1\t0\texamples/demo/wiki/a.md\n", "", "knowledge"),
    ("1\t0\t.github/workflows/ci.yml\n", "", "CI"),
    ("1\t0\tscripts/hooks/pre-commit\n", "", "hooks"),
    ("1\t0\tsrc/kb_distillery/publish/cloudflare/x.py\n", "", "deploy"),
])
def test_gate_holds_dramatic_diffs(numstat, status, expect):
    assert any(expect in r for r in gate.reasons(numstat, status))


def test_gate_holds_weakened_tests():
    patch = ("+++ b/tests/ops/test_x.py\n@@\n-    assert a == 1\n-    assert b\n+    pass\n"
             "+@pytest.mark.skip(reason='flaky')\n")
    why = gate.reasons("2\t2\ttests/ops/test_x.py\n", "M\ttests/ops/test_x.py", patch)
    assert any("skips" in r for r in why) and any("assertion" in r for r in why)


@pytest.mark.flag("nightly-autofix", True)
def test_hook_runs_autofix_when_flag_on(tmp_path, monkeypatch):
    from kb_distillery.ops import core
    monkeypatch.setattr(core, "AUTOFIX_LOG", str(tmp_path / "autofix.log"))
    calls = []
    rc = core.nightly_autofix(str(tmp_path), run=lambda cmd, **kw: calls.append(cmd) or
                              subprocess.CompletedProcess(cmd, 0))
    assert rc == 0 and calls[0][1:4] == ["-m", "kb_distillery.autofix", "nightly"]


@pytest.mark.flag("nightly-autofix", False)
def test_hook_is_dark_when_flag_off(tmp_path):
    from kb_distillery.ops import core
    calls = []
    assert core.nightly_autofix(str(tmp_path), run=lambda cmd, **kw: calls.append(cmd)) is None
    assert calls == []

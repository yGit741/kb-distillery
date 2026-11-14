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
def test_hook_runs_autofix_and_reads_its_summary(tmp_path, monkeypatch):
    from kb_distillery.ops import core
    monkeypatch.setenv("KB_NIGHTLY", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(core, "AUTOFIX_LOG", str(tmp_path / "autofix.log"))
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        assert json.load(open(cmd[cmd.index("--run-json") + 1]))["status"] == "error"
        with open(cmd[cmd.index("--summary") + 1], "w") as f:
            json.dump([{"step": "sync", "fixable": True, "outcome": "merged: https://github.com/octocat/kb/pull/9",
                        "issue": 4, "repo": "https://github.com/octocat/kb"}], f)
        return subprocess.CompletedProcess(cmd, 0)
    results, why = core.nightly_autofix(str(tmp_path), _run(), run=run)
    assert calls[0][1:4] == ["-m", "kb_distillery.autofix", "nightly"] and why == ""
    assert results[0]["outcome"].startswith("merged")


@pytest.mark.flag("nightly-autofix", False)
def test_hook_is_dark_when_flag_off(tmp_path):
    from kb_distillery.ops import core
    calls = []
    assert core.nightly_autofix(str(tmp_path), _run(), run=lambda cmd, **kw: calls.append(cmd)) is None
    assert calls == []


def _res(outcome, fixable=True, issue=4):
    return {"step": "sync", "fixable": fixable, "why": "a kb data finding", "outcome": outcome, "issue": issue,
            "repo": "https://github.com/octocat/kb"}


@pytest.mark.parametrize("results,expect", [
    ([_res("held: https://github.com/octocat/kb/pull/12")], "Nightly failed · fix ready, needs your approval (PR #12)"),
    ([_res("merged: https://github.com/octocat/kb/pull/12")], "Nightly failed · fixed automatically (PR #12)"),
    ([_res("no fix: gave-up")], "Nightly failed · tried to fix, could not (issue #4)"),
    ([_res("skipped: already attempted on 2026-11-13 (one attempt per signature)")],
     "Nightly failed again · fix already tried, needs you (issue #4)"),
    ([_res("created", fixable=False)], "Nightly failed · needs you, not auto-fixable (issue #4)"),
    ([_res("created", fixable=False), _res("held: https://github.com/octocat/kb/pull/3")],
     "Nightly failed · fix ready, needs your approval (PR #3)"),
    ([], "Nightly failed · auto-fix did not run (no result)"),
])
def test_one_mail_headline(results, expect):
    from kb_distillery.ops import nightly_report
    assert nightly_report.autofix_headline(results) == expect


def test_mail_subject_carries_the_fix_outcome():
    from kb_distillery.ops import nightly_report
    from kb_distillery.ops.report import model as m

    class Report:
        def kinds(self):
            return ["sync-skipped"]
    doc = m.Doc("Nightly", "error", "1 thing needs you — x", [m.Section("", [m.Banner("error", "1 thing needs you")])])
    nightly_report.apply_autofix(doc, [_res("held: https://github.com/octocat/kb/pull/12")])
    subject = nightly_report.subject(doc, Report(), "[kb]")
    assert subject.endswith("Nightly failed · fix ready, needs your approval (PR #12)")
    assert [s.id for s in doc.sections][1] == "autofix"
    assert ["Fix PR #12", "https://github.com/octocat/kb/pull/12"] in doc.links
    assert "ship -- approve 12" in doc.sections[1].blocks[0].items[0].fix


def test_summary_and_run_json(tmp_path):
    kb = _write_runs(tmp_path, _run(status="ok"))
    done = cli.nightly(kb, root=str(tmp_path), run_gh=FakeGh(), run=_run())
    rows = cli.summary(done, str(tmp_path))
    assert rows[0]["step"] == "sync" and rows[0]["issue"] == 41 and rows[0]["outcome"] == "created"


def test_gate_counts_a_rename_as_a_delete():
    assert any("deletes" in r for r in gate.reasons("0\t0\tsrc/kb_distillery/x.py\n", "R100\tsrc/a.py\tsrc/b.py"))


def test_gate_holds_binary_and_billing_paths():
    assert any("binary" in r for r in gate.reasons("-\t-\tsrc/kb_distillery/ops/x.bin\n", ""))
    assert any("LLM" in r for r in gate.reasons("1\t0\tsrc/kb_distillery/llm/__init__.py\n", ""))


def test_network_errors_are_ticket_only():
    run = _run(steps=[{"name": "sync", "status": "error", "error": "error: failed to push some refs to 'origin'"}],
               findings=[])
    assert [f.fixable for f in detect.failures(run)] == [False]


def test_hygiene_issue_carries_no_kb_detail():
    run = _run(findings=[{"severity": "error", "kind": "broken-link", "detail": "wiki/secret-page.md"}])
    assert all("secret-page" not in f.message for f in detect.failures(run))


def test_unlisted_issues_never_open_a_duplicate(tmp_path):
    f = detect.failures(_run())[0]

    def gh(args, root):
        rc = 1 if args[:2] == ["issue", "list"] else 0
        return subprocess.CompletedProcess(args, rc, "", "")
    assert issue.open_or_reuse(f, _run(), str(tmp_path), run_gh=gh)[0] is None


@pytest.mark.flag("nightly-autofix", True)
def test_timeout_still_reads_what_the_fixer_did(tmp_path, monkeypatch):
    from kb_distillery.ops import core
    monkeypatch.setenv("KB_NIGHTLY", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(core, "AUTOFIX_LOG", str(tmp_path / "autofix.log"))

    def run(cmd, **kw):
        with open(cmd[cmd.index("--summary") + 1], "w") as f:
            json.dump([_res("created")], f)
        raise subprocess.TimeoutExpired(cmd, 1)
    results, why = core.nightly_autofix(str(tmp_path), _run(), run=run)
    assert results[0]["issue"] == 4 and why.startswith("timed out")


@pytest.mark.flag("nightly-autofix", True)
def test_bad_summary_is_ignored(tmp_path, monkeypatch):
    from kb_distillery.ops import core
    monkeypatch.setenv("KB_NIGHTLY", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(core, "AUTOFIX_LOG", str(tmp_path / "autofix.log"))

    def run(cmd, **kw):
        with open(cmd[cmd.index("--summary") + 1], "w") as f:
            json.dump({"not": "a list"}, f)
        return subprocess.CompletedProcess(cmd, 0)
    assert core.nightly_autofix(str(tmp_path), _run(), run=run) == ([], "")


def test_held_plus_ticket_is_an_error_night():
    from kb_distillery.ops import nightly_report
    from kb_distillery.ops.report import model as m
    doc = m.Doc("Nightly", "error", "x", [m.Section("", [m.Banner("error", "x")])])
    nightly_report.apply_autofix(doc, [_res("held: https://github.com/octocat/kb/pull/3"), _res("created", fixable=False)])
    assert doc.status == "error"


@pytest.mark.flag("nightly-autofix", True)
@pytest.mark.parametrize("nightly", [None, "1"])
def test_autofix_never_runs_outside_the_real_nightly(tmp_path, monkeypatch, nightly):
    """A sync run by a test (or any command but daily_sync.main) never opens issues or starts the fixer."""
    from kb_distillery.ops import core
    if nightly:
        monkeypatch.setenv("KB_NIGHTLY", nightly)          # pytest's own PYTEST_CURRENT_TEST still blocks it
    else:
        monkeypatch.delenv("KB_NIGHTLY", raising=False)
    calls = []
    assert core.nightly_autofix(str(tmp_path), _run(), run=lambda cmd, **kw: calls.append(cmd)) is None
    assert calls == []


def test_issue_gh_refuses_inside_tests(tmp_path):
    cp = issue.gh(["issue", "list"], str(tmp_path))
    assert cp.returncode == 1 and "tests" in cp.stderr


def test_seen_again_comment_at_most_once_a_day(tmp_path):
    f = detect.failures(_run())[0]
    kb = _write_runs(tmp_path, _run())
    gh = FakeGh(issues=[{"number": 7, "body": issue.MARK.format(f.signature)}])
    cli.nightly(kb, root=str(tmp_path), run_gh=gh)
    cli.nightly(kb, root=str(tmp_path), run_gh=gh, run=_run(started="2026-11-13T23:30:00"))
    assert sum(c[:2] == ["issue", "comment"] for c in gh.calls) == 1
    cli.nightly(kb, root=str(tmp_path), run_gh=gh, run=_run(started="2026-11-14T22:00:00"))
    assert sum(c[:2] == ["issue", "comment"] for c in gh.calls) == 2


def test_nightly_entry_runs_without_a_runtime_warning():
    import subprocess as sp
    import sys
    out = sp.run([sys.executable, "-W", "error::RuntimeWarning", "-m", "kb_distillery.ops.nightly", "--help"],
                 capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-600:]
    assert "RuntimeWarning" not in out.stderr

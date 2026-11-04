"""Clean-install papercuts: kb commits without a git identity, --help never opens an ops session."""
import os
import subprocess

import pytest

from kb_distillery.ops import core, wrap

NO_IDENTITY = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "user.useConfigOnly", "GIT_CONFIG_VALUE_0": "true"}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in NO_IDENTITY.items():
        monkeypatch.setenv(k, v)
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "a.md").write_text("one\n")
    return str(tmp_path)


def _author(root):
    return subprocess.run(["git", "log", "-1", "--format=%an <%ae>"], cwd=root, capture_output=True, text=True).stdout.strip()


def test_kb_commit_without_a_git_identity_uses_the_fallback(repo):
    assert core._commit_paths(repo, ["wiki/a.md"], "kb(scrap): a\n")
    assert _author(repo) == "kb-distillery <kb@localhost>"


def test_a_configured_identity_wins_over_the_fallback(repo):
    subprocess.run(["git", "config", "user.name", "Ann"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "ann@example.com"], cwd=repo, check=True)
    assert core.identity_env(repo) == {}
    assert core._commit_paths(repo, ["wiki/a.md"], "kb(scrap): a\n")
    assert _author(repo) == "Ann <ann@example.com>"


def test_environment_identity_wins_over_the_fallback(repo, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Env")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "env@example.com")
    assert core.identity_env(repo) == {}


def test_help_does_not_open_an_ops_session(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(core, "begin", lambda *a, **k: opened.append(a))
    monkeypatch.delenv("KB_OPS_DISABLE", raising=False)
    seen = []
    key = next(iter(wrap.INGEST_BEGIN))
    for flag in ("--help", "-h"):
        rc = wrap.run(lambda argv: seen.append(argv) or 0, argv=[key[0], "raw/x.md", flag], table={}, begin_table=wrap.INGEST_BEGIN)
        assert rc == 0
    assert opened == [] and len(seen) == 2
    assert "ops:" not in capsys.readouterr().out


def test_a_half_configured_identity_keeps_what_is_set(repo):
    subprocess.run(["git", "config", "user.name", "Ann"], cwd=repo, check=True)
    assert core._commit_paths(repo, ["wiki/a.md"], "kb(scrap): a\n")
    assert _author(repo) == "Ann <kb@localhost>"

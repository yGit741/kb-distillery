"""kbd init: a first kb from a template, its own git repo, no LLM. Temp dirs and a temp HOME only."""
import os
import subprocess

import pytest

from kb import init_kb, kbconfig, llm
from kb.git import commit_policy


@pytest.fixture
def world(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bases = tmp_path / "kbs"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("KB_BASES_DIR", str(bases))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("KB", "KB_ROOT", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "nokey"))
    monkeypatch.setattr(llm, "_which", lambda n: None)
    return bases, home


def git(path, *args):
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True).stdout.strip()


def test_creates_a_loadable_kb_with_its_own_repo(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "starter", str(bases))
    assert target == str(bases / "notes")
    cfg = kbconfig.load_dir(target)                            # strict: schema version and template resolve
    assert (cfg.id, cfg.template, cfg.schema_version) == ("notes", "starter", kbconfig.SCHEMA_VERSION)
    assert cfg.git_root == target
    for rel in ("wiki", "raw/inbox", "meta", ".gitignore"):
        assert os.path.exists(os.path.join(target, rel))
    assert git(target, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(target, "status", "--porcelain") == ""          # everything is committed
    assert "kb.toml" in git(target, "ls-files")
    assert kbconfig.discover() == {"notes": target}
    assert not [d for d in os.listdir(bases) if d.startswith(".")]      # no temp folder left


def test_first_commit_message_passes_commit_policy(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "academic-research", str(bases))
    subject = git(target, "log", "-1", "--format=%s")
    assert commit_policy.SUBJECT_KB.match(subject), subject
    assert git(target, "log", "-1", "--format=%an") == "kb-distillery"      # the fallback identity


def test_uses_the_configured_git_identity(world, monkeypatch):
    bases, _ = world
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Ann")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "ann@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Ann")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "ann@example.com")
    target = init_kb.create("notes", "Notes", "starter", str(bases))
    assert git(target, "log", "-1", "--format=%an") == "Ann"
    assert os.environ["GIT_AUTHOR_NAME"] == "Ann"


def test_fallback_identity_does_not_leak_into_the_environment(world):
    bases, _ = world
    init_kb.create("notes", "Notes", "starter", str(bases))
    assert "GIT_AUTHOR_NAME" not in os.environ


def test_refuses_to_overwrite_and_leaves_it_untouched(world):
    bases, _ = world
    (bases / "notes").mkdir(parents=True)
    (bases / "notes" / "mine.md").write_text("keep")
    with pytest.raises(init_kb.InitError, match="already exists"):
        init_kb.create("notes", "Notes", "starter", str(bases))
    assert (bases / "notes" / "mine.md").read_text() == "keep"
    assert os.listdir(bases / "notes") == ["mine.md"]


@pytest.mark.parametrize("bad", ["think", "yonatan-thesis", "demo", "../x", "a/b", ".hidden", "Up", ""])
def test_refuses_reserved_and_unsafe_ids(world, bad):
    bases, _ = world
    with pytest.raises(init_kb.InitError):
        init_kb.create(bad, "X", "starter", str(bases))
    assert not bases.exists() or os.listdir(bases) == []


def test_refuses_home_and_unknown_template(world):
    bases, home = world
    with pytest.raises(init_kb.InitError, match="home"):
        init_kb.create("notes", "N", "starter", str(home))
    with pytest.raises(init_kb.InitError, match="unknown template"):
        init_kb.create("notes", "N", "nope", str(bases))
    assert list(home.iterdir()) == []


def test_failed_commit_leaves_nothing_behind(world, monkeypatch):
    bases, _ = world
    import kb.ops.core as core

    def boom(*a, **k):
        raise core.OpsError("git commit failed: no")
    monkeypatch.setattr(core, "_commit_paths", boom)
    with pytest.raises(init_kb.InitError, match="first commit"):
        init_kb.create("notes", "N", "starter", str(bases))
    assert os.listdir(bases) == []


def test_name_with_quotes_stays_valid_toml(world):
    bases, _ = world
    target = init_kb.create("notes", 'My "best" notes', "starter", str(bases))
    assert kbconfig.load_dir(target).name == 'My "best" notes'


def test_main_non_interactive_runs_doctor_and_prints_launch(world, capsys):
    bases, _ = world
    rc = init_kb.main(["--kb-id", "notes", "--yes"])
    out = capsys.readouterr().out
    assert rc == 0 and (bases / "notes" / "kb.toml").is_file()
    assert "kbd launch --kb notes" in out
    assert "PASS  kb.toml" in out
    assert "claude login" in out and "stay off" in out         # the one LLM line; nothing was asked or stored
    assert not os.path.exists(llm.KEY_FILE)


def test_main_second_run_refuses(world, capsys):
    init_kb.main(["--kb-id", "notes", "--yes"])
    capsys.readouterr()
    assert init_kb.main(["--kb-id", "notes", "--yes"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_main_dir_prints_a_path_launch(world, tmp_path, capsys):
    other = tmp_path / "elsewhere"
    assert init_kb.main(["--kb-id", "notes", "--dir", str(other), "--yes"]) == 0
    assert f"kbd launch --kb {os.path.realpath(other)}/notes" in capsys.readouterr().out.replace(str(other), os.path.realpath(other))


def test_new_kb_lints_clean(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "starter", str(bases))
    env = {**os.environ, "KB_ROOT": target}
    cp = subprocess.run([os.sys.executable, "-m", "kb.lint.lint"], cwd=target, env=env, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stdout[-800:] + cp.stderr[-800:]

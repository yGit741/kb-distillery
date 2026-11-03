"""distill init: a first kb from a kit, its own git repo, no LLM. Temp dirs and a temp HOME only."""
import os
import subprocess

import pytest

from kb_distillery import init_kb, llm
from kb_distillery.config import kb as kbconfig
from kb_distillery.git import commit_policy


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
    target = init_kb.create("notes", "Notes", "base", str(bases))
    assert target == str(bases / "notes")
    cfg = kbconfig.load_dir(target)                            # strict: schema version and kit resolve
    assert (cfg.id, cfg.kit, cfg.schema_version) == ("notes", "base", kbconfig.SCHEMA_VERSION)
    toml = open(os.path.join(target, "kb.toml"), encoding="utf-8").read()
    assert 'kit = "base"' in toml and "template" not in toml          # init writes `kit`, never the older `template`
    assert cfg.git_root == target
    for rel in ("wiki", "raw/inbox", "meta", ".gitignore"):
        assert os.path.exists(os.path.join(target, rel))
    assert git(target, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(target, "status", "--porcelain") == ""          # everything is committed
    assert "kb.toml" in git(target, "ls-files")
    assert kbconfig.discover() == {"notes": target}
    assert not [d for d in os.listdir(bases) if d.startswith(".")]      # no temp folder left


def test_the_old_template_names_still_create_a_kb_with_the_current_kit_names(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "academic-research", str(bases))
    assert kbconfig.load_dir(target).kit == "research"
    assert 'kit = "research"' in open(os.path.join(target, "kb.toml"), encoding="utf-8").read()
    with pytest.raises(init_kb.InitError, match="unknown kit"):
        init_kb.create("other", "Other", "nope", str(bases))


def test_first_commit_message_passes_commit_policy(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "research", str(bases))
    subject = git(target, "log", "-1", "--format=%s")
    assert commit_policy.SUBJECT_KB.match(subject), subject
    assert git(target, "log", "-1", "--format=%an") == "kb-distillery"      # the fallback identity


def test_uses_the_configured_git_identity(world, monkeypatch):
    bases, _ = world
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Ann")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "ann@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Ann")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "ann@example.com")
    target = init_kb.create("notes", "Notes", "base", str(bases))
    assert git(target, "log", "-1", "--format=%an") == "Ann"
    assert os.environ["GIT_AUTHOR_NAME"] == "Ann"


def test_fallback_identity_does_not_leak_into_the_environment(world):
    bases, _ = world
    init_kb.create("notes", "Notes", "base", str(bases))
    assert "GIT_AUTHOR_NAME" not in os.environ


def test_refuses_to_overwrite_and_leaves_it_untouched(world):
    bases, _ = world
    (bases / "notes").mkdir(parents=True)
    (bases / "notes" / "mine.md").write_text("keep")
    with pytest.raises(init_kb.InitError, match="already exists"):
        init_kb.create("notes", "Notes", "base", str(bases))
    assert (bases / "notes" / "mine.md").read_text() == "keep"
    assert os.listdir(bases / "notes") == ["mine.md"]


@pytest.mark.parametrize("bad", ["think", "demo", "../x", "a/b", ".hidden", "Up", ""])
def test_refuses_reserved_and_unsafe_ids(world, bad):
    bases, _ = world
    with pytest.raises(init_kb.InitError):
        init_kb.create(bad, "X", "base", str(bases))
    assert not bases.exists() or os.listdir(bases) == []


def test_refuses_home_and_unknown_kit(world):
    bases, home = world
    with pytest.raises(init_kb.InitError, match="home"):
        init_kb.create("notes", "N", "base", str(home))
    with pytest.raises(init_kb.InitError, match="unknown kit"):
        init_kb.create("notes", "N", "nope", str(bases))
    assert list(home.iterdir()) == []


def test_failed_commit_leaves_nothing_behind(world, monkeypatch):
    bases, _ = world
    import kb_distillery.ops.core as core

    def boom(*a, **k):
        raise core.OpsError("git commit failed: no")
    monkeypatch.setattr(core, "_commit_paths", boom)
    with pytest.raises(init_kb.InitError, match="first commit"):
        init_kb.create("notes", "N", "base", str(bases))
    assert os.listdir(bases) == []


def test_name_with_quotes_stays_valid_toml(world):
    bases, _ = world
    target = init_kb.create("notes", 'My "best" notes', "base", str(bases))
    assert kbconfig.load_dir(target).name == 'My "best" notes'


def test_main_non_interactive_runs_doctor_and_prints_launch(world, capsys):
    bases, _ = world
    rc = init_kb.main(["--kb-id", "notes", "--yes"])
    out = capsys.readouterr().out
    assert rc == 0 and (bases / "notes" / "kb.toml").is_file()
    assert "distill launch --kb notes" in out
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
    assert f"distill launch --kb {os.path.realpath(other)}/notes" in capsys.readouterr().out.replace(str(other), os.path.realpath(other))


def test_new_kb_lints_clean(world):
    bases, _ = world
    target = init_kb.create("notes", "Notes", "base", str(bases))
    env = {**os.environ, "KB_ROOT": target}
    cp = subprocess.run([os.sys.executable, "-m", "kb_distillery.lint.lint"], cwd=target, env=env, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stdout[-800:] + cp.stderr[-800:]


def test_positional_dir_is_the_same_as_dir_flag(world, tmp_path, capsys):
    out = tmp_path / "out"
    assert init_kb.main(["--kit", "research", "--yes", str(out)]) in (0, 1)       # doctor may warn; the kb is made
    assert os.path.isfile(out / "my-kb" / "kb.toml")
    same = tmp_path / "same"
    init_kb.main(["--yes", "--dir", str(same), str(same)])
    assert os.path.isfile(same / "my-kb" / "kb.toml")


def test_positional_dir_and_a_different_dir_flag_is_an_error(world, tmp_path):
    with pytest.raises(SystemExit) as e:
        init_kb.main(["--yes", "--dir", str(tmp_path / "a"), str(tmp_path / "b")])
    assert e.value.code == 2

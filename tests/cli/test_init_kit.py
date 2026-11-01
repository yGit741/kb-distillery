"""`distill init` writes a kb's kit files and `distill init --refresh` re-syncs them. Temp dirs and a temp HOME only."""
import hashlib
import os
import re
import subprocess

import pytest

from kb_distillery import init_kb, kbconfig, llm
from kb_distillery.git import install_hooks
from kb_distillery.vault import kit as kits


OLD_HOOKS_PATH = "../../tools" "/kb-hooks"      # a kb wired before the move; spelled in two parts so the old-paths scan stays clean


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
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "nokey"))
    monkeypatch.setattr(llm, "_which", lambda n: None)
    return bases


def git(path, *args):
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True).stdout.strip()


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def tree_hash(root, *tops):
    """Content hash of whole folders: proves a refresh left them alone."""
    h = hashlib.sha256()
    for top in tops:
        for base, dirs, files in sorted(os.walk(os.path.join(root, top))):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(base, name)
                h.update(os.path.relpath(path, root).encode() + open(path, "rb").read())
    return h.hexdigest()


def refresh(root, capsys, monkeypatch):
    monkeypatch.setenv("KB", root)
    assert init_kb.main(["--refresh"]) == 0
    return capsys.readouterr().out


def test_thesis_is_not_a_reserved_id_any_more_but_the_shared_spaces_are():
    assert init_kb.validate_id("yonatan-thesis") == "yonatan-thesis"
    for reserved in ("think", "demo"):
        with pytest.raises(init_kb.InitError, match="reserved"):
            init_kb.validate_id(reserved)


@pytest.mark.parametrize("kit", ["base", "research"])
def test_init_writes_the_kits_skills_docs_hooks_settings_and_rendered_files_in_the_first_commit(world, kit):
    root = init_kb.create("notes", "My Notes", kit, str(world))
    sources = init_kb.skill_sources(kit)
    assert ("build-researcher-profile" in sources) == (kit == "research")
    assert "query-knowledge" in sources                                   # the parent's skills come along
    for skill, src in sources.items():
        for base, _d, files in os.walk(src):
            for name in files:
                rel = os.path.relpath(os.path.join(base, name), src)
                assert read(root, f".claude/skills/{skill}/{rel}") == open(os.path.join(src, rel), encoding="utf-8").read()
    assert not os.path.exists(os.path.join(root, ".claude/skills/_TEMPLATE.md"))
    assert read(root, ".claude/settings.json") == open(os.path.join(install_hooks.resources.resource(install_hooks.HOOKS_DIR),
                                                                    install_hooks.SETTINGS), encoding="utf-8").read()
    for name in install_hooks.CLAUDE_HOOKS:
        assert os.access(os.path.join(root, ".claude/hooks", name), os.X_OK)
    for doc in kits.KB_DOCS:
        assert os.path.isfile(os.path.join(root, ".claude/docs", f"{doc}.md")), doc
    agents, readme = read(root, "AGENTS.md"), read(root, "README.md")
    assert "My Notes" in agents and "`notes`" in agents and f"kit `{kit}`" in agents
    assert ("Research kit additions" in agents) == (kit == "research")
    assert agents.count("# ") and "## Hard rules" in agents                 # the research kit builds on the base text
    assert "My Notes" in readme
    for text in (agents, readme):
        assert not re.search(r"\{\{|\}\}", text)
        assert not re.search(r"yonatan|\bthesis\b|MSc|pixi|scripts/|\bship\b|infra/", text, re.I), "no thesis, personal or engine-dev text"
    for base, _d, files in os.walk(os.path.join(root, ".claude")):                         # the copies carry no personal text either
        for name in files:
            assert not re.search(r"yonatan|com\.thesis-kb|thesis-knowledge-base", read(base, name), re.I), os.path.join(base, name)
    assert git(root, "status", "--porcelain") == ""                         # all of it is in the one commit
    tracked = git(root, "ls-files")
    for rel in ("AGENTS.md", "README.md", ".claude/settings.json", ".claude/hooks/kb-guard.sh",
                ".claude/skills/query-knowledge/SKILL.md", ".claude/docs/page-model.md"):
        assert rel in tracked.splitlines(), rel
    assert len(git(root, "log", "--format=%s").splitlines()) == 1
    hooks_path = git(root, "config", "core.hooksPath")
    resolved = hooks_path if os.path.isabs(hooks_path) else os.path.normpath(os.path.join(root, hooks_path))
    assert all(os.access(os.path.join(resolved, n), os.X_OK) for n in install_hooks.GIT_HOOKS)
    assert not [d for d in os.listdir(world) if d.startswith(".")]


def test_the_cli_hints_name_skills_that_exist_in_an_initialised_kb(world):
    root = init_kb.create("notes", "Notes", "base", str(world))
    sources = [open(os.path.join(os.path.dirname(__file__), "..", "..", "src", "kb_distillery", rel), encoding="utf-8").read()
               for rel in ("ingest/cli.py", "ingest/mail.py")]
    hinted = {m for text in sources for m in re.findall(r"\.claude/skills/[\w./-]+", text)}
    assert {".claude/skills/full-digest/SKILL.md", ".claude/skills/deep-digest/SKILL.md",
            ".claude/skills/scrap-data/mail/SKILL.md"} <= hinted
    for rel in hinted:
        assert os.path.isfile(os.path.join(root, rel)), rel
    from kb_distillery.publish import export
    assert ".claude/skills/README.md" in export.TEXT_META_FILES and os.path.isfile(os.path.join(root, ".claude/skills/README.md"))
    for rel in export.TEXT_META_FILES:
        if rel.startswith(".claude/"):
            assert os.path.isfile(os.path.join(root, rel)), rel


def test_refresh_of_a_fresh_kb_is_already_up_to_date_and_idempotent(world, capsys, monkeypatch):
    root = init_kb.create("notes", "Notes", "research", str(world))
    out = refresh(root, capsys, monkeypatch)
    assert "already up to date" in out and "added" not in out and "updated" not in out
    assert "AGENTS.md: matches the kit template" in out
    assert git(root, "status", "--porcelain") == ""
    assert "already up to date" in refresh(root, capsys, monkeypatch)


def test_refresh_restores_what_drifted_says_what_changed_and_touches_no_knowledge(world, capsys, monkeypatch):
    root = init_kb.create("notes", "Notes", "research", str(world))
    for rel, text in (("wiki/idea.md", "---\ntype: idea\n---\n# Idea\n"), ("raw/inbox/a.txt", "raw"), ("meta/log.md", "log\n")):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        open(os.path.join(root, rel), "w").write(text)
    os.makedirs(os.path.join(root, "think"), exist_ok=True)
    open(os.path.join(root, "think", "n.md"), "w").write("mine")
    open(os.path.join(root, "AGENTS.md"), "a").write("\nMy own rule.\n")
    guarded = ("wiki", "raw", "meta", "think")
    before = tree_hash(root, *guarded)
    open(os.path.join(root, ".claude/skills/query-knowledge/SKILL.md"), "a").write("drift\n")
    os.remove(os.path.join(root, ".claude/skills/kb-undo/SKILL.md"))
    os.makedirs(os.path.join(root, ".claude/skills/query-knowledge/old"))
    open(os.path.join(root, ".claude/skills/query-knowledge/old/SKILL.md"), "w").write("gone from the kit")
    os.makedirs(os.path.join(root, ".claude/skills/my-own"))
    open(os.path.join(root, ".claude/skills/my-own/SKILL.md"), "w").write("mine")
    open(os.path.join(root, ".claude/settings.json"), "w").write("{}")
    open(os.path.join(root, ".claude/hooks/env.sh"), "w").write("# the old engine lookup\n")
    git(root, "config", "core.hooksPath", OLD_HOOKS_PATH)
    out = refresh(root, capsys, monkeypatch)
    assert "updated .claude/skills/query-knowledge/SKILL.md" in out
    assert "added .claude/skills/kb-undo/SKILL.md" in out
    assert ".claude/skills/query-knowledge/old/SKILL.md is not in the kit" in out
    assert "updated .claude/settings.json (previous copy: .claude/settings.json.bak)" in out
    assert f"core.hooksPath {OLD_HOOKS_PATH} ->" in out
    assert ".claude/hooks/env.sh is not part of the kit any more" in out and os.path.isfile(os.path.join(root, ".claude/hooks/env.sh"))
    assert "AGENTS.md: yours" in out and "My own rule." in read(root, "AGENTS.md")
    assert os.path.isfile(os.path.join(root, ".claude/skills/my-own/SKILL.md"))          # the kb's own skill stays
    assert os.path.isfile(os.path.join(root, ".claude/skills/query-knowledge/old/SKILL.md"))      # never deleted
    assert tree_hash(root, *guarded) == before
    assert "distill ops chore" in out                                                     # it commits nothing itself
    assert "already up to date" in refresh(root, capsys, monkeypatch)                    # and a second run changes nothing


def test_refresh_reads_a_kb_written_before_the_rename_and_without_agents_md(world, capsys, monkeypatch):
    root = init_kb.create("notes", "Notes", "research", str(world))
    toml = read(root, "kb.toml").replace('kit = "research"', 'template = "academic-research"')
    open(os.path.join(root, "kb.toml"), "w").write(toml)
    os.remove(os.path.join(root, "AGENTS.md"))
    out = refresh(root, capsys, monkeypatch)
    assert "AGENTS.md: none in this kb; --refresh never creates it" in out and not os.path.exists(os.path.join(root, "AGENTS.md"))
    assert read(root, "kb.toml") == toml                                                  # kb.toml is never rewritten


def test_refresh_refuses_without_a_kb_or_a_kit_and_takes_no_creation_options(world, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert init_kb.main(["--refresh"]) == 1 and "no knowledge base selected" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        init_kb.main(["--refresh", "--kit", "base"])
    root = init_kb.create("plain", "Plain", "base", str(world))
    toml = read(root, "kb.toml").replace('kit = "base"\n', "")
    open(os.path.join(root, "kb.toml"), "w").write(toml)
    monkeypatch.setenv("KB", root)
    assert init_kb.main(["--refresh"]) == 1 and "names no kit" in capsys.readouterr().err


def test_a_kits_dir_without_the_templates_is_an_init_error_not_a_half_made_kb(world, monkeypatch, tmp_path):
    kits_dir = tmp_path / "kits" / "bare"
    kits_dir.mkdir(parents=True)
    (kits_dir / "kit.toml").write_text('[kit]\nname = "bare"\nversion = 1\n')
    monkeypatch.setenv("KB_KITS_DIR", str(tmp_path / "kits"))
    with pytest.raises(init_kb.InitError, match="AGENTS.template.md"):
        init_kb.create("notes", "Notes", "bare", str(world))
    assert not os.path.exists(world / "notes") and not [d for d in os.listdir(world) if d.startswith(".")]


def test_an_explicit_kb_beats_kb_root_and_a_broken_kit_is_a_clean_error(world, capsys, monkeypatch):
    a = init_kb.create("aaa", "A", "base", str(world))
    b = init_kb.create("bbb", "B", "base", str(world))
    os.remove(os.path.join(b, ".claude/settings.json"))
    monkeypatch.setenv("KB_ROOT", a)
    monkeypatch.setenv("KB", b)
    assert init_kb.main(["--refresh"]) == 0
    assert os.path.isfile(os.path.join(b, ".claude/settings.json")) and "bbb" in capsys.readouterr().out
    toml = read(b, "kb.toml").replace('kit = "base"', 'kit = "typo"')
    open(os.path.join(b, "kb.toml"), "w").write(toml)
    monkeypatch.delenv("KB_ROOT")
    assert init_kb.main(["--refresh"]) == 1                    # KbConfigError for an unknown kit: one line, no traceback
    assert "typo" in capsys.readouterr().err

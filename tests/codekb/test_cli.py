"""`distill code build` and `cards` from a project file and from a kb's kb.toml, and the clear refusals."""
import os
import subprocess
import sys

import pytest

from kb_distillery.codekb import cli
from kb_distillery.codekb.cpp import parser
from tests.codekb import repos


def test_build_then_cards_from_a_project_file(py_project, capsys):
    f = str(py_project.base / "project.yaml")
    assert cli.main_args(["build", f, "--quiet"]) == 0
    assert cli.main_args(["cards", f]) == 0
    out = capsys.readouterr().out
    assert "IR:" in out and "2 cards" in out
    assert (py_project.out / "ir.json").is_file() and (py_project.out / "cards" / "index.json").is_file()


def test_the_kb_toml_code_table_is_the_default_project(tmp_path, monkeypatch, capsys):
    repos.python_repo(tmp_path / "src-core")
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "kb.toml").write_text('[code]\ntiers = ["python"]\nrepos_dir = "../"\n[[code.repos]]\nname = "src-core"\nrole = "focus"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "_kb_root", lambda: kb)
    assert cli.main_args(["build", "--quiet"]) == 0
    assert (kb / ".local" / "code" / "kb" / "ir.json").is_file()


def test_a_missing_checkout_and_a_missing_tree_sitter_say_what_to_do(tmp_path, monkeypatch):
    f = tmp_path / "p.yaml"
    f.write_text("name: p\ntiers: [cpp]\nrepos:\n  - {name: ghost, role: focus}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no checkout for \\['ghost'\\]"):
        cli.main_args(["build", str(f)])
    repos.cpp_repo(tmp_path / "ghost")
    monkeypatch.setattr(parser, "_PARSER", None)
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    with pytest.raises(SystemExit, match=r"kb-distillery\[code\]"):
        cli.main_args(["build", str(f), "--quiet"])


def test_help_needs_no_knowledge_base():
    r = subprocess.run([sys.executable, "-m", "kb_distillery.cli", "code", "--help"], capture_output=True, text=True, timeout=60,
                       env={**{k: v for k, v in os.environ.items() if not k.startswith("KB")}, "KB_DISTILLERY_HOME": "/nonexistent"})
    assert r.returncode == 0 and "distill code build" in r.stdout

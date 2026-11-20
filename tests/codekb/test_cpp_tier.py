"""The C++ tier (tree-sitter) on a fixture repo with a GitLab remote. Skipped where the optional `code` extra is not installed."""
import sys

import pytest

from kb_distillery.codekb import pipeline
from kb_distillery.codekb.cpp import parser
from kb_distillery.codekb.generic import project
from kb_distillery.codekb.generic.graph import Graph
from tests.codekb import repos


def make(tmp_path, tiers=("cpp",)):
    repos.cpp_repo(tmp_path / "native")
    return project.from_dict({"name": "n", "tiers": list(tiers), "repos": [{"name": "native", "role": "focus"}]}, tmp_path, "t")


def test_a_missing_tree_sitter_is_one_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "_PARSER", None)
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    p = make(tmp_path)
    with pytest.raises(parser.MissingParser, match=r"kb-distillery\[code\]"):
        pipeline.build(p, quiet=True)


def test_classes_includes_and_calls(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    g = pipeline.build(make(tmp_path), quiet=True)
    assert g.nodes["class:shapes::Circle"]["doc"] == "A circle." and g.nodes["class:shapes::Circle"]["n_methods"] == 3
    assert any(e["src"] == "file:native:src/main.cpp" and e["dst"] == "file:native:include/foo.h" and e["kind"] == "includes" for e in g.edges)
    assert not any(e["dst"] == "ext:vector" for e in g.edges)      # <system> headers are not facts
    assert any(e["src"] == "func:main" and e["dst"] == "func:shapes::Circle::area" and e["conf"] == "typed" for e in g.edges)
    assert g.nodes["file:native:src/foo.cpp"]["lang"] == "cpp" and g.nodes["file:native:src/foo.cpp"]["loc"] > 1


def test_cards_link_to_a_gitlab_remote(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    p = make(tmp_path)
    pipeline.build(p, quiet=True)
    pipeline.cards(p)
    sha = Graph.load(p.out).meta["repos"]["native"]["sha"]
    text = (p.out / "cards" / "ir-native-dir-include.md").read_text()
    assert f"https://gitlab.example.com/group/native/-/blob/{sha}/include/foo.h#L4" in text


def test_include_prefix_resolves_across_repositories(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    repos.cpp_repo(tmp_path / "native")
    repos.python_repo(tmp_path / "app")
    repos.commit(tmp_path / "app", "cpp", {"src/use.cpp": '#include "shapes/foo.h"\nint f() { return 1; }\n'})
    p = project.from_dict({"name": "n", "tiers": ["cpp"], "repos": [
        {"name": "app", "role": "focus"}, {"name": "native", "role": "platform", "include_prefix": "shapes"}]}, tmp_path, "t")
    g = pipeline.build(p, quiet=True)
    assert any(e["src"] == "file:app:src/use.cpp" and e["dst"] == "file:native:include/foo.h" for e in g.edges)

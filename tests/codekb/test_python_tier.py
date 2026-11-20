"""The generic core and the Python tier on a fixture repo with a merged pull request: no tree-sitter, no network."""
import json
import re
import sys

from kb_distillery.codekb import pipeline
from kb_distillery.codekb.generic.graph import Graph


def test_ir_layers_and_history(built):
    g = Graph.load(built.out)
    assert g.meta["tiers"] == ["python"] and g.meta["generator"] == pipeline.GENERATOR
    kinds = {(e["layer"], e["kind"]) for e in g.edges}
    assert {("include", "includes"), ("symbol", "defines"), ("symbol", "inherits"), ("call", "calls"), ("history", "touches"),
            ("history", "cochange"), ("config", "defines"), ("config", "reads_env")} <= kinds
    assert "class:pkg.app.Runner" in g.nodes and g.nodes["class:pkg.app.Runner"]["doc"] == "Runs things."
    assert any(e["src"] == "class:pkg.app.Runner" and e["dst"] == "class:pkg.app.Base" for e in g.edges)
    assert any(e["src"] == "func:pkg.app.Runner.again" and e["dst"] == "func:pkg.app.Runner.run" for e in g.edges)
    assert any(e["src"] == "func:pkg.app.Runner.run" and e["dst"] == "func:pkg.util.slugify" for e in g.edges)
    assert "env:APP_HOME" in g.nodes and g.nodes["file:core:pkg/app.py"]["entry"] is True
    mr = g.nodes["mr:core!7"]
    assert mr["title"] == "Add the slug helper" and mr["url"] == "https://github.com/octocat/core/pull/7" and mr["author"] == "octocat"
    co = [e for e in g.edges if e["kind"] == "cochange"]
    assert [(e["src"], e["dst"], e["n"]) for e in co] == [("file:core:pkg/app.py", "file:core:pkg/util.py", 1)]
    assert g.nodes["file:core:pkg/util.py"]["n_commits"] == 3 and (built.out / "ir.db").is_file()


def test_python_tier_needs_no_tree_sitter(py_project, monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    monkeypatch.setitem(sys.modules, "tree_sitter_cpp", None)
    g = pipeline.build(py_project, quiet=True)
    assert "class:pkg.app.Runner" in g.nodes


def test_cards_are_cited_by_fact_id_with_permalinks(built):
    index = json.loads((built.out / "cards" / "index.json").read_text())
    assert {c["slug"] for c in index} == {"ir-core-py-pkg", "ir-history-core"}
    text = (built.out / "cards" / "ir-core-py-pkg.md").read_text()
    sha = Graph.load(built.out).meta["repos"]["core"]["sha"]
    assert f"https://github.com/octocat/core/blob/{sha}/pkg/app.py#L" in text
    rows = re.findall(r"^\| (F[0-9a-f]{5}) \|", text, re.M)
    assert len(rows) == len(set(rows)) == next(c["facts"] for c in index if c["slug"] == "ir-core-py-pkg")
    assert f'  core: "{sha}"' in text and "octocat" not in text.split("---")[1]
    assert all(f["anchors"] for c in index for f in c["fact_list"] if c["slug"] == "ir-core-py-pkg" and f["section"] == "Functions")


def test_a_rebuild_is_byte_identical(py_project):
    cards = py_project.out / "cards"
    pipeline.build(py_project, quiet=True)
    pipeline.cards(py_project)
    first = {p.name: p.read_bytes() for p in cards.glob("*.md")}
    pipeline.build(py_project, quiet=True)
    pipeline.cards(py_project)
    assert first == {p.name: p.read_bytes() for p in cards.glob("*.md")}


def test_drift_warning_for_an_empty_layer_and_a_shallow_history(tmp_path):
    from kb_distillery.codekb.generic import project
    from tests.codekb import repos
    repos.write(tmp_path / "bare", {"notes.txt": "x"})
    repos.git(tmp_path / "bare", "init", "-q")
    repos.commit(tmp_path / "bare", "one", {"notes.txt": "x"})
    p = project.from_dict({"name": "d", "tiers": ["python"], "repos": [{"name": "bare", "role": "focus"}]}, tmp_path, "t")
    g = pipeline.build(p, quiet=True)
    assert any("no facts in layer(s) include, symbol" in w for w in g.meta["drift"]) and any("shallow" in w for w in g.meta["drift"])


def test_a_plain_folder_has_no_history_and_is_pinned_by_content(tmp_path):
    from kb_distillery.codekb.generic import project
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    p = project.from_dict({"name": "d", "tiers": ["python"], "repos": [{"name": "scripts", "path": "scripts", "git": False, "role": "focus",
                                                                           "web": "https://example.com/blob/main/scripts"}]}, tmp_path, "t")
    g = pipeline.build(p, quiet=True)
    sha = g.meta["repos"]["scripts"]["sha"]
    pipeline.build(p, quiet=True)
    assert Graph.load(p.out).meta["repos"]["scripts"]["sha"] == sha
    pipeline.cards(p)
    assert "(https://example.com/blob/main/scripts/a.py#L1)" in (p.out / "cards" / "ir-scripts-py-root.md").read_text()
    assert not any(c.name.startswith("ir-history") for c in (p.out / "cards").glob("*.md"))

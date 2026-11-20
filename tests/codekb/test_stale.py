"""Staleness: build the cards at two commits and say which facts a wiki page may still cite."""
import json

from kb_distillery.codekb import pipeline
from kb_distillery.codekb.generic import project, staleness
from tests.codekb import repos


def build_at(tmp_path, name):
    f = tmp_path / "project.yaml"
    p = project.load(f)
    p.out = tmp_path / name
    pipeline.build(p, quiet=True)
    pipeline.cards(p)
    return p.out


def test_added_removed_and_moved_facts(py_project, tmp_path):
    core = tmp_path / "core"
    old = build_at(tmp_path, "old")
    # util.py: a comment above everything moves every line (not a change); `extra` is removed; `shout` is new
    text = (core / "pkg/util.py").read_text(encoding="utf-8")
    text = "# a new first line\n" + text.replace('\n\ndef extra():\n    return 3\n', "") + "\n\ndef shout(text):\n    return text.upper()\n"
    repos.commit(core, "edit util", {"pkg/util.py": text})
    new = build_at(tmp_path, "new")
    out = staleness.main(old, new)
    card = next(c for c in out["cards"] if c["card"] == "ir-core-py-pkg")
    assert card["added"] >= 1 and card["removed"] >= 1 and card["moved_only"] >= 1
    assert any("shout" in t for t in card["examples_added"]) and any("extra" in t for t in card["examples_removed"])
    gone = set(card["fact_ids_gone"])
    old_facts = {f["text"]: f["id"] for f in json.loads((old / "cards/index.json").read_text())[0]["fact_list"]}
    assert old_facts and any("extra" in t and i in gone for t, i in old_facts.items())
    assert json.loads((new / "staleness.json").read_text())["facts_added"] == out["facts_added"]
    assert set(out["old"]) == {"core"} and out["old"]["core"] != out["new"]["core"]


def test_the_same_commit_is_not_stale(py_project, tmp_path):
    a = build_at(tmp_path, "a")
    b = build_at(tmp_path, "b")
    out = staleness.main(a, b)
    assert out["facts_added"] == out["facts_removed"] == out["facts_moved_only"] == 0 and out["cards_changed"] == 0

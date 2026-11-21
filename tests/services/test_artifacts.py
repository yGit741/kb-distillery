"""services.artifacts: a kb's artifact layer (artifacts/graph.json) and the fact ids its pages cite.

Fixture: tests/fixtures/artifacts/kb-code, copied to a temp folder (no real kb, no network)."""
import json
import shutil
from pathlib import Path

import pytest

from kb_distillery.services import artifacts

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "artifacts" / "kb-code"


@pytest.fixture
def kb(tmp_path):
    root = tmp_path / "kb-code"
    shutil.copytree(FIXTURE, root)
    return root


def test_load_reads_the_graph_and_adds_the_cites_of_each_page(kb):
    data = artifacts.load(kb)
    assert [n["id"] for n in data["nodes"]][0] == "repo:r"
    assert data["views"][0]["id"] == "dependencies"
    # in order of first mention, each id once; only facts some card knows; index.md and a page citing nothing are left out
    assert data["cites"] == {"buffer-copy": ["F0a1b2", "F3c4d5"], "build-graph": ["F3c4d5"]}


def test_a_fact_id_is_F_and_five_lower_case_hex_digits_standing_alone():
    assert artifacts.FACT.findall("F0a1b2 F0A1B2 XF0a1b2 F0a1b2c (F3c4d5)") == ["F0a1b2", "F3c4d5"]


def test_no_file_no_layer(kb):
    (kb / "artifacts" / "graph.json").unlink()
    assert artifacts.load(kb) is None


@pytest.mark.parametrize("text", ["{not json", "[]", json.dumps({"nodes": []}), json.dumps({"links": []})])
def test_an_unreadable_or_empty_graph_is_no_layer(kb, text):
    (kb / "artifacts" / "graph.json").write_text(text, encoding="utf-8")
    assert artifacts.load(kb) is None


def test_links_default_to_none_and_a_kb_without_wiki_cites_nothing(tmp_path):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "graph.json").write_text(json.dumps({"nodes": [{"id": "a", "type": "File", "name": "a"}]}), encoding="utf-8")
    data = artifacts.load(tmp_path)
    assert data["links"] == [] and data["cites"] == {}


def test_hidden_folders_of_the_wiki_are_not_read(kb):
    (kb / "wiki" / ".trash").mkdir()
    (kb / "wiki" / ".trash" / "old.md").write_text("F0a1b2", encoding="utf-8")
    assert "old" not in artifacts.load(kb)["cites"]

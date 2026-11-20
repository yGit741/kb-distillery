"""Export: cards into a kb's raw/ as one kb(catalog) step (the ops flow), corpus rows, the artifact graph, the CLI."""
import json
import os
import re
from unittest import mock

import pytest

from kb_distillery.codekb import cli, export, pipeline
from kb_distillery.codekb.cites import CARD_DIR
from kb_distillery.codekb.generic import artifacts
from kb_distillery.vault.schema import RAW_NAME
from tests.ops.test_view import ENV, commits, git, head_files, make_repo

SUBJECT = re.compile(r"^kb\(catalog\): (?P<summary>.+) \(kb-\d+\.\d+\.\d+\)$")


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path / "kb"), gitignore="meta/.ops/\n.local/\n")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        yield root


def corpus(root):
    rows = {}
    with open(os.path.join(root, "meta", "corpus.tsv"), encoding="utf-8") as f:
        for line in f:
            if not line.startswith(("#", "path\t")):
                parts = line.rstrip("\n").split("\t")
                rows[parts[0]] = parts
    return rows


def test_cards_become_one_catalog_step_with_skip_rows(built, kb):
    n = commits(kb)
    r = export.export(built.out / "cards", kb)
    assert sorted(r["added"]) == ["ir-core-py-pkg.md", "ir-history-core.md"] and r["commit"] and not r["updated"]
    assert commits(kb) == n + 1 and SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "code IR: 2 cards"
    assert {f"{CARD_DIR}/ir-core-py-pkg.md", f"{CARD_DIR}/ir-history-core.md", "meta/corpus.tsv"} <= head_files(kb)
    rows = corpus(kb)
    assert rows[f"{CARD_DIR}/ir-history-core.md"][2:4] == ["printed-docs", "skip"] and len(rows[f"{CARD_DIR}/ir-history-core.md"][1]) == 12
    assert all(re.match(RAW_NAME, name) for name in os.listdir(os.path.join(kb, CARD_DIR)))


def test_exporting_twice_commits_nothing_and_a_changed_card_is_replaced(built, kb, tmp_path):
    export.export(built.out / "cards", kb)
    n = commits(kb)
    again = export.export(built.out / "cards", kb)
    assert again["commit"] is None and sorted(again["unchanged"]) == ["ir-core-py-pkg.md", "ir-history-core.md"] and commits(kb) == n
    card = built.out / "cards" / "ir-history-core.md"
    card.write_text(card.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    changed = export.export(built.out / "cards", kb)
    assert changed["updated"] == ["ir-history-core.md"] and commits(kb) == n + 1
    assert corpus(kb)[f"{CARD_DIR}/ir-history-core.md"][3] == "skip"
    (built.out / "cards" / "ir-history-core.md").unlink()
    assert export.export(built.out / "cards", kb)["gone"] == ["ir-history-core.md"]


def test_an_open_session_and_a_read_only_kb_refuse(built, kb):
    with mock.patch("kb_distillery.ops.core.current_session", return_value={"op": "refine", "target": "x"}):
        with pytest.raises(export.ExportError, match="ops session is open"):
            export.export(built.out / "cards", kb)
    with mock.patch.dict(os.environ, {"KB_READ_ONLY": "1"}):
        with pytest.raises(export.ExportError, match="(?i)read.only"):
            export.export(built.out / "cards", kb)
    assert not os.path.exists(os.path.join(kb, CARD_DIR))


def test_no_cards_says_what_to_run(tmp_path, kb):
    (tmp_path / "empty").mkdir()
    with pytest.raises(export.ExportError, match="distill code cards"):
        export.export(tmp_path / "empty", kb)


def test_the_artifact_graph(built, tmp_path):
    dest = tmp_path / "artifacts" / "graph.json"
    s = artifacts.export(built, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert s["nodes"] == len(data["nodes"]) and data["version"] == 1 and data["views"] == [] and data["project"] == "demo"
    types = {n["type"] for n in data["nodes"]}
    assert {"Repo", "Folder", "File", "Class", "Function"} <= types
    repo = data["repos"]["core"]
    assert repo["web"] == f"https://github.com/octocat/core/blob/{repo['sha']}"
    assert {l["kind"] for l in data["links"]} >= {"imports", "calls", "inherits", "co-changes"}
    assert data["nodes"][0]["id"] < data["nodes"][-1]["id"]                         # sorted: the same commits, the same file
    assert set(data["cards"]) == {"ir-core-py-pkg", "ir-history-core"} and data["cards"]["ir-core-py-pkg"]["facts"]
    first = dest.read_bytes()
    artifacts.export(built, dest)
    assert dest.read_bytes() == first
    node_ids = {n["id"] for n in data["nodes"]}
    assert all(i in node_ids for c in data["cards"].values() for ids in c["facts"].values() for i in ids)


def test_cli_kb_end_to_end(py_project, kb, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_kb_root", lambda: __import__("pathlib").Path(kb))
    project_file = str(py_project.base / "project.yaml")
    (py_project.base / "kb-wiki").mkdir()
    assert cli.main_args(["kb", project_file, "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "IR:" in out and "added: 2" in out and "artifact graph:" in out
    assert os.path.isfile(os.path.join(kb, "artifacts", "graph.json")) and not pipeline.drift(py_project, __import__("kb_distillery.codekb.generic.graph", fromlist=["Graph"]).Graph.load(py_project.out))
    assert cli.main_args(["kb", project_file, "--no-build", "--no-graph"]) == 0
    assert "unchanged: 2" in capsys.readouterr().out


def test_a_failed_step_is_repaired_by_the_next_export(built, kb):
    from kb_distillery.ops import core
    with mock.patch("kb_distillery.ops.core.commit_op", side_effect=core.OpsError("lint refused")):
        with pytest.raises(export.ExportError, match="lint refused"):
            export.export(built.out / "cards", kb)
    n = commits(kb)
    again = export.export(built.out / "cards", kb)
    assert again["commit"] and commits(kb) == n + 1 and sorted(again["unchanged"]) == ["ir-core-py-pkg.md", "ir-history-core.md"]
    assert {f"{CARD_DIR}/ir-core-py-pkg.md", "meta/corpus.tsv"} <= head_files(kb) and len(corpus(kb)) == 2


def test_a_read_only_kb_is_a_clean_refusal_for_the_cli(built, kb):
    with mock.patch.dict(os.environ, {"KB_READ_ONLY": "1"}):
        with pytest.raises(export.ExportError):
            export.export(built.out / "cards", kb)

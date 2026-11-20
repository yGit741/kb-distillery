"""Experiment runs (schema 1.6): a run bundle under raw/experiments/<run>/ is one `run` source."""
import importlib
import json

import pytest

from kb_distillery.vault.schema import (RAW_EXPERIMENTS, RAW_NESTED, RAW_SUBDIRS, RUN_ITEM,
                                        unit_slug_for_raw, unit_type_for_raw)


def test_experiments_is_a_nested_raw_format():
    assert RAW_EXPERIMENTS in RAW_SUBDIRS and RAW_EXPERIMENTS in RAW_NESTED
    assert RUN_ITEM == "run.md"


def test_a_run_bundle_is_a_run_source_named_by_its_folder():
    rel = "raw/experiments/gaussian-ratio-sweep-ab12cd34/run.md"
    assert unit_type_for_raw(rel) == "run"
    assert unit_slug_for_raw(rel, "run") == "run-gaussian-ratio-sweep-ab12cd34"


def test_lint_binds_bundle_files_to_run_md():
    from kb_distillery.lint.lint import asset_source
    on_disk = {"raw/experiments/r1/run.md", "raw/experiments/r1/history.csv", "raw/experiments/r1/config.json"}
    assert asset_source("raw/experiments/r1/history.csv", on_disk) == "raw/experiments/r1/run.md"
    assert asset_source("raw/experiments/r1/config.json", on_disk) == "raw/experiments/r1/run.md"
    assert asset_source("raw/experiments/r1/run.md", on_disk) is None
    assert asset_source("raw/experiments/other/history.csv", on_disk) is None


def _bundle(folder, name="ratio sweep"):
    folder.mkdir(parents=True)
    (folder / "run.md").write_text("# run\n")
    (folder / "run.json").write_text(json.dumps({"id": "ab12cd34", "name": name}))
    (folder / "history.csv").write_text("gamma,lambda_min\n1.5,0.05\n")


def test_catalog_detects_a_run_bundle(tmp_path, monkeypatch):
    from kb_distillery.ingest import catalog
    d = tmp_path / "raw" / "inbox" / "run-sweep"
    d.mkdir(parents=True)
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="run-<name>"):
        catalog.detect_format("raw/inbox/run-sweep")              # no run.md yet: not a bundle
    (d / "run.md").write_text("# sweep\n")
    assert catalog.detect_format("raw/inbox/run-sweep") == "experiments"


def test_catalog_moves_a_run_bundle_and_never_replaces_one(tmp_path, monkeypatch):
    from kb_distillery.ingest import catalog
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    monkeypatch.setattr(catalog, "_run_lint", lambda: None)
    joined = []
    monkeypatch.setattr(catalog, "_join", lambda *a: joined.append(a))
    _bundle(tmp_path / "raw" / "inbox" / "run-sweep")
    dest, slug = catalog.catalog_run("raw/inbox/run-sweep", collection="exp-ratio")
    assert dest == "raw/experiments/sweep" and slug is None
    assert (tmp_path / "raw" / "experiments" / "sweep" / "history.csv").exists()
    assert joined == [("raw/experiments/sweep/run.md", "exp-ratio", "ratio sweep")]   # titled by the run's name
    _bundle(tmp_path / "raw" / "inbox" / "run-sweep", name="another")
    with pytest.raises(ValueError, match="immutable"):             # a cataloged run is a frozen record
        catalog.catalog_run("raw/inbox/run-sweep")
    assert json.loads((tmp_path / "raw" / "experiments" / "sweep" / "run.json").read_text())["name"] == "ratio sweep"


def test_ops_target_of_a_run_bundle_is_its_folder():
    from kb_distillery.ops.wrap import _target
    assert _target(["raw/inbox/run-sweep/history.csv", "raw/inbox/run-sweep/run.md"], ["scrap-wandb"]) == "sweep"


def test_relation_gates_for_empirical_kinds():
    from kb_distillery.graph import propose
    for kind in ("tests", "supports", "refutes"):
        assert kind in propose.KINDS and kind in propose.MEANING
        assert "conjecture" in propose.GATES[kind][1]
    assert propose.GATES["tests"][0] == frozenset({"experiment", "run"})
    assert "result" in propose.GATES["supports"][0] and "paper" in propose.GATES["refutes"][0]


def test_migration_0016_changes_no_page_and_produces_1_6(tmp_path):
    mig = importlib.import_module("kb_distillery.migrations.0016_experiment_types")
    assert mig.PRODUCES == (1, 6)
    assert mig.apply(str(tmp_path)) == []
    assert mig.apply(str(tmp_path), dry_run=True) == []

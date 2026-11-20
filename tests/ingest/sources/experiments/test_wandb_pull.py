"""scrap-wandb: a W&B run becomes a run bundle in the inbox (offline: the API is a fake)."""
import csv
import json
import os

import pytest

from kb_distillery.ingest import catalog
from kb_distillery.ingest import resolve as resolve_mod
from kb_distillery.ingest.sources.experiments import wandb_pull as wp


class FakeEntry:
    def __init__(self, art, path):
        self.art, self.path = art, path

    def download(self, root):
        if self.art.broken:
            raise OSError("download failed")
        self.art.downloaded.append(self.path)
        dest = os.path.join(root, self.path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(self.art.files[self.path])
        return dest


class FakeManifest:
    def __init__(self, files):
        self.entries = dict.fromkeys(files)


class FakeArtifact:
    def __init__(self, name, type_, files=None, size=1000, broken=False):
        self.name, self.type, self.size, self.files, self.broken = name, type_, size, files or {}, broken
        self.manifest, self.downloaded = FakeManifest(self.files), []

    def get_entry(self, path):
        return FakeEntry(self, path)


class FakeRun:
    entity, project = "octocat", "demo"
    group, job_type, commit, notes = "ratio-sweep", "ratio-sweep", "a1b2c3d", "E1: sweep gamma"
    created_at = "2026-01-02T03:04:05Z"

    def __init__(self, run_id="ab12cd34", name="Ratio sweep | gaussian", state="finished", artifacts=None, steps=3):
        self.id, self.name, self.state = run_id, name, state
        self.url = f"https://wandb.example.com/octocat/demo/runs/{run_id}"
        self.tags = ["kb", "gaussian"]
        self.config = {"N": 100, "n_grid": [20, 40], "_wandb": {"cli": "x"}, "features": {"_type": "gaussian", "std": 1},
                       "hf_token": "s3cr3t", "nested": {"api_key": "s3cr3t", "password": ""}}
        self.summary = {"peak_gamma": 1.0, "windows": {"_type": "table-file", "path": "p"}, "_wandb": {"runtime": 3},
                        "_step": 2, "_runtime": 3.5}
        self._steps = steps
        self._artifacts = artifacts if artifacts is not None else [
            FakeArtifact("grid:v0", "result-grid",
                         {"grid.table.json": json.dumps({"_type": "table", "columns": ["seed", "gamma"],
                                                         "data": [[0, 1.5], [1, 1.5]]})}),
            FakeArtifact("source-demo:v0", "code", {"run.py": "print(1)"}),
            FakeArtifact("weights:v0", "model", {"w.bin": "x"}, size=900 * 1024 * 1024)]

    def scan_history(self):
        for i in range(self._steps):
            yield {"lambda_min": 0.1 * i, "_runtime": 1.5, "_timestamp": 1.0, "gamma": 1.0 + i, "_step": i,
                   "windows": {"_type": "table-file"}}
        yield {"_step": self._steps, "_runtime": 2.0}                 # a system-only step carries no metric

    def logged_artifacts(self):
        return self._artifacts


class FakeApi:
    def __init__(self, runs):
        self._runs, self.asked = runs, []

    def run(self, path):
        self.asked.append(path)
        return next(r for r in self._runs if path.endswith("/" + r.id))

    def runs(self, path, filters=None):
        self.asked.append((path, filters))
        return list(self._runs)


@pytest.mark.parametrize("source,want", [
    ("https://wandb.ai/octocat/demo/runs/ab12cd34", ("octocat", "demo", "ab12cd34")),
    ("https://host.example.com/wandb/octocat/demo/runs/ab12cd34?nw=1", ("octocat", "demo", "ab12cd34")),
    ("https://host.example.com/wandb/octocat/demo/runs/ab12cd34/overview", ("octocat", "demo", "ab12cd34")),
    ("octocat/demo/runs/ab12cd34", ("octocat", "demo", "ab12cd34")),
    ("octocat/demo/ab12cd34", ("octocat", "demo", "ab12cd34")),
    ("octocat/demo", ("octocat", "demo", None)),
    ("https://wandb.ai/octocat/demo", ("octocat", "demo", None)),
    ("https://wandb.ai/octocat/demo/workspace?nw=abc", ("octocat", "demo", None)),
    ("https://host.example.com/wandb/octocat/demo/table", ("octocat", "demo", None)),
    ("https://wandb.ai/octocat/demo/runs", ("octocat", "demo", None)),
    ("octocat/demo/runs", ("octocat", "demo", None)),
])
def test_parse_ref(source, want):
    assert wp.parse_ref(source) == want


@pytest.mark.parametrize("source", ["", "demo", "runs/ab12cd34", "a/b/c/d", "https://wandb.ai/octocat"])
def test_parse_ref_refuses_what_is_not_a_run_or_project(source):
    with pytest.raises(ValueError, match="not a W&B run or project"):
        wp.parse_ref(source)


def test_a_run_becomes_a_bundle(tmp_path):
    run = FakeRun()
    rel = wp.pull_run(run, root=str(tmp_path))
    assert rel == "raw/inbox/run-ratio-sweep-gaussian-ab12cd34"
    d = tmp_path / rel
    assert sorted(os.listdir(d)) == ["grid.csv", "history.csv", "run.json", "run.md"]
    data = json.loads((d / "run.json").read_text())
    assert (data["id"], data["entity"], data["project"], data["name"]) == ("ab12cd34", "octocat", "demo", run.name)
    assert data["config"] == {"N": 100, "n_grid": [20, 40], "features": {"_type": "gaussian", "std": 1},
                              "hf_token": "(redacted)", "nested": {"api_key": "(redacted)", "password": ""}}
    assert "s3cr3t" not in (d / "run.json").read_text() + (d / "run.md").read_text()   # no W&B internals, no secrets
    assert data["summary"] == {"peak_gamma": 1.0, "windows": "(table-file)"}
    assert data["history"] == {"rows": 3, "columns": ["_step", "gamma", "lambda_min"], "truncated": False}
    assert data["tables"] == [{"file": "grid.csv", "rows": 2, "columns": ["seed", "gamma"], "artifact": "grid:v0"}]
    hist = list(csv.DictReader(open(d / "history.csv", encoding="utf-8")))
    assert [r["gamma"] for r in hist] == ["1.0", "2.0", "3.0"] and "_runtime" not in hist[0]
    assert list(csv.reader(open(d / "grid.csv", encoding="utf-8"))) == [["seed", "gamma"], ["0", "1.5"], ["1", "1.5"]]
    grid, code, weights = run.logged_artifacts()
    assert grid.downloaded == ["grid.table.json"] and not code.downloaded and not weights.downloaded   # code, big files: listed only
    md = (d / "run.md").read_text()
    assert md.startswith("# Ratio sweep | gaussian\n")
    for line in (f"- Run: {run.url}", "- Project: octocat/demo", "- Code commit: a1b2c3d", "E1: sweep gamma",
                 "| `N` | 100 |", "| `peak_gamma` | 1.0 |", "`history.csv`: 3 rows, 3 columns.",
                 "- `grid.csv`: 2 rows; columns `seed`, `gamma`", "- `grid:v0` (result-grid, 1.0 kB): kept as `grid.csv`",
                 "- `source-demo:v0` (code, 1.0 kB): not copied, see the run",
                 "- `weights:v0` (model, 943.7 MB): not copied, see the run"):
        assert line in md, line
    assert os.listdir(tmp_path / ".cache" / "wandb-build") == []


def test_history_is_capped(tmp_path):
    rel = wp.pull_run(FakeRun(steps=10, artifacts=[]), max_rows=4, root=str(tmp_path))
    data = json.loads((tmp_path / rel / "run.json").read_text())
    assert data["history"]["rows"] == 4 and data["history"]["truncated"]
    assert "4 rows (truncated)" in (tmp_path / rel / "run.md").read_text()


def test_a_run_without_steps_or_artifacts(tmp_path):
    rel = wp.pull_run(FakeRun(steps=0, artifacts=[]), root=str(tmp_path))
    assert sorted(os.listdir(tmp_path / rel)) == ["run.json", "run.md"]
    assert "No logged steps." in (tmp_path / rel / "run.md").read_text()


def test_tables_of_one_name_do_not_collide_and_only_tables_are_read(tmp_path):
    table = json.dumps({"columns": ["a"], "data": [[1]]})
    both = FakeArtifact("run-ab12cd34-grid:v0", "run_table",
                        {"a/grid.table.json": table, "b/grid.table.json": table, "c/grid.table.json": table,
                         "history.table.json": table, "notes.json": "{}", "weights.bin": "x"})
    arts = [FakeArtifact("grid:v0", "result-grid", {"grid.table.json": table}), both]
    rel = wp.pull_run(FakeRun(artifacts=arts), root=str(tmp_path))
    assert sorted(os.listdir(tmp_path / rel)) == [
        "grid-run-ab12cd34-grid-v0-2.csv", "grid-run-ab12cd34-grid-v0-3.csv", "grid-run-ab12cd34-grid-v0.csv",
        "grid.csv", "history-run-ab12cd34-grid-v0.csv", "history.csv", "run.json", "run.md"]
    assert sorted(both.downloaded) == ["a/grid.table.json", "b/grid.table.json", "c/grid.table.json",
                                       "history.table.json"]                      # never notes.json or weights.bin
    files = [t["file"] for t in json.loads((tmp_path / rel / "run.json").read_text())["tables"]]
    assert len(files) == len(set(files)) == 5


def test_a_failed_pull_leaves_nothing_and_keeps_the_old_bundle(tmp_path):
    root = str(tmp_path)
    bad = [FakeArtifact("grid:v0", "result-grid", {"grid.table.json": "{}"}, broken=True)]
    with pytest.raises(OSError):
        wp.pull_run(FakeRun(artifacts=bad), root=root)
    assert not (tmp_path / "raw").exists() and os.listdir(tmp_path / ".cache" / "wandb-build") == []
    rel = wp.pull_run(FakeRun(), root=root)
    with pytest.raises(OSError):
        wp.pull_run(FakeRun(name="renamed", artifacts=bad), force=True, root=root)
    assert json.loads((tmp_path / rel / "run.json").read_text())["name"] == "Ratio sweep | gaussian"
    assert os.listdir(tmp_path / ".cache" / "wandb-build") == []


def test_pulling_twice_is_blocked_unless_forced(tmp_path, capsys):
    root = str(tmp_path)
    rel = wp.pull_run(FakeRun(), root=root)
    with pytest.raises(resolve_mod.DuplicateBlocked) as e:
        wp.pull_run(FakeRun(), root=root)
    assert e.value.matches == [{"raw": rel, "reason": "wandb run id"}]
    assert "pass --force" in capsys.readouterr().err
    (tmp_path / rel / "stale.txt").write_text("x")
    assert wp.pull_run(FakeRun(name="renamed"), force=True, root=root) == rel     # same folder, rebuilt
    assert not (tmp_path / rel / "stale.txt").exists()
    assert json.loads((tmp_path / rel / "run.json").read_text())["name"] == "renamed"


def test_a_cataloged_run_is_never_pulled_again(tmp_path, capsys):
    root = str(tmp_path)
    rel = wp.pull_run(FakeRun(), root=root)
    os.makedirs(tmp_path / "raw" / "experiments")
    os.rename(tmp_path / rel, tmp_path / "raw" / "experiments" / "ratio-sweep-gaussian-ab12cd34")
    with pytest.raises(resolve_mod.DuplicateBlocked):
        wp.pull_run(FakeRun(), force=True, root=root)
    assert "immutable" in capsys.readouterr().err
    assert not (tmp_path / rel).exists()
    other = FakeRun()
    other.project = "other"                                                       # the same id elsewhere is another run
    assert wp.pull_run(other, root=root) == rel


def test_one_run_by_url(tmp_path):
    api = FakeApi([FakeRun()])
    out = wp.scrap_wandb("https://host.example.com/wandb/octocat/demo/runs/ab12cd34", root=str(tmp_path), api=api)
    assert out == ["raw/inbox/run-ratio-sweep-gaussian-ab12cd34"] and api.asked == ["octocat/demo/ab12cd34"]


def test_a_project_pull_takes_tagged_finished_runs_and_skips_known_ones(tmp_path, capsys):
    root = str(tmp_path)
    runs = [FakeRun("aaaa1111", "one"), FakeRun("bbbb2222", "two", state="running"), FakeRun("cccc3333", "three")]
    wp.pull_run(runs[0], root=root)
    api = FakeApi(runs)
    out = wp.scrap_wandb("octocat/demo", root=root, api=api)
    assert out == ["raw/inbox/run-three-cccc3333"]
    assert api.asked == [("octocat/demo", {"tags": {"$in": ["kb"]}})]
    got = capsys.readouterr()
    assert "1 runs pulled, 2 skipped (tag kb)" in got.out and "FOUND" not in got.out and "blocked" not in got.err
    api = FakeApi([])
    wp.scrap_wandb("octocat/demo", tag="", root=root, api=api)
    assert api.asked == [("octocat/demo", None)]


def test_a_project_pull_goes_on_past_a_run_that_fails(tmp_path, capsys):
    bad = FakeRun("bbbb2222", "two", artifacts=[FakeArtifact("grid:v0", "result-grid", {"g.table.json": "{}"}, broken=True)])
    api = FakeApi([FakeRun("aaaa1111", "one"), bad, FakeRun("cccc3333", "three")])
    with pytest.raises(ValueError, match="1 of the project's runs could not be pulled: bbbb2222"):
        wp.scrap_wandb("octocat/demo", root=str(tmp_path), api=api)
    assert sorted(os.listdir(tmp_path / "raw" / "inbox")) == ["run-one-aaaa1111", "run-three-cccc3333"]
    got = capsys.readouterr()
    assert "failed bbbb2222: download failed" in got.err and "2 runs pulled, 0 skipped, 1 failed" in got.out


def test_the_bundle_catalogs_as_a_run(tmp_path, monkeypatch):
    rel = wp.pull_run(FakeRun(), root=str(tmp_path))
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    monkeypatch.setattr(catalog, "_run_lint", lambda: None)
    joined = []
    monkeypatch.setattr(catalog, "_join", lambda *a: joined.append(a))
    assert catalog.detect_format(rel) == "experiments"
    dest, _ = catalog.catalog_run(rel)
    assert dest == "raw/experiments/ratio-sweep-gaussian-ab12cd34"
    assert joined == [(f"{dest}/run.md", "", "Ratio sweep | gaussian")]


def test_cli_and_commit_wrapper_know_the_command(monkeypatch, capsys):
    from kb_distillery.ingest import cli
    from kb_distillery.ops import wrap
    seen = {}
    monkeypatch.setattr(wp, "scrap_wandb", lambda source, **kw: seen.update(source=source, **kw) or [])
    monkeypatch.setattr(cli.net, "install", lambda: None)
    assert cli.main(["scrap-wandb", "octocat/demo", "--tag", "thesis", "--max-mb", "5"]) == 0
    assert seen == {"source": "octocat/demo", "tag": "thesis", "force": False, "max_rows": 100_000, "max_mb": 5}

    def boom(source, **kw):
        raise ValueError("no such run")
    monkeypatch.setattr(wp, "scrap_wandb", boom)
    assert cli.main(["scrap-wandb", "octocat/demo/zzz"]) == 1
    assert "scrap-wandb failed: no such run" in capsys.readouterr().err
    assert wrap.INGEST[("scrap-wandb", None)] == ("import", True)
    assert wrap._target(["raw/inbox/run-three-cccc3333/history.csv", "raw/inbox/run-three-cccc3333/run.md"],
                        ["scrap-wandb"]) == "three-cccc3333"

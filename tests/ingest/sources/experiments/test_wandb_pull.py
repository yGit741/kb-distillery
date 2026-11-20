"""scrap-wandb: a W&B run becomes a run bundle in the inbox (offline: the API is a fake)."""
import csv
import json
import os

import pytest

from kb_distillery.ingest import catalog
from kb_distillery.ingest import resolve as resolve_mod
from kb_distillery.ingest.sources.experiments import wandb_pull as wp


class FakeArtifact:
    def __init__(self, name, type_, files=None, size=1000):
        self.name, self.type, self.size, self.files = name, type_, size, files or {}
        self.downloaded = False

    def download(self, root):
        self.downloaded = True
        os.makedirs(root, exist_ok=True)
        for name, body in self.files.items():
            with open(os.path.join(root, name), "w", encoding="utf-8") as f:
                f.write(body)
        return root


class FakeRun:
    entity, project = "octocat", "demo"
    group, job_type, commit, notes = "ratio-sweep", "ratio-sweep", "a1b2c3d", "E1: sweep gamma"
    created_at = "2026-01-02T03:04:05Z"

    def __init__(self, run_id="ab12cd34", name="Ratio sweep | gaussian", state="finished", artifacts=None, steps=3):
        self.id, self.name, self.state = run_id, name, state
        self.url = f"https://wandb.example.com/octocat/demo/runs/{run_id}"
        self.tags = ["kb", "gaussian"]
        self.config = {"N": 100, "n_grid": [20, 40], "_wandb": {"cli": "x"}}
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
])
def test_parse_ref(source, want):
    assert wp.parse_ref(source) == want


@pytest.mark.parametrize("source", ["", "demo", "octocat/demo/runs", "a/b/c/d"])
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
    assert data["config"] == {"N": 100, "n_grid": [20, 40]}                       # no W&B internals
    assert data["summary"] == {"peak_gamma": 1.0, "windows": "(table-file)"}
    assert data["history"] == {"rows": 3, "columns": ["_step", "gamma", "lambda_min"], "truncated": False}
    assert data["tables"] == [{"file": "grid.csv", "rows": 2, "columns": ["seed", "gamma"], "artifact": "grid:v0"}]
    hist = list(csv.DictReader(open(d / "history.csv", encoding="utf-8")))
    assert [r["gamma"] for r in hist] == ["1.0", "2.0", "3.0"] and "_runtime" not in hist[0]
    assert list(csv.reader(open(d / "grid.csv", encoding="utf-8"))) == [["seed", "gamma"], ["0", "1.5"], ["1", "1.5"]]
    grid, code, weights = run.logged_artifacts()
    assert grid.downloaded and not code.downloaded and not weights.downloaded   # code and big files: listed only
    md = (d / "run.md").read_text()
    assert md.startswith("# Ratio sweep | gaussian\n")
    for line in (f"- Run: {run.url}", "- Project: octocat/demo", "- Code commit: a1b2c3d", "E1: sweep gamma",
                 "| `N` | 100 |", "| `peak_gamma` | 1.0 |", "`history.csv`: 3 rows, 3 columns.",
                 "- `grid.csv`: 2 rows; columns `seed`, `gamma`", "- `grid:v0` (result-grid, 1.0 kB): kept as `grid.csv`",
                 "- `source-demo:v0` (code, 1.0 kB): not copied, see the run",
                 "- `weights:v0` (model, 943.7 MB): not copied, see the run"):
        assert line in md, line
    assert not (tmp_path / ".cache" / "wandb-build").exists() or not os.listdir(tmp_path / ".cache" / "wandb-build")


def test_history_is_capped(tmp_path):
    rel = wp.pull_run(FakeRun(steps=10, artifacts=[]), max_rows=4, root=str(tmp_path))
    data = json.loads((tmp_path / rel / "run.json").read_text())
    assert data["history"]["rows"] == 4 and data["history"]["truncated"]
    assert "4 rows (truncated)" in (tmp_path / rel / "run.md").read_text()


def test_a_run_without_steps_or_artifacts(tmp_path):
    rel = wp.pull_run(FakeRun(steps=0, artifacts=[]), root=str(tmp_path))
    assert sorted(os.listdir(tmp_path / rel)) == ["run.json", "run.md"]
    assert "No logged steps." in (tmp_path / rel / "run.md").read_text()


def test_two_tables_of_one_name_do_not_collide(tmp_path):
    table = json.dumps({"columns": ["a"], "data": [[1]]})
    arts = [FakeArtifact("grid:v0", "result-grid", {"grid.table.json": table}),
            FakeArtifact("run-ab12cd34-grid:v0", "run_table", {"grid.table.json": table, "notes.json": "{}"})]
    rel = wp.pull_run(FakeRun(artifacts=arts), root=str(tmp_path))
    assert {"grid.csv", "grid-run-ab12cd34-grid-v0.csv"} <= set(os.listdir(tmp_path / rel))
    assert "notes.csv" not in os.listdir(tmp_path / rel)                          # only tables are kept


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
    assert "1 runs pulled, 2 skipped (tag kb)" in capsys.readouterr().out
    api = FakeApi([])
    wp.scrap_wandb("octocat/demo", tag="", root=root, api=api)
    assert api.asked == [("octocat/demo", None)]


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

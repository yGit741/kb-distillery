"""`/api/pipeline` is memoised on the vault change signature: one build per vault state, a rebuild after an edit,
and the `server` block fresh on every call."""
import os
import shutil

import pytest

from kb_distillery.graph import cache
from kb_distillery.services import pipeline as dd


@pytest.fixture
def kb(monkeypatch, tmp_path):
    """A private copy of the fixture kb (xdist workers share the original), the cache on and empty."""
    root = os.path.join(str(tmp_path), "kb")
    shutil.copytree(dd.ROOT, root, symlinks=True)
    monkeypatch.setattr(dd, "ROOT", root)
    monkeypatch.delenv(cache.ENV, raising=False)
    cache.clear()
    yield root
    cache.clear()


def test_pipeline_builds_once_per_vault_state_and_again_after_an_edit(kb, monkeypatch):
    builds = []
    monkeypatch.setattr(dd, "_build", lambda: builds.append(1) or {"summary": {"files": len(builds)}, "items": []})
    first = dd.build_digestion_snapshot()
    second = dd.build_digestion_snapshot()
    assert len(builds) == 1 and first["summary"] == second["summary"]
    assert first["server"]["root"] == kb and "started_at" in first["server"]
    page = next(os.path.join(kb, "wiki", f) for f in os.listdir(os.path.join(kb, "wiki")) if f.endswith(".md"))
    with open(page, "a", encoding="utf-8") as fh:
        fh.write("\n\nedited\n")
    third = dd.build_digestion_snapshot()
    assert len(builds) == 2 and third["summary"]["files"] == 2


def test_pipeline_rebuilds_when_hidden_state_under_meta_changes(kb, monkeypatch):
    """`meta/.ingest`, `meta/.catalog` and `meta/.distill` feed the snapshot but are dot folders the vault walk skips."""
    builds = []
    monkeypatch.setattr(dd, "_build", lambda: builds.append(1) or {"summary": {}, "items": []})
    dd.build_digestion_snapshot()
    for rel in (os.path.join("meta", ".ingest", "abc", "session.json"), os.path.join("meta", ".catalog", "failures.jsonl"),
                os.path.join("meta", ".distill", "x", "plan.json")):
        path = os.path.join(kb, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"ts": "2026-01-01T00:00:00Z"}\n')
        dd.build_digestion_snapshot()
    assert len(builds) == 4


def test_pipeline_cache_off_builds_every_call(kb, monkeypatch):
    monkeypatch.setenv(cache.ENV, "0")
    builds = []
    monkeypatch.setattr(dd, "_build", lambda: builds.append(1) or {"summary": {}, "items": []})
    dd.build_digestion_snapshot()
    dd.build_digestion_snapshot()
    assert len(builds) == 2

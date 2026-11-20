"""PUT /api/kb/{id}/star: the starred ids live in <bases dir>/.stars.json (never in a kb) and come back on GET /api/kb/list."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8765"}


def _kb(bases, kb_id):
    root = os.path.join(bases, kb_id)
    os.makedirs(root)
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(f'[kb]\nid = "{kb_id}"\nname = "{kb_id.title()}"\nschema_version = "1.5"\n')
    os.makedirs(os.path.join(root, "wiki"))


@pytest.fixture
def bases(monkeypatch, tmp_path):
    out = tmp_path / "kbs"
    monkeypatch.setenv("KB_BASES_DIR", str(out))
    for k in ("KB", "KB_ROOT"):
        monkeypatch.delenv(k, raising=False)
    _kb(str(out), "alpha")
    _kb(str(out), "beta")
    return out


def _stars(bases):
    with open(bases / ".stars.json", encoding="utf-8") as f:
        return json.load(f)


def test_star_round_trip(bases):
    with TestClient(create_app()) as c:
        assert {r["id"]: r["starred"] for r in c.get("/api/kb/list").json()["kbs"]} == {"alpha": False, "beta": False}
        r = c.put("/api/kb/beta/star", json={"starred": True}, headers=ORIGIN)
        assert r.status_code == 200, r.text
        assert {k["id"]: k["starred"] for k in r.json()["kbs"]} == {"alpha": False, "beta": True}
        assert _stars(bases) == ["beta"]
        assert set(kbconfig.discover()) == {"alpha", "beta"}            # the dotfile is not a knowledge base
        c.put("/api/kb/alpha/star", json={"starred": True}, headers=ORIGIN)
        c.put("/api/kb/beta/star", json={"starred": False}, headers=ORIGIN)
        assert _stars(bases) == ["alpha"]
        assert [k["id"] for k in c.get("/api/kb/list").json()["kbs"] if k["starred"]] == ["alpha"]


def test_unknown_id_is_404_and_writes_nothing(bases):
    with TestClient(create_app()) as c:
        assert c.put("/api/kb/nope/star", json={"starred": True}, headers=ORIGIN).status_code == 404
    assert not (bases / ".stars.json").exists()


def test_a_bad_stars_file_reads_as_none(bases):
    (bases / ".stars.json").write_text("{not json", encoding="utf-8")
    with TestClient(create_app()) as c:
        assert not any(k["starred"] for k in c.get("/api/kb/list").json()["kbs"])
        c.put("/api/kb/alpha/star", json={"starred": True}, headers=ORIGIN)
    assert _stars(bases) == ["alpha"]


def test_stats_answers_at_once_and_counts_the_rest_in_the_background(bases, monkeypatch):
    import time

    from kb_distillery.services import kb as svc
    monkeypatch.setattr(svc, "_SIZES", {})
    monkeypatch.setattr(svc, "_PENDING", {})
    monkeypatch.setattr(svc, "_SIZES_WORKER", None)
    with TestClient(create_app()) as c:
        first = c.get("/api/kb/stats")
        assert first.status_code == 200, first.text
        sizes = first.json()["kbs"]
        for _ in range(100):                         # the background count lands; the menu asks again until then
            if {"alpha", "beta"} <= set(sizes):
                break
            time.sleep(0.05)
            sizes = c.get("/api/kb/stats").json()["kbs"]
    assert {"alpha", "beta"} <= set(sizes), sizes
    if svc._SIZES_WORKER is not None:
        svc._SIZES_WORKER.join(5)
    for size in sizes.values():
        assert set(size) == {"concepts", "sources", "edges"}


def test_a_size_is_reused_until_the_folder_changes(bases, monkeypatch):
    from kb_distillery.services import kb as svc
    monkeypatch.setattr(svc, "_SIZES", {})
    monkeypatch.setattr(svc, "_PENDING", {})
    calls = []
    real = svc._size_of
    monkeypatch.setattr(svc, "_size_of", lambda kb_id, root: (calls.append(kb_id), real(kb_id, root))[1])
    assert {"alpha", "beta"} <= set(svc.graph_sizes(wait=True)["kbs"])
    n = len(calls)
    svc.graph_sizes(wait=True)
    assert len(calls) == n                           # nothing changed: no count again
    (bases / "alpha" / "wiki" / "new.md").write_text("---\ntitle: New\ntype: idea\n---\n# New\n", encoding="utf-8")
    again = svc.graph_sizes()                        # changed: counted in the background, the last size stays
    assert again["pending"] == ["alpha"] and "alpha" in again["kbs"]
    svc.graph_sizes(wait=True)
    assert calls[n:] == ["alpha"]                    # only the changed one is counted again


def test_a_kb_whose_graph_fails_is_left_out_and_not_retried(bases, monkeypatch):
    from kb_distillery.services import kb as svc
    monkeypatch.setattr(svc, "_SIZES", {})
    monkeypatch.setattr(svc, "_PENDING", {})
    from kb_distillery.graph import cache

    def boom(*_a, **_k):
        raise RuntimeError("no graph")

    monkeypatch.setattr(cache, "cached_graph_snapshot", boom)
    out = svc.graph_sizes(wait=True)
    assert out == {"kbs": {}, "pending": []}         # nothing to wait for: the menu stops asking

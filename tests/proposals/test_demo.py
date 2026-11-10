"""`pixi run demo-proposals`: the demo seed writes only `.local/`, covers every producer, and is idempotent."""
import hashlib
import json
import os
import shutil

import pytest

from kb_distillery.proposals import demo, service, store

DEMO = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "demo")


def _tree(root):
    """{relative path: sha256} of every file outside `.local/`."""
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".local"]
        for name in files:
            p = os.path.join(base, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return out


@pytest.fixture
def kb(tmp_path, monkeypatch):
    monkeypatch.setattr("kb_distillery.llm.ask", lambda *a, **k: pytest.fail("the demo seed must not call a model"))
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".local"))
    return str(root)


def _snapshot(root):
    ps = [store.load(root, pid) for pid in store.all_ids(root)]
    return sorted((p["id"], p["title"], p["status"], p["producer"]["kind"]) for p in ps)


def test_writes_only_local_state(kb):
    before = _tree(kb)
    demo.seed(kb)
    assert _tree(kb) == before
    assert os.listdir(os.path.join(kb, ".local", "proposals"))


def test_idempotent(kb):
    first = demo.seed(kb)
    snap = _snapshot(kb)
    flags = sorted(os.listdir(os.path.join(kb, ".local", "flags")))
    second = demo.seed(kb)
    assert first == second
    assert _snapshot(kb) == snap
    assert sorted(os.listdir(os.path.join(kb, ".local", "flags"))) == flags
    rows = json.load(open(os.path.join(kb, ".local", "flags", "skill-clinical-nlp.json")))
    assert len(rows) == 2
    msgs = json.load(open(os.path.join(kb, ".local", "chat", "skill-clinical-nlp.json")))["messages"]
    assert len(msgs) == 2


def test_keeps_the_owners_own_records(kb):
    os.makedirs(os.path.join(kb, ".local", "proposals"))
    mine = {"id": "abcd1234", "title": "mine"}
    store.save(kb, mine)
    demo.seed(kb)
    demo.seed(kb)
    assert store.load(kb, "abcd1234") == mine


def test_every_producer_and_screen_has_something(kb):
    demo.seed(kb)
    kinds = {k for _id, _t, _s, k in _snapshot(kb)}
    assert {"chat", "flags", "ingest", "lint", "restructure", "manual"} <= kinds
    actions = {store.load(kb, pid)["producer"]["context"].get("action") for pid in store.all_ids(kb)}
    assert {"merge", "split", "extract"} <= actions
    assert [i["id"] for i in service.feed(root=kb)] == ["de000008"]
    assert {p["status"] for p in service.list_proposals(root=kb)} >= {"open", "rejected", "undone"}


def test_seed_lifts_read_only_only_while_seeding(kb):
    demo.seed(kb)
    assert service._writable is not service._root

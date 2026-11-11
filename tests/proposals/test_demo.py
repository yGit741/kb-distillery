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
    assert {i["id"] for i in service.feed(root=kb)} == {"de000008", "de00000a"}
    assert {p["status"] for p in service.list_proposals(root=kb)} >= {"open", "rejected", "undone"}


def test_seed_works_on_a_read_only_kb_and_restores_the_guard(kb, monkeypatch):
    from kb_distillery.config.kb import ReadOnlyError

    def refuse(root=None):
        raise ReadOnlyError("read-only")

    monkeypatch.setattr("kb_distillery.proposals.service.require_writable", refuse)
    guard = service._writable
    out = demo.seed(kb)
    assert len(out["proposals"]) == 11
    assert service._writable is guard
    with pytest.raises(Exception, match="read-only"):
        service.create("x", [{"kind": "set_frontmatter", "slug": "skill-pytorch", "key": "maturity", "value": "seed"}], root=kb)


def test_ingest_screen_has_a_row_in_each_group(kb):
    from kb_distillery.services import ingest_ui
    demo.seed(kb)
    demo.seed(kb)
    rows = ingest_ui.listing(kb)
    groups = {}
    for r in rows:
        key = r["status"] if r["status"] != "done" else r["proposal_status"]
        groups.setdefault(key, []).append(r["source"])
    assert {k: len(v) for k, v in groups.items()} == {"running": 1, "open": 1, "applied": 1, "rejected": 1, "failed": 1, "interrupted": 1}
    assert len(rows) == 6 and rows[0]["status"] == "running"

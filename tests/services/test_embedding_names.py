"""Naming the embedding's components and clusters: the requests built, the replies parsed, what is saved, and when
saved names count as current. The LLM is always a fake `llm.run`."""
import json
import sqlite3
import time

import pytest

from kb_distillery import llm
from kb_distillery.services import embedding, embedding_names as svc
from tests.services.test_embedding import _blobs, _store


@pytest.fixture()
def store(tmp_path):
    return _store(tmp_path, _blobs())


def _fake(monkeypatch, reply=None, seen=None):
    def run(requests, backend=None, **kw):
        if seen is not None:
            seen.update(backend=backend, requests=list(requests))
        out = []
        for r in requests:
            text = reply(r) if reply else (json.dumps({"low": "group one", "high": "group two", "why": "they differ"})
                                           if r.id.startswith("component") else json.dumps({"name": "a theme", "why": "shared"}))
            out.append(llm.Result(id=r.id, text=text, usd=0.01, backend=backend))
        return out
    monkeypatch.setattr(svc.llm, "run", run)


def test_one_request_per_component_and_cluster_with_titles_and_summaries(store, monkeypatch):
    db, cards = store
    seen = {}
    _fake(monkeypatch, seen=seen)
    record = svc.name_all("api", db, cards)
    report = embedding.build_embedding_report(db, cards)
    ids = [r.id for r in seen["requests"]]
    assert seen["backend"] == "api"
    assert ids == [f"component-{c['index']}" for c in report["components"]] + [f"cluster-{c['id']}" for c in report["clusters"]]
    first = seen["requests"][0]
    assert "LOW END" in first.prompt and "HIGH END" in first.prompt and "- Title of " in first.prompt and ": summary" in first.prompt
    assert first.model == svc.MODEL
    assert len(record["components"]) == len(report["components"]) and len(record["clusters"]) == len(report["clusters"])
    assert record["usd"] == pytest.approx(0.01 * len(ids)) and record["failed"] == 0 and record["backend"] == "api"


def test_saved_names_show_in_the_report_until_the_vectors_change(store, monkeypatch):
    db, cards = store
    _fake(monkeypatch)
    assert svc.apply(embedding.build_embedding_report(db, cards), db)["names"]["state"] == "none"
    svc.name_all("subscription", db, cards)
    r = svc.apply(embedding.build_embedding_report(db, cards), db)
    assert r["names"]["state"] == "current" and r["names"]["backend"] == "subscription" and r["names"]["model"] == svc.MODEL
    assert (r["components"][0]["low_name"], r["components"][0]["high_name"], r["components"][0]["why"]) == ("group one", "group two", "they differ")
    assert r["clusters"][0]["name"] == "a theme"
    con = sqlite3.connect(db)
    con.execute("DELETE FROM vectors WHERE slug = 'c19'")
    con.commit()
    con.close()
    r = svc.apply(embedding.build_embedding_report(db, cards), db)
    assert r["names"]["state"] == "stale" and r["components"][0]["low_name"] is None and r["clusters"][0]["name"] is None


def test_an_unreadable_reply_leaves_that_item_unnamed(store, monkeypatch):
    db, cards = store
    _fake(monkeypatch, reply=lambda r: "no json here" if r.id == "component-0" else 'Sure: {"low": "a", "high": "b", "why": "c", "name": "n"}')
    record = svc.name_all(None, db, cards)
    assert record["failed"] == 1 and "0" not in record["components"] and record["clusters"]["0"] == {"name": "n", "why": "c"}
    r = svc.apply(embedding.build_embedding_report(db, cards), db)
    assert r["components"][0]["low_name"] is None and r["components"][1]["low_name"] == "a" and r["names"]["failed"] == 1


def test_nothing_back_is_an_error_and_saves_nothing(store, monkeypatch):
    db, cards = store
    monkeypatch.setattr(svc.llm, "run", lambda requests, backend=None, **kw: [llm.Result(id=r.id, error="not logged in") for r in requests])
    with pytest.raises(svc.NamesError, match="not logged in") as e:
        svc.name_all(None, db, cards)
    assert e.value.status == 502 and svc.load(db) is None


def test_unknown_backend_and_missing_store_are_refused(store, tmp_path, monkeypatch):
    db, cards = store
    _fake(monkeypatch)
    with pytest.raises(svc.NamesError) as e:
        svc.name_all("carrier-pigeon", db, cards)
    assert e.value.status == 422
    with pytest.raises(svc.NamesError) as e:
        svc.start(None, str(tmp_path / "nope" / "vectors.sqlite"), cards)
    assert e.value.status == 409


def test_parse_takes_the_first_object_and_needs_the_names():
    assert svc.parse('```json\n{"name": " Deep  learning ", "why": ""}\n```', ("name", "why")) == {"name": "Deep learning", "why": ""}
    assert svc.parse('{"low": "a"}', ("low", "high", "why")) is None and svc.parse("nothing", ("name",)) is None and svc.parse("[1]", ("name",)) is None


def test_start_runs_in_the_background_and_reports_running_then_current(store, monkeypatch):
    db, cards = store
    import threading
    gate = threading.Event()

    def slow(requests, backend=None, **kw):
        gate.wait(5)
        return [llm.Result(id=r.id, text='{"low": "a", "high": "b", "why": "c", "name": "n"}') for r in requests]
    monkeypatch.setattr(svc.llm, "run", slow)
    svc.start("batch", db, cards)
    assert svc.status(db)["state"] == "running" and svc.status(db)["backend"] == "batch"
    with pytest.raises(svc.NamesError) as e:
        svc.start(None, db, cards)
    assert e.value.status == 409
    gate.set()
    for _ in range(200):
        if svc.status(db)["state"] != "running":
            break
        time.sleep(0.02)
    assert svc.status(db)["state"] == "current" and svc.status(db)["error"] is None


def test_a_failed_background_run_keeps_its_reason(store, monkeypatch):
    db, cards = store
    monkeypatch.setattr(svc.llm, "run", lambda requests, backend=None, **kw: [llm.Result(id=r.id, error="rate limited") for r in requests])
    svc.start(None, db, cards)
    for _ in range(200):
        if svc.status(db)["state"] != "running":
            break
        time.sleep(0.02)
    st = svc.status(db)
    assert st["state"] == "none" and "rate limited" in st["error"]

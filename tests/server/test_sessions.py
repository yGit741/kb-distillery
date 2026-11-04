"""Chat sessions over HTTP on a temp kb repo: one JSON file per session under .local/sessions, never staged."""
import json
import os
import subprocess
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.sessions import SessionDeleted, SessionDoc, SessionList
from kb_distillery.services import sessions_store as store

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout


@pytest.fixture
def kb(tmp_path, monkeypatch):
    root = str(tmp_path / "kb")
    os.makedirs(root)
    git(root, "init", "-q")
    monkeypatch.delenv(store.READ_ONLY_ENV, raising=False)
    with mock.patch.object(store, "DEFAULT_ROOT", root):
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


def msgs(question="What is tensor rank?\nPlease be brief.", cost=0.0125):
    return [{"role": "user", "content": question, "sources": ["tensor-rank.md"]},
            {"role": "assistant", "content": "It is ...", "usage": {"cost_usd": cost, "num_turns": 2}, "meta": "m"}]


def put(client, sid, **body):
    body.setdefault("messages", msgs())
    return client.put(f"/api/sessions/{sid}", json=body, headers=LOOPBACK)


def test_empty_list(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200 and SessionList.model_validate(r.json()).sessions == []


def test_put_get_round_trip_keeps_the_messages_as_given(client, kb):
    m = msgs()
    r = put(client, "20261103101500-abc123", messages=m, model="m1", effort="high", backend="agent")
    assert r.status_code == 200, r.text
    doc = SessionDoc.model_validate(r.json())
    assert doc.id == "20261103101500-abc123" and doc.title == "What is tensor rank?" and doc.model == "m1"
    assert doc.usage.turns == 1 and doc.usage.cost_usd == 0.0125 and doc.created and doc.updated
    got = client.get("/api/sessions/20261103101500-abc123")
    assert got.status_code == 200 and got.json()["messages"] == m
    assert got.json()["effort"] == "high" and got.json()["backend"] == "agent"
    on_disk = json.load(open(os.path.join(kb, ".local", "sessions", "20261103101500-abc123.json")))
    assert on_disk["messages"] == m and on_disk["usage"] == {"cost_usd": 0.0125, "turns": 1}


def test_put_again_keeps_created_and_a_rename_survives_the_next_save(client):
    first = put(client, "a1", created="2026-11-03T10:00:00Z").json()
    assert first["created"] == "2026-11-03T10:00:00Z"
    with mock.patch.object(store, "now_iso", return_value="2026-11-03T11:00:00Z"):
        assert client.patch("/api/sessions/a1", json={"title": "  My   chat "}, headers=LOOPBACK).json()["title"] == "My chat"
    again = put(client, "a1", created="1999-01-01T00:00:00Z", messages=msgs() + msgs("second")).json()
    assert again["created"] == "2026-11-03T10:00:00Z" and again["title"] == "My chat" and again["usage"]["turns"] == 2
    assert put(client, "a1", title="Explicit").json()["title"] == "Explicit"


def test_list_is_newest_first_with_preview_turns_and_cost(client):
    for sid, ts, q in (("old", "2026-11-01T09:00:00Z", "first\nmore"), ("new", "2026-11-03T09:00:00Z", "third"),
                       ("mid", "2026-11-02T09:00:00Z", "second")):
        with mock.patch.object(store, "now_iso", return_value=ts):
            put(client, sid, messages=msgs(q))
    listing = SessionList.model_validate(client.get("/api/sessions").json())
    assert [s.id for s in listing.sessions] == ["new", "mid", "old"]
    s = listing.sessions[2]
    assert (s.preview, s.turns, s.cost_usd, s.title) == ("first", 1, 0.0125, "first")
    # touching an old session moves it to the top
    with mock.patch.object(store, "now_iso", return_value="2026-11-04T09:00:00Z"):
        put(client, "old", messages=msgs("first"))
    assert [s["id"] for s in client.get("/api/sessions").json()["sessions"]][0] == "old"


def test_delete_and_error_shapes(client):
    put(client, "a1")
    r = client.delete("/api/sessions/a1", headers=LOOPBACK)
    assert r.status_code == 200 and SessionDeleted.model_validate(r.json()).ok
    assert client.get("/api/sessions/a1").status_code == 404
    assert "error" in client.get("/api/sessions/a1").json()
    assert client.delete("/api/sessions/a1", headers=LOOPBACK).status_code == 404
    assert client.patch("/api/sessions/nope", json={"title": "x"}, headers=LOOPBACK).status_code == 404
    put(client, "a2")
    r = client.patch("/api/sessions/a2", json={"title": "  "}, headers=LOOPBACK)
    assert r.status_code == 400 and "title" in r.json()["error"]
    assert put(client, "bad.id").status_code == 400
    assert put(client, "Upper").status_code == 400
    assert client.put("/api/sessions/abc%0A", json={"messages": []}, headers=LOOPBACK).status_code == 400
    assert put(client, "x" * 65).status_code == 400
    assert client.put("/api/sessions/a3", json={"messages": ["not an object"]}, headers=LOOPBACK).status_code == 422
    assert client.put("/api/sessions/a3", json={"title": "x"}, headers=LOOPBACK).status_code == 422


def test_mutations_need_a_loopback_origin(client):
    assert client.put("/api/sessions/a1", json={"messages": []}).status_code == 403
    assert client.delete("/api/sessions/a1", headers={"Origin": "http://evil.example"}).status_code == 403


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_read_only_refuses_every_write_but_reads_work(client, kb, monkeypatch, value):
    put(client, "a1")
    monkeypatch.setenv(store.READ_ONLY_ENV, value)
    for r in (put(client, "a1"), put(client, "fresh"),
              client.patch("/api/sessions/a1", json={"title": "x"}, headers=LOOPBACK),
              client.delete("/api/sessions/a1", headers=LOOPBACK)):
        assert r.status_code == 405 and "read-only" in r.json()["error"]
    assert not os.path.exists(os.path.join(kb, ".local", "sessions", "fresh.json"))
    assert client.get("/api/sessions/a1").status_code == 200
    assert [s["id"] for s in client.get("/api/sessions").json()["sessions"]] == ["a1"]
    monkeypatch.setenv(store.READ_ONLY_ENV, "0")
    assert put(client, "a1").status_code == 200


def test_local_dir_is_excluded_once_and_never_staged(client, kb):
    exclude = os.path.join(kb, ".git", "info", "exclude")
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    with open(exclude, "w") as f:
        f.write("# local ignores")                       # no trailing newline, no rule yet
    put(client, "a1")
    put(client, "a2")
    put(client, "a1", messages=msgs("again"))
    lines = open(exclude).read().splitlines()
    assert lines == ["# local ignores", ".local/"]
    assert open(os.path.join(kb, ".local", ".gitignore")).read() == "*\n"
    assert git(kb, "status", "--porcelain", "--untracked-files=all") == ""
    git(kb, "add", "-A")
    assert git(kb, "diff", "--cached", "--name-only") == ""


def test_exclude_file_is_created_when_missing_and_a_non_repo_is_fine(client, kb, tmp_path):
    put(client, "a1")
    assert open(os.path.join(kb, ".git", "info", "exclude")).read().count(".local/") == 1
    plain = str(tmp_path / "plain")
    os.makedirs(plain)
    store.put_session("p1", msgs(), root=plain)           # no .git: still written, nothing to exclude
    assert os.path.isfile(os.path.join(plain, ".local", "sessions", "p1.json"))
    assert not os.path.exists(os.path.join(plain, ".git"))


def test_exclude_follows_a_linked_worktree(tmp_path):
    main = str(tmp_path / "main")
    os.makedirs(main)
    git(main, "init", "-q")
    git(main, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "i")
    wt = str(tmp_path / "wt")
    git(main, "worktree", "add", "-q", wt)
    store.put_session("w1", msgs(), root=wt)
    assert ".local/" in open(os.path.join(main, ".git", "info", "exclude")).read().splitlines()
    assert git(wt, "status", "--porcelain") == ""


def test_damaged_files_are_tolerated(client, kb):
    put(client, "good")
    d = os.path.join(kb, ".local", "sessions")
    open(os.path.join(d, "broken.json"), "w").write("{not json")
    open(os.path.join(d, "shape.json"), "w").write(json.dumps({"id": "shape", "messages": "nope"}))
    open(os.path.join(d, "odd name.json"), "w").write("{}")
    open(os.path.join(d, ".tmp-x.part"), "w").write("half")
    assert [s["id"] for s in client.get("/api/sessions").json()["sessions"]] == ["good"]
    r = client.get("/api/sessions/broken")
    assert r.status_code == 409 and "damaged" in r.json()["error"]
    assert client.patch("/api/sessions/broken", json={"title": "x"}, headers=LOOPBACK).status_code == 409
    # saving the chat again replaces the damaged file; deleting it works too
    assert put(client, "broken").status_code == 200 and client.get("/api/sessions/broken").status_code == 200
    assert client.delete("/api/sessions/shape", headers=LOOPBACK).status_code == 200


def test_a_file_from_another_version_is_read_with_defaults(client, kb):
    d = os.path.join(kb, ".local", "sessions")
    os.makedirs(d)
    json.dump({"messages": [{"role": "user", "content": "hello there"}]}, open(os.path.join(d, "legacy.json"), "w"))
    doc = client.get("/api/sessions/legacy").json()
    assert doc["title"] == "hello there" and doc["usage"] == {"cost_usd": 0, "turns": 1} and doc["created"] == ""
    assert client.get("/api/sessions").json()["sessions"][0]["id"] == "legacy"


def test_a_session_over_the_size_cap_is_refused(client, kb):
    big = [{"role": "user", "content": "x" * (store.MAX_BYTES + 10)}]
    r = client.put("/api/sessions/big", json={"messages": big}, headers=LOOPBACK)
    assert r.status_code == 413                           # the app-wide body cap
    with pytest.raises(store.SessionsError) as e:
        store.put_session("big", big)                     # the service holds the same cap for CLI callers
    assert e.value.status == 400
    assert not os.path.exists(os.path.join(kb, ".local", "sessions", "big.json"))


def test_concurrent_puts_leave_one_valid_file(client, kb):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda i: put(client, "race", messages=msgs(f"q{i}")).status_code, range(24)))
    assert set(codes) == {200}
    doc = client.get("/api/sessions/race").json()
    assert doc["usage"]["turns"] == 1 and doc["title"].startswith("q")
    assert [n for n in os.listdir(os.path.join(kb, ".local", "sessions"))] == ["race.json"]


def test_a_folder_that_is_not_a_repo_still_ignores_its_local_dir(tmp_path):
    outer = str(tmp_path / "outer")
    os.makedirs(os.path.join(outer, "inner"))
    git(outer, "init", "-q")
    store.put_session("p1", msgs(), root=os.path.join(outer, "inner"))
    assert git(outer, "status", "--porcelain", "--untracked-files=all") == ""


def test_an_unwritable_local_dir_is_a_500_with_a_message(client, kb):
    open(os.path.join(kb, ".local"), "w").write("a file where the directory should be")
    r = put(client, "a1")
    assert r.status_code == 500 and "error" in r.json()

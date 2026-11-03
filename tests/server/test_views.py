"""Pinned views (meta/views.json, one kb(refine) step each) and recent steps (.local/, never committed) over HTTP, on a
temp kb repo; the real kb is never written."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.app import create_app
from kb_distillery.server.models.views import RecentList, ViewList, ViewStep
from kb_distillery.services import kbview
from kb_distillery.services import views as views_svc
from kb_distillery.vault import views as vv
from tests.ops.test_view import ENV, SUBJECT, commits, git, head_files, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path))
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(views_svc, "DEFAULT_ROOT", root), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None):
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


def test_list_pin_rename_unpin_round_trip(client, kb):
    assert ViewList.model_validate(client.get("/api/views").json()).views == []
    n = commits(kb)

    spec = {"cypher": "MATCH (n:concept) RETURN n", "style": {"size": "degree"}, "layout": "force", "camera": [0, 0, 1]}
    r = client.post("/api/views", json={"name": "Concepts by degree", "spec": spec}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    step = ViewStep.model_validate(r.json())
    assert step.ok and step.view.id == "concepts-by-degree" and step.view.spec == spec and step.version.startswith("kb-")
    assert commits(kb) == n + 1
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "pin view Concepts by degree"
    assert head_files(kb) == {"meta/views.json", "wiki/log.md"}

    listing = client.get("/api/views").json()
    assert [(v["id"], v["name"], v["spec"]) for v in listing["views"]] == [("concepts-by-degree", "Concepts by degree", spec)]

    r = client.patch("/api/views/concepts-by-degree", json={"name": "By degree"}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["view"]["name"] == "By degree"
    assert commits(kb) == n + 2
    assert client.get("/api/views").json()["views"][0]["spec"] == spec

    r = client.delete("/api/views/concepts-by-degree", headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["view"]["id"] == "concepts-by-degree"
    assert commits(kb) == n + 3 and client.get("/api/views").json() == {"views": []}
    assert git(kb, "status", "--porcelain") == ""


def test_error_shapes(client, kb):
    n = commits(kb)
    r = client.post("/api/views", json={"name": "   ", "spec": {}}, headers=LOOPBACK)
    assert r.status_code == 400 and "name" in r.json()["error"]
    assert client.post("/api/views", json={"name": "x", "spec": [1]}, headers=LOOPBACK).status_code == 422
    assert client.delete("/api/views/nope", headers=LOOPBACK).status_code == 404
    assert client.patch("/api/views/nope", json={"name": "y"}, headers=LOOPBACK).status_code == 404
    assert client.post("/api/views", json={"name": "a", "id": "A b"}, headers=LOOPBACK).status_code == 400
    client.post("/api/views", json={"name": "a", "id": "a"}, headers=LOOPBACK)
    assert client.post("/api/views", json={"name": "b", "id": "a"}, headers=LOOPBACK).status_code == 409
    assert commits(kb) == n + 1


def test_mutations_need_a_loopback_origin(client):
    assert client.post("/api/views", json={"name": "x"}).status_code == 403
    assert client.post("/api/recent", json={"text": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403


# ---------- read-only ----------

def test_a_read_only_server_refuses_every_write_with_405(client, kb):
    n = commits(kb)
    with mock.patch.dict(os.environ, {views_svc.READ_ONLY_ENV: "1"}):
        for call in (lambda: client.post("/api/views", json={"name": "x"}, headers=LOOPBACK),
                     lambda: client.patch("/api/views/x", json={"name": "y"}, headers=LOOPBACK),
                     lambda: client.delete("/api/views/x", headers=LOOPBACK),
                     lambda: client.post("/api/recent", json={"text": "x"}, headers=LOOPBACK),
                     lambda: client.delete("/api/recent", headers=LOOPBACK)):
            r = call()
            assert r.status_code == 405 and "read-only" in r.json()["error"]
        assert client.get("/api/views").status_code == 200 and client.get("/api/recent").status_code == 200
    assert commits(kb) == n and not os.path.exists(os.path.join(kb, ".local"))


@pytest.fixture
def two_kbs(kb, tmp_path_factory):
    other = str(tmp_path_factory.mktemp("other-kb"))
    os.makedirs(os.path.join(other, "wiki"))
    with open(os.path.join(other, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nid = "beta"\nname = "Beta"\nschema_version = "1.5"\n')
    os.makedirs(os.path.join(other, "meta"))
    with open(os.path.join(other, "meta", "views.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "theirs", "name": "Theirs", "created": "2026-01-01T00:00:00Z", "spec": {"a": 1}}], f)
    with mock.patch.object(kbconfig, "discover", lambda: {"beta": other}):
        kbview._views.clear()
        with TestClient(create_app()) as c:
            yield c, other
        kbview._views.clear()


@pytest.mark.flag("kb-view", True)
def test_another_kb_in_multi_kb_mode_is_read_only(two_kbs, kb):
    c, other = two_kbs
    assert [v["id"] for v in c.get("/api/views?kb=beta").json()["views"]] == ["theirs"]
    assert c.get("/api/views").json() == {"views": []}                  # the served kb has none
    n = commits(kb)
    for r in (c.post("/api/views?kb=beta", json={"name": "x"}, headers=LOOPBACK),
              c.patch("/api/views/theirs?kb=beta", json={"name": "y"}, headers=LOOPBACK),
              c.delete("/api/views/theirs?kb=beta", headers=LOOPBACK)):
        assert r.status_code == 405 and "read-only" in r.json()["error"]
    assert commits(kb) == n and len(json.load(open(os.path.join(other, "meta", "views.json")))) == 1


@pytest.mark.flag("kb-view", False)
def test_flag_off_serves_no_other_kb_views(two_kbs):
    c, _ = two_kbs
    assert c.get("/api/views?kb=beta").status_code == 404
    assert c.get("/api/views?kb=nope").status_code == 404


# ---------- recent steps ----------

def test_recent_append_trims_to_twenty_and_clears(client, kb):
    assert RecentList.model_validate(client.get("/api/recent").json()).recent == []
    for i in range(25):
        r = client.post("/api/recent", json={"text": f"step {i}", "spec": {"i": i}}, headers=LOOPBACK)
        assert r.status_code == 200
    recent = RecentList.model_validate(client.get("/api/recent").json()).recent
    assert [e.text for e in recent] == [f"step {i}" for i in range(5, 25)]       # the last 20, oldest first
    assert recent[-1].spec == {"i": 24} and recent[0].at
    with open(os.path.join(kb, ".local", "recent.json")) as f:
        assert len(json.load(f)) == 20
    assert client.post("/api/recent", json={"text": " "}, headers=LOOPBACK).status_code == 400

    assert client.delete("/api/recent", headers=LOOPBACK).json() == {"recent": []}
    assert client.get("/api/recent").json() == {"recent": []}
    assert not os.path.exists(os.path.join(kb, ".local", "recent.json"))


def test_recent_is_never_staged_by_ops_even_without_the_gitignore_rule(client, kb):
    assert ".local" not in open(os.path.join(kb, ".gitignore")).read()          # a kb that predates the rule
    client.post("/api/recent", json={"text": "filter by type", "spec": {}}, headers=LOOPBACK)
    assert os.path.isfile(os.path.join(kb, ".local", "recent.json"))
    assert git(kb, "status", "--porcelain") == ""                               # ignored locally, not even untracked

    client.post("/api/views", json={"name": "Pinned"}, headers=LOOPBACK)
    assert head_files(kb) == {"meta/views.json", "wiki/log.md"}
    assert git(kb, "ls-files", ".local") == ""
    assert git(kb, "log", "--format=", "--name-only", "--all", "--", ".local") == ""


def test_recent_survives_a_damaged_file(client, kb):
    os.makedirs(os.path.join(kb, ".local"))
    with open(os.path.join(kb, ".local", "recent.json"), "w") as f:
        f.write("{broken")
    assert client.get("/api/recent").json() == {"recent": []}
    assert client.post("/api/recent", json={"text": "fresh"}, headers=LOOPBACK).json()["recent"][0]["text"] == "fresh"


def test_exclude_rule_is_added_once_and_only_for_a_repo(tmp_path):
    repo = make_repo(str(tmp_path / "repo"))
    vv.ensure_local_ignored(repo)
    vv.ensure_local_ignored(repo)
    text = open(os.path.join(repo, ".git", "info", "exclude")).read()
    assert text.splitlines().count(".local/") == 1
    plain = tmp_path / "plain"
    plain.mkdir()
    vv.ensure_local_ignored(str(plain))                  # no repo: nothing created, nothing raised
    assert not (plain / ".git").exists()

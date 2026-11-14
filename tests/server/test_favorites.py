"""Favorite pages (meta/favorites.json, one kb(refine) step each) over HTTP, on a temp kb repo; the real kb is never written."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.app import create_app
from kb_distillery.server.models.favorites import FavoriteList, FavoriteStep
from kb_distillery.services import favorites as fav_svc
from kb_distillery.services import kbview
from tests.ops.test_favorite import SUBJECT, write_page
from tests.ops.test_view import ENV, commits, git, head_files, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path))
    for slug in ("alpha", "beta"):
        write_page(root, slug)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: pages (retro)")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(fav_svc, "DEFAULT_ROOT", root), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


def test_get_post_delete_round_trip(client, kb):
    assert FavoriteList.model_validate(client.get("/api/favorites").json()).slugs == []
    n = commits(kb)

    r = client.post("/api/favorites", json={"slug": "beta"}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    step = FavoriteStep.model_validate(r.json())
    assert step.ok and step.slugs == ["beta"] and step.version.startswith("kb-")
    assert commits(kb) == n + 1
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "favorite add beta"
    assert head_files(kb) == {"meta/favorites.json", "wiki/log.md"}

    client.post("/api/favorites", json={"slug": "alpha"}, headers=LOOPBACK)
    assert client.get("/api/favorites").json() == {"slugs": ["alpha", "beta"]}

    again = client.post("/api/favorites", json={"slug": "alpha"}, headers=LOOPBACK)
    assert again.status_code == 200 and again.json()["ok"] is False and again.json()["reason"] == "already"
    assert commits(kb) == n + 2

    r = client.delete("/api/favorites/beta", headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["slugs"] == ["alpha"]
    assert client.delete("/api/favorites/beta", headers=LOOPBACK).json()["reason"] == "absent"
    assert commits(kb) == n + 3 and git(kb, "status", "--porcelain") == ""


def test_error_shapes(client, kb):
    n = commits(kb)
    assert client.post("/api/favorites", json={"slug": "not-a-page"}, headers=LOOPBACK).status_code == 404
    assert client.post("/api/favorites", json={"slug": "a/b"}, headers=LOOPBACK).status_code == 400
    assert client.post("/api/favorites", json={}, headers=LOOPBACK).status_code == 422
    assert commits(kb) == n


def test_mutations_need_a_loopback_origin(client):
    assert client.post("/api/favorites", json={"slug": "alpha"}).status_code == 403
    assert client.delete("/api/favorites/alpha").status_code == 403


def test_a_read_only_server_refuses_every_write_with_405(client, kb):
    n = commits(kb)
    with mock.patch.dict(os.environ, {fav_svc.READ_ONLY_ENV: "1"}):
        for r in (client.post("/api/favorites", json={"slug": "alpha"}, headers=LOOPBACK),
                  client.delete("/api/favorites/alpha", headers=LOOPBACK)):
            assert r.status_code == 405 and "read-only" in r.json()["error"]
        assert client.get("/api/favorites").status_code == 200
    assert commits(kb) == n


@pytest.fixture
def two_kbs(kb, tmp_path_factory):
    other = str(tmp_path_factory.mktemp("other-kb"))
    os.makedirs(os.path.join(other, "wiki"))
    os.makedirs(os.path.join(other, "meta"))
    with open(os.path.join(other, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nid = "beta"\nname = "Beta"\nschema_version = "1.6"\n')
    with open(os.path.join(other, "meta", "favorites.json"), "w", encoding="utf-8") as f:
        json.dump({"v": 1, "slugs": ["theirs"]}, f)
    with mock.patch.object(kbconfig, "discover", lambda: {"beta": other}):
        kbview._views.clear()
        with TestClient(create_app()) as c:
            yield c, other
        kbview._views.clear()


@pytest.mark.flag("kb-view", True)
def test_another_kb_in_multi_kb_mode_is_read_only(two_kbs, kb):
    c, other = two_kbs
    assert c.get("/api/favorites?kb=beta").json() == {"slugs": ["theirs"]}
    assert c.get("/api/favorites").json() == {"slugs": []}
    n = commits(kb)
    for r in (c.post("/api/favorites?kb=beta", json={"slug": "alpha"}, headers=LOOPBACK),
              c.delete("/api/favorites/theirs?kb=beta", headers=LOOPBACK)):
        assert r.status_code == 405 and "read-only" in r.json()["error"]
    assert commits(kb) == n and json.load(open(os.path.join(other, "meta", "favorites.json")))["slugs"] == ["theirs"]

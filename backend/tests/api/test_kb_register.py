"""POST /api/kb/register: save a knowledge base folder from anywhere on disk in the machine-local registry."""
import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from kb import kbconfig
from kb.api.app import create_app


def _folder(root, kb_id="far", version="1.3", repo=True):
    os.makedirs(os.path.join(root, "wiki"))
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(f'[kb]\nid = "{kb_id}"\nname = "Far Away"\nschema_version = "{version}"\n')
    if repo:
        subprocess.run(["git", "init", "-q", root], check=True)
    return root


@pytest.fixture
def client(tmp_path, monkeypatch):
    reg = str(tmp_path / "knowledge-bases.toml")
    monkeypatch.setattr(kbconfig, "registry_path", lambda: reg)
    monkeypatch.setattr(kbconfig, "bases_dir", lambda: str(tmp_path / "bases"))
    with TestClient(create_app(legacy=False), headers={"Origin": "http://127.0.0.1:8765"}) as c:
        yield c, reg


def test_register_saves_and_lists(client, tmp_path):
    c, reg = client
    root = _folder(str(tmp_path / "somewhere" / "far"))
    r = c.post("/api/kb/register", json={"path": root})
    assert r.status_code == 200, r.text
    assert "far" in [k["id"] for k in r.json()["kbs"]]
    assert kbconfig.discover()["far"] == os.path.realpath(root)
    # idempotent: the same folder again changes nothing
    before = open(reg, encoding="utf-8").read()
    assert c.post("/api/kb/register", json={"path": root}).status_code == 200
    assert open(reg, encoding="utf-8").read() == before


@pytest.mark.parametrize("kw, msg", [({"repo": False}, "not a git repository"), ({"version": "0.9"}, "schema_version")])
def test_register_refuses_what_it_cannot_open(client, tmp_path, kw, msg):
    c, reg = client
    root = _folder(str(tmp_path / "bad"), **kw)
    r = c.post("/api/kb/register", json={"path": root})
    assert r.status_code == 400 and msg in r.json()["error"]
    assert not os.path.exists(reg)


def test_register_refuses_a_foreign_origin(client, tmp_path):
    c, reg = client
    r = c.post("/api/kb/register", json={"path": _folder(str(tmp_path / "x"))}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not os.path.exists(reg)


def test_register_refuses_a_missing_folder_and_a_taken_id(client, tmp_path):
    c, _reg = client
    assert c.post("/api/kb/register", json={"path": str(tmp_path / "nope")}).status_code == 400
    assert c.post("/api/kb/register", json={"path": _folder(str(tmp_path / "a"))}).status_code == 200
    r = c.post("/api/kb/register", json={"path": _folder(str(tmp_path / "b"))})   # same id "far", other folder
    assert r.status_code == 400 and "already known" in r.json()["error"]

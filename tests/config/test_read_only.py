"""Read-only knowledge bases: `is_read_only`, the ops refusal, the 403 on mutating routes, `open-example` names."""
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import kb as kbconfig
from kb_distillery.ops import core
from kb_distillery.server.app import create_app
from tests.ops.test_view import ENV, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
MESSAGE = "this knowledge base is read-only (example kb)"


def _kb(path, extra=""):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(f'[kb]\nid = "x"\nname = "X"\nschema_version = "1.5"\n{extra}')
    return str(path)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("KB_READ_ONLY", raising=False)


def test_plain_kb_is_writable(tmp_path):
    assert not kbconfig.is_read_only(_kb(tmp_path / "kb"), examples=[str(tmp_path / "examples")])


def test_kb_under_examples_dir_is_read_only(tmp_path):
    ex = tmp_path / "engine" / "examples"
    inside = _kb(ex / "demo")
    sibling = _kb(tmp_path / "engine" / "examples-other" / "demo")
    assert kbconfig.is_read_only(inside, examples=[str(ex)])
    assert not kbconfig.is_read_only(sibling, examples=[str(ex)])


def test_kb_toml_flag_and_env(tmp_path, monkeypatch):
    flagged = _kb(tmp_path / "a", "read_only = true\n")
    assert kbconfig.is_read_only(flagged, examples=[])
    off = _kb(tmp_path / "b", "read_only = false\n")
    assert not kbconfig.is_read_only(off, examples=[])
    monkeypatch.setenv("KB_READ_ONLY", "1")
    assert kbconfig.is_read_only(off, examples=[])


def test_require_writable_message(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    with pytest.raises(kbconfig.ReadOnlyError, match="read-only"):
        kbconfig.require_writable(str(tmp_path))
    assert str(kbconfig.ReadOnlyError(kbconfig.READ_ONLY_MESSAGE)) == MESSAGE


def test_list_examples_finds_kb_folders(tmp_path):
    ex = tmp_path / "examples"
    _kb(ex / "demo")
    os.makedirs(ex / "not-a-kb")
    with mock.patch.object(kbconfig, "examples_dirs", return_value=[str(ex)]):
        assert list(kbconfig.list_examples()) == ["demo"]


def test_ops_entry_points_refuse(tmp_path, monkeypatch):
    root = make_repo(str(tmp_path))
    monkeypatch.setenv("KB_READ_ONLY", "1")
    for call in (lambda: core.begin("refine", "x", root=root), lambda: core.commit_op("refine", "x", root=root),
                 lambda: core.undo("HEAD", root=root), lambda: core.restore("kb-1.0.0", root=root),
                 lambda: core.snapshot(root=root)):
        with pytest.raises(core.OpsError, match="read-only"):
            call()


def test_server_refuses_kb_writes_but_not_app_state(tmp_path, monkeypatch):
    """KB_READ_ONLY=1 is the server-wide switch: its documented answer is 405 (see tests/server/test_read_only.py)."""
    root = make_repo(str(tmp_path))
    monkeypatch.setenv("KB_READ_ONLY", "1")
    with mock.patch.dict(os.environ, ENV), TestClient(create_app()) as c:
        r = c.post("/api/think/capture", json={"text": "hi"}, headers=LOOPBACK)
        assert r.status_code == 405 and MESSAGE in r.text
        assert c.post("/api/favorites", json={"slug": "alpha"}, headers=LOOPBACK).status_code == 405
        assert c.post("/api/think/capture", json={"text": "hi"}, headers=LOOPBACK).status_code == 405
        assert c.delete("/api/views/v1", headers=LOOPBACK).status_code == 405
        assert c.delete("/api/sessions/s1", headers=LOOPBACK).status_code == 405
        assert c.post("/api/recent", json={"text": "x"}, headers=LOOPBACK).status_code == 405
        assert c.delete("/api/chat/attachments/s1/a1", headers=LOOPBACK).status_code == 405
        assert c.put("/api/flags/nope", json={}, headers=LOOPBACK).status_code != 405
        assert c.get("/api/kb").json()["read_only"] is True
    assert os.path.isdir(root)


def test_server_writable_by_default(tmp_path):
    make_repo(str(tmp_path))
    with mock.patch.dict(os.environ, ENV), TestClient(create_app()) as c:
        r = c.post("/api/favorites", json={"slug": "nope"}, headers=LOOPBACK)
        assert r.json().get("detail") != MESSAGE


def test_open_example_refuses_unknown_name(tmp_path, capsys):
    ex = tmp_path / "examples"
    _kb(ex / "demo")
    with mock.patch.object(kbconfig, "examples_dirs", return_value=[str(ex)]):
        assert kbconfig.main(["open-example", "nope"]) == 2
    assert "available: demo" in capsys.readouterr().err


def test_server_refuses_on_examples_path_without_env(tmp_path):
    root = make_repo(str(tmp_path))
    with mock.patch.dict(os.environ, ENV), mock.patch.object(kbconfig, "examples_dirs", return_value=[str(tmp_path)]), \
            mock.patch.object(kbconfig, "vault_root", return_value=root), TestClient(create_app()) as c:
        r = c.post("/api/recent", json={"text": "x"}, headers=LOOPBACK)
        assert r.status_code == 403 and r.json() == {"detail": MESSAGE}
        assert c.delete("/api/sessions/s1", headers=LOOPBACK).status_code == 403
        assert c.post("/api/think/capture", json={"text": "hi"}, headers=LOOPBACK).status_code == 403
    assert not os.path.exists(os.path.join(root, ".local"))

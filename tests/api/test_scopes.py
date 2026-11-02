"""Scopes API against a temp git vault (the real vault is never written): reads, the four writes as one
kb(refine) step each, legacy error shapes and the Origin rule."""
import pytest

from kb_distillery.core import schema as _schema

if "paper" not in _schema.SOURCE_TYPES:   # this module builds `paper` pages: it needs the explorer's default types
    pytest.skip("needs the default source types (run with KB=yonatan-thesis or a kb that defines `paper`)", allow_module_level=True)

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.scopes import ScopeDetail, ScopeList, ScopeResolved, ScopeStep
from kb_distillery.paths import meta_file, vault_root
from kb_distillery.services import scopes as scopes_data
from tests.core.test_scopes import A, B, C, IMG, TEXTS

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB_NO_PUSH": "1"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


@pytest.fixture
def vault(tmp_path):
    from tests.core.test_scopes import manifest
    root = str(tmp_path)
    files = {"meta/stub.py": "x = 1\n", "wiki/log.md": "# Log\n", ".gitignore": "meta/.ops/\n", "wiki/index.md": "v1\n",
             "meta/templates/scope.md": Path(meta_file("templates", "scope.md")).read_text()}
    for slug, text in TEXTS.items():
        files[f"wiki/{slug}.md"] = text
    lines = ["path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes"]
    for p, r in sorted(manifest().items()):
        lines.append("\t".join([p, r["sha1"], r["kind"], r["disposition"], r["slug"], r["collection"], ""]))
    files["meta/corpus.tsv"] = "\n".join(lines) + "\n"
    for rel, text in files.items():
        Path(root, rel).parent.mkdir(parents=True, exist_ok=True)
        Path(root, rel).write_text(text)
    with mock.patch.dict(os.environ, ENV):
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "t")
        git(root, "config", "user.email", "t@t")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "chore: init (retro)")
        with mock.patch.object(scopes_data, "DEFAULT_ROOT", root), \
             mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
             mock.patch("kb_distillery.ops.core.run_lint", return_value=None):      # lint of a bare temp repo is not under test
            yield root


@pytest.fixture
def client(vault):
    with TestClient(create_app()) as c:
        yield c


def commits(root):
    return int(git(root, "rev-list", "--count", "HEAD"))


def save(client, **kw):
    body = {"slug": "alpha", "title": "Alpha set", "why": "Because [[q-y]] needs it.", "paths": [A, C], "create": True}
    return client.post("/api/scopes", json=body | kw, headers=LOOPBACK)


def test_empty_list_then_full_lifecycle_one_step_each(client, vault):
    body = client.get("/api/scopes").json()
    assert ScopeList.model_validate(body).scopes == [] and set(body) >= set(scopes_data.list_scopes())
    n = commits(vault)

    r = save(client)
    assert r.status_code == 200, r.text
    step = ScopeStep.model_validate(r.json())
    assert step.ok and step.slug == "scope-alpha" and step.version.startswith("kb-")
    assert commits(vault) == n + 1
    assert git(vault, "log", "-1", "--format=%s").startswith("kb(refine): ")

    listing = client.get("/api/scopes").json()
    assert [(s["slug"], s["files"], s["digested"], s["uncovered"]) for s in listing["scopes"]] == [("scope-alpha", 2, 1, 1)]
    detail = client.get("/api/scopes/scope-alpha").json()
    ScopeDetail.model_validate(detail)
    assert set(detail) >= set(scopes_data.get_scope("scope-alpha"))
    assert [row["path"] for row in detail["rows"]] == [A, C] and detail["projection"]["uncovered"] == [C]

    r = save(client, paths=[B], create=False, title="")
    assert r.status_code == 200 and commits(vault) == n + 2

    r = client.post("/api/scopes/scope-alpha/duplicate", json={"new_slug": "beta"}, headers=LOOPBACK)
    assert r.status_code == 200 and ScopeStep.model_validate(r.json()).slug == "scope-beta"
    assert [s["slug"] for s in client.get("/api/scopes").json()["scopes"]] == ["scope-alpha", "scope-beta"]

    r = client.delete("/api/scopes/scope-alpha", headers=LOOPBACK)
    assert r.status_code == 200 and not Path(vault, "wiki", "scope-alpha.md").exists()
    assert commits(vault) == n + 4
    assert [s["slug"] for s in client.get("/api/scopes").json()["scopes"]] == ["scope-beta"]
    assert git(vault, "status", "--porcelain") == ""


def test_resolve(client):
    r = client.post("/api/scopes/resolve", json={"nodes": ["course-c", "raw:" + A]}, headers=LOOPBACK)
    assert r.status_code == 200
    body = ScopeResolved.model_validate(r.json())
    assert body.paths == scopes_data.resolve_nodes(["course-c", "raw:" + A])["paths"] and A in body.paths
    assert client.post("/api/scopes/resolve", json={"nodes": "course-c"}, headers=LOOPBACK).status_code == 422


def test_legacy_error_shapes(client, vault):
    r = client.get("/api/scopes/scope-nope")
    assert r.status_code == 404 and r.json() == {"error": "unknown scope"}
    assert save(client, why="  ").status_code == 400
    assert save(client, slug="Bad Slug!").status_code == 400
    assert save(client, paths=["raw/inbox/x.pdf"]).status_code == 400
    assert save(client, paths=[IMG]).status_code == 400
    assert save(client, create=False).status_code == 404
    n = commits(vault)
    assert save(client).status_code == 200
    r = save(client)
    assert r.status_code == 409 and "already exists" in r.json()["error"]
    assert client.delete("/api/scopes/scope-nope", headers=LOOPBACK).status_code == 404
    assert client.post("/api/scopes/scope-nope/duplicate", json={"new_slug": "z"}, headers=LOOPBACK).status_code == 404
    assert client.post("/api/scopes/scope-alpha/duplicate", json={"new_slug": "alpha"}, headers=LOOPBACK).status_code == 409
    assert commits(vault) == n + 1


def test_mutations_are_refused_without_a_loopback_origin(client, vault):
    n = commits(vault)
    body = {"slug": "alpha", "why": "w", "paths": [A], "create": True}
    for headers in ({}, {"Origin": "https://evil.example"}):
        assert client.post("/api/scopes", json=body, headers=headers).status_code == 403
        assert client.post("/api/scopes/resolve", json={"nodes": []}, headers=headers).status_code == 403
        assert client.post("/api/scopes/scope-x/duplicate", json={"new_slug": "y"}, headers=headers).status_code == 403
        assert client.delete("/api/scopes/scope-x", headers=headers).status_code == 403
    assert commits(vault) == n and not Path(vault, "wiki", "scope-alpha.md").exists()


def test_reads_on_the_real_vault_are_valid_models():
    with TestClient(create_app()) as c:                     # read-only: nothing here writes
        body = c.get("/api/scopes").json()
        ScopeList.model_validate(body)
        assert set(body) >= set(scopes_data.list_scopes())
        for s in body["scopes"][:3]:
            ScopeDetail.model_validate(c.get(f"/api/scopes/{s['slug']}").json())

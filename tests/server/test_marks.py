"""GET/POST /api/marks/… on a temp kb repo: fake model, no network, the real kb is never written."""
import json
import os
import re
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.parse import store
from kb_distillery.server.app import create_app
from kb_distillery.server.models.marks import MarkDetail, MarkFixReply, MarkStepResult
from kb_distillery.services import marks as svc
from tests.ops.test_view import ENV, commits, git, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
SHA = "ab12cd34ef" + "0" * 30
S12 = SHA[:12]
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PAGE = f"# Rank\n\nThe rank is $r = n - 1$ [!!](mark:{S12}/p0188/3) here.\n\n$$\nx = 1\n$$\n[!](mark:{S12}/p0188/4)\n"
BASE = f"/api/marks/{S12}/p0188"


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path / "kb"), gitignore="meta/.ops/\nmeta/parsed/\n")
    with open(os.path.join(root, "wiki", "rank.md"), "w", encoding="utf-8") as f:
        f.write(PAGE)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: page (retro)")
    proot = store.parsed_root(root)
    store.write_transcript_page(proot, SHA, 188, "x", [
        {"id": 3, "level": "!!", "reason": "readers disagree", "text": "$r = n - 1$", "was": "", "other": "$r = n + 1$",
         "box": [0, 0, 1, 1], "crop": "p0188-3.png"},
        {"id": 4, "level": "!", "reason": "judge fixed it", "text": "$$\nx = 1\n$$", "was": "$$x=l$$", "other": "",
         "box": [0, 0, 1, 1]},
        {"id": 5, "level": "!", "reason": "escape", "text": "", "box": [0, 0, 1, 1], "crop": "../../../wiki/rank.md"},
    ])
    os.makedirs(os.path.join(proot, SHA, "crops"))
    with open(os.path.join(proot, SHA, "crops", "p0188-3.png"), "wb") as f:
        f.write(PNG)
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(svc, "DEFAULT_ROOT", root), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        os.environ.pop("KB_READ_ONLY", None)
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


def page(kb):
    with open(os.path.join(kb, "wiki", "rank.md"), encoding="utf-8") as f:
        return f.read()


def test_lookup_and_crop(client, kb):
    d = MarkDetail.model_validate(client.get(f"{BASE}/3").json())
    assert d.level == "!!" and d.reason == "readers disagree" and d.crop_url == f"{BASE}/3/crop" and d.resolution is None
    r = client.get(f"{BASE}/3/crop")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG
    assert MarkDetail.model_validate(client.get(f"{BASE}/4").json()).crop_url is None
    assert client.get(f"{BASE}/4/crop").status_code == 404
    assert client.get(f"{BASE}/9").status_code == 404
    assert client.get(f"/api/marks/{'f' * 12}/p0188/3").status_code == 404
    assert client.get(f"/api/marks/{S12}/188/3").status_code == 404


def test_short_id_matching_several_documents_is_404(client, kb):
    os.makedirs(os.path.join(store.parsed_root(kb), S12 + "f" * 28))
    assert client.get(f"{BASE}/3").status_code == 404


def test_crop_never_leaves_the_crops_folder(client, kb):
    assert MarkDetail.model_validate(client.get(f"{BASE}/5").json()).crop_url is None
    assert client.get(f"{BASE}/5/crop").status_code == 404


def test_resolve_keeps_the_formula_and_commits(client, kb):
    n = commits(kb)
    r = client.post(f"{BASE}/3/resolve", json={"slug": "rank"}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = MarkStepResult.model_validate(r.json())
    assert out.commit == git(kb, "rev-parse", "HEAD") and commits(kb) == n + 1
    assert re.match(r"^kb\(refine\): .+ \(kb-\d+\.\d+\.\d+\)$", git(kb, "log", "-1", "--format=%s"))
    assert "The rank is $r = n - 1$ here." in page(kb) and "/p0188/3)" not in page(kb)
    res = store.resolutions(store.parsed_root(kb), SHA)["p0188/3"]
    assert res["action"] == "correct" and res["slug"] == "rank"
    assert MarkDetail.model_validate(client.get(f"{BASE}/3").json()).resolution.action == "correct"
    assert client.post(f"{BASE}/3/resolve", json={"slug": "rank"}, headers=LOOPBACK).status_code == 409


def test_fix_asks_the_model_with_the_crop_and_writes_nothing(client, kb):
    seen = {}

    def fake_ask(prompt, backend=None, run_kw=None, **kw):
        seen.update(prompt=prompt, backend=backend, **kw)
        return SimpleNamespace(error="", text="```latex\n$r = n + 1$\n```", backend="api", backend_used="api")

    before = page(kb)
    with mock.patch.object(svc.llm, "ask", side_effect=fake_ask):
        r = client.post(f"{BASE}/3/fix", json={"slug": "rank", "instruction": "it is plus one", "backend": "api"},
                        headers=LOOPBACK)
    assert r.status_code == 200, r.text
    assert MarkFixReply.model_validate(r.json()).replacement == "$r = n + 1$"
    assert seen["backend"] == "api" and len(seen["images"]) == 1 and seen["images"][0].endswith("p0188-3.png")
    assert "$r = n - 1$" in seen["prompt"] and "it is plus one" in seen["prompt"] and "readers disagree" in seen["prompt"]
    assert page(kb) == before


def test_fix_defaults_to_env_backend_and_refuses_a_bad_answer(client, kb):
    with mock.patch.dict(os.environ, {"KB_LLM_BACKEND": "subscription"}), \
         mock.patch.object(svc.llm, "ask", return_value=SimpleNamespace(error="", text="$$x$$", backend="subscription",
                                                                         backend_used="")) as ask:
        r = client.post(f"{BASE}/3/fix", json={"slug": "rank", "instruction": "x"}, headers=LOOPBACK)
    assert ask.call_args.kwargs["backend"] == "subscription" and r.status_code == 502


def test_apply_replaces_the_formula(client, kb):
    r = client.post(f"{BASE}/4/apply", json={"slug": "rank", "replacement": "$$\nx = l\n$$"}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    assert "$$\nx = l\n$$\n" in page(kb) and "/p0188/4)" not in page(kb) and "/p0188/3)" in page(kb)
    res = json.load(open(store.resolutions_path(store.parsed_root(kb), SHA)))["p0188/4"]
    assert res["action"] == "fixed" and res["text"] == "$$\nx = l\n$$"


def test_apply_refuses_odd_dollars_and_changed_form(client, kb):
    before, n = page(kb), commits(kb)
    for bad in ("$r = n + 1", "$$r$$", "$a$ [x](https://example.com) $b$"):
        r = client.post(f"{BASE}/3/apply", json={"slug": "rank", "replacement": bad}, headers=LOOPBACK)
        assert r.status_code == 422
    assert page(kb) == before and commits(kb) == n


def test_read_only_kb_refuses(client, kb):
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nread_only = true\n')
    assert MarkDetail.model_validate(client.get(f"{BASE}/3").json()).read_only is True
    before = page(kb)
    r = client.post(f"{BASE}/3/resolve", json={"slug": "rank"}, headers=LOOPBACK)
    assert r.status_code == 403 and "read-only" in r.json()["detail"].lower()
    assert page(kb) == before


def test_read_only_server_refuses_with_405(client, kb):
    with mock.patch.dict(os.environ, {"KB_READ_ONLY": "1"}):
        assert client.post(f"{BASE}/3/fix", json={"slug": "rank", "instruction": "x"}, headers=LOOPBACK).status_code == 405


def test_apply_refuses_when_the_page_changed(client, kb):
    r = client.post(f"{BASE}/3/apply", json={"slug": "rank", "replacement": "$r = n + 1$", "expected_current": "$r = 0$"},
                    headers=LOOPBACK)
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    ok = client.post(f"{BASE}/3/apply", json={"slug": "rank", "replacement": "$r = n + 1$",
                                              "expected_current": "$r = n - 1$"}, headers=LOOPBACK)
    assert ok.status_code == 200 and "$r = n + 1$ here." in page(kb)


def test_apply_checks_page_before_replacement(client, kb):
    r = client.post(f"{BASE}/3/apply", json={"slug": "nope", "replacement": "$x"}, headers=LOOPBACK)
    assert r.status_code == 404


def test_fix_on_read_only_kb_spends_no_call(client, kb):
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nread_only = true\n')
    with mock.patch.object(svc.llm, "ask") as ask:
        r = client.post(f"{BASE}/3/fix", json={"slug": "rank", "instruction": "x"}, headers=LOOPBACK)
    assert r.status_code == 403 and not ask.called


def test_default_backend_comes_from_env(client, kb):
    with mock.patch.dict(os.environ, {"KB_LLM_BACKEND": "api"}):
        assert MarkDetail.model_validate(client.get(f"{BASE}/3").json()).default_backend == "api"


def test_resolution_write_failure_is_a_warning(client, kb):
    with mock.patch.object(svc.store, "write_resolution", side_effect=OSError("disk full")):
        r = client.post(f"{BASE}/3/resolve", json={"slug": "rank"}, headers=LOOPBACK)
    assert r.status_code == 200 and "disk full" in MarkStepResult.model_validate(r.json()).warning


def test_crlf_page_stays_crlf(client, kb):
    with open(os.path.join(kb, "wiki", "rank.md"), "w", encoding="utf-8", newline="") as f:
        f.write(PAGE.replace("\n", "\r\n"))
    assert client.post(f"{BASE}/3/resolve", json={"slug": "rank"}, headers=LOOPBACK).status_code == 200
    with open(os.path.join(kb, "wiki", "rank.md"), encoding="utf-8", newline="") as f:
        raw = f.read()
    assert "\r\n" in raw and "\n" not in raw.replace("\r\n", "")


def test_a_figure_png_is_served_and_nothing_outside_its_folder(kb, client):
    proot = store.parsed_root(kb)
    store.write_transcript_page(proot, SHA, 73, "![Figure 3.1](figure:%s/p0073/1)" % S12, [], figures=[
        {"id": 1, "file": "p0073-1.png"}, {"id": 2, "file": "../crops/p0188-3.png"}])
    os.makedirs(os.path.join(proot, SHA, "figures"))
    with open(os.path.join(proot, SHA, "figures", "p0073-1.png"), "wb") as f:
        f.write(PNG)
    r = client.get(f"/api/figures/{S12}/p0073/1")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert client.get(f"/api/figures/{S12}/p0073/2").status_code == 404
    assert client.get(f"/api/figures/{S12}/p0073/9").status_code == 404
    assert client.get(f"/api/figures/{S12}/x/1").status_code == 404

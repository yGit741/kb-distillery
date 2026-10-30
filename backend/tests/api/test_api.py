"""The FastAPI skeleton: typed routes, auto-discovery, local-only guards, SSE helper, legacy fall-through."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from unittest import mock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kb.api import app as app_mod
from kb.api import security, sse
from kb.api.app import create_app, discover_routers
from kb.api.models.health import HealthSnapshot
from kb.api.models.lifecycle import LifecycleSnapshot

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


# ── a canned health snapshot with the real shape (the real run rewrites index.md and corpus.tsv) ──
def canned_health():
    metrics = {"errors": 0, "warnings": 2, "hooks": "ok", "broken": 1, "orphans": 3, "queued": 4,
               "coherence_internal": 0, "coherence_external": 1, "coherence_cosmetic": 2, "coherence_open": 3,
               "lint_ms": 12.5, "sha1_ms": 1.0, "wiki_ms": 2.0, "links_ms": 3.0, "raw_tokens": 100,
               "wiki_tokens": 10, "index_savings_pct": 90, "queued_mb": 1.5, "partial_books": 1, "scopes": 2,
               "scope_uncovered": 0, "persons_unverified": 1, "person_unknowns": 0, "lineage_stubs": 0,
               "to_read_stubs": 5}
    return {"generated_at": "2026-10-24T00:00:00Z", "values": metrics,
            "statuses": {k: "ok" for k in metrics}, "hooks_ok": True, "inbox_count": 0, "wiki_pages": 7,
            "raw_files": 9, "orphan_slugs": ["a"], "compression_pct": 90,
            "graphs": {"in_degree": {"0": 1}, "lint_phases_ms": {"wiki": 2.0}},
            "partial_books": [{"slug": "book-x"}], "lineage_stubs": [], "legacy_extra": 1}


def test_health_valid_model_and_legacy_superset(client):
    with mock.patch("kb.services.health.build_health_snapshot", return_value=canned_health()), \
         mock.patch("kb.api.routers.health.build_health_snapshot", return_value=canned_health()):
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    HealthSnapshot.model_validate(body)
    assert body["legacy_extra"] == 1               # fields the model does not list still pass through
    assert body["values"]["errors"] == 0


def test_health_service_drops_private_rows():
    snap = canned_health() | {"_rows": {"x": 1}}
    with mock.patch("kb.lint.lint.collect_snapshot", return_value=snap):
        from kb.services.health import build_health_snapshot
        assert "_rows" not in build_health_snapshot()


def _real_kb_with_history():
    from kb import kbconfig
    cfg = kbconfig.current()
    return bool(os.environ.get("KB")) and not os.environ.get("KB_ROOT") and bool(cfg and cfg.git_root)


@pytest.mark.skipif(not _real_kb_with_history(), reason="reads a real knowledge base with git history: run with KB=<id>")
def test_lifecycle_on_the_real_vault(client):
    r = client.get("/api/lifecycle?limit=5")
    assert r.status_code == 200
    body = r.json()
    model = LifecycleSnapshot.model_validate(body)
    assert model.schema_.version and body["schema"]["version"] == model.schema_.version
    assert body["timeline"] and len(body["timeline"]) <= 5
    assert client.get("/api/lifecycle?limit=0").status_code == 422


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=dict(os.environ, **ENV))


def test_lifecycle_on_a_fixture_vault(client):
    from kb.core.schema import SCHEMA_VERSION
    v = "%d.%d" % SCHEMA_VERSION
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, ENV):
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "t")
        git(root, "config", "user.email", "t@t")
        os.makedirs(os.path.join(root, "wiki"))
        open(os.path.join(root, "wiki", "a.md"), "w").write("x\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", f"kb(digest): a (kb-{v}.1)\n\nKB-Version: {v}.1\nKB-Op: digest\nKB-Target: a")
        with mock.patch("kb.api.routers.lifecycle.vault_root", return_value=root):
            r = client.get("/api/lifecycle")
        assert r.status_code == 200, r.text
        body = r.json()
        LifecycleSnapshot.model_validate(body)
        assert body["version"] == f"{v}.1"
        assert body["timeline"][0]["op"] == "digest"
        assert body["stats"]["ops_30d"] == {"digest": 1}


# ── security ───────────────────────────────────────────────────────────────
def guarded_app():
    app = create_app(legacy=False)

    @app.post("/api/_throwaway")
    def throwaway(payload: dict):
        return {"ok": True}

    return app


def test_mutation_needs_a_loopback_origin():
    c = TestClient(guarded_app())
    assert c.post("/api/_throwaway", json={}).status_code == 403                                  # no Origin
    assert c.post("/api/_throwaway", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/_throwaway", json={}, headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert c.post("/api/_throwaway", json={}, headers=LOOPBACK).json() == {"ok": True}
    assert c.get("/api/lifecycle?limit=1").status_code == 200                                      # reads need none


def test_body_cap_and_host_check():
    c = TestClient(guarded_app())
    big = b"x" * (security.MAX_BODY_BYTES + 1)
    r = c.post("/api/_throwaway", content=big, headers={**LOOPBACK, "Content-Type": "application/json"})
    assert r.status_code == 413
    assert c.get("/api/lifecycle?limit=1", headers={"Host": "evil.example"}).status_code == 400


def test_loopback_bind_check():
    security.assert_loopback_bind("127.0.0.1")
    security.assert_loopback_bind("localhost")
    security.assert_loopback_bind("::1")
    for host in ("0.0.0.0", "192.168.1.5", "example.com", ""):
        with pytest.raises(SystemExit):
            security.assert_loopback_bind(host)


def test_safe_raw_path_dependency(tmp_path):
    raw = tmp_path / "raw" / "printed-docs"
    raw.mkdir(parents=True)
    (raw / "2000-x.pdf").write_bytes(b"%PDF")
    (tmp_path / "raw" / "inbox").mkdir()
    (tmp_path / "raw" / "inbox" / "y.pdf").write_bytes(b"%PDF")
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", raw / "evil.pdf")
    app = FastAPI()

    @app.get("/raw/{path:path}")
    def get_raw(full: str = Depends(security.safe_raw_path)):
        return {"file": os.path.basename(full)}

    c = TestClient(app)
    with mock.patch("kb.services.corpus.ROOT", str(tmp_path)):
        assert c.get("/raw/raw/printed-docs/2000-x.pdf").json() == {"file": "2000-x.pdf"}
        assert c.get("/raw/printed-docs/2000-x.pdf").status_code == 200       # the raw/ prefix is optional
        for bad in ("raw/printed-docs/../../secret.txt", "raw/%2e%2e/secret.txt", "../secret.txt",
                    "raw/printed-docs/evil.pdf", "raw/inbox/y.pdf", "raw/printed-docs/missing.pdf",
                    "meta/corpus.tsv", "/etc/passwd"):
            assert c.get(f"/raw/{bad}").status_code == 404, bad


# ── SSE ─────────────────────────────────────────────────────────────────────
def test_sse_framing():
    app = FastAPI()

    @app.get("/stream")
    def stream():
        def gen():
            yield "sources", {"hits": [1]}
            yield "ping", None
            yield "delta", "héllo"
            yield "done", {}
        return sse.sse_response(gen())

    r = TestClient(app).get("/stream")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text == ('event: sources\ndata: {"hits": [1]}\n\n: ping\n\n'
                      'event: delta\ndata: "h\\u00e9llo"\n\nevent: done\ndata: {}\n\n')


def test_sse_error_in_generator_becomes_an_event():
    def gen():
        yield "delta", "a"
        raise RuntimeError("boom")

    async def run():
        return [f async for f in sse.sse_frames(gen())]

    frames = asyncio.run(run())
    assert frames[-1] == b'event: error\ndata: {"error": "boom"}\n\n'


def test_sse_quiet_generator_gets_pings():
    release = threading.Event()

    def gen():
        release.wait(5)
        yield "done", {}

    async def run():
        out = []
        async for f in sse.sse_frames(gen(), ping_seconds=0.05):
            out.append(f)
            if len(out) == 2:
                release.set()
        return out

    frames = asyncio.run(run())
    assert frames[:2] == [sse.PING_FRAME, sse.PING_FRAME] and frames[-1] == b"event: done\ndata: {}\n\n"


def test_sse_disconnect_closes_the_generator():
    closed = threading.Event()

    def gen():
        try:
            n = 0
            while True:
                n += 1
                time.sleep(0.01)
                yield "delta", n
        finally:
            closed.set()

    async def run():
        frames = sse.sse_frames(gen())
        await frames.__anext__()            # the client reads one frame ...
        await frames.aclose()               # ... and goes away

    asyncio.run(run())
    assert closed.wait(3), "the generator was not closed after the client disconnected"


# ── router auto-discovery ────────────────────────────────────────────────────
def test_shipped_routers_are_discovered():
    assert {"health", "lifecycle"} <= {name for name, _ in discover_routers()}


def test_a_dropped_in_module_is_picked_up(tmp_path, monkeypatch):
    pkg = tmp_path / "tmp_kb_routers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "ping.py").write_text(textwrap.dedent("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/api/ping")
        def ping():
            return {"pong": True}
    """))
    (pkg / "_private.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")
    (pkg / "helpers.py").write_text("x = 1\n")             # no `router`: ignored
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("tmp_kb_routers", None)
    assert [n for n, _ in discover_routers("tmp_kb_routers")] == ["ping"]
    c = TestClient(create_app(routers_package="tmp_kb_routers", legacy=False))
    assert c.get("/api/ping").json() == {"pong": True}
    assert c.get("/api/health").status_code == 404           # only the given package is included


# ── legacy fall-through and the React shell ──────────────────────────────────
def test_legacy_pages_and_api_names_still_answer(client):
    r = client.get("/explore")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/legacy/explore").text == r.text                                # the shell's link form
    assert client.get("/legacy/graph").status_code == 200                              # ported, old page kept
    assert client.get("/api/chat/status").json()["backend"] in ("agent", "direct")
    assert client.get("/nope-not-a-page").status_code == 404


def test_legacy_post_keeps_its_own_rules(client):
    legacy = {"Content-Type": "application/json"}
    assert client.post("/api/raw-action", json={}).status_code == 400                         # reached the handler
    foreign = client.post("/api/raw-action", json={}, headers={**legacy, "Origin": "https://evil.example"})
    assert foreign.status_code == 403


def test_spa_fallback(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "assets" / "a.js").write_text("js")
    c = TestClient(create_app(dist=str(tmp_path), legacy=False))
    assert c.get("/app").text == "<html>shell</html>"
    assert c.get("/app/graph/deep/link").text == "<html>shell</html>"
    assert c.get("/app/assets/a.js").text == "js"
    assert c.get("/assets/a.js").text == "js"
    assert "shell" not in c.get("/assets/%2e%2e/index.html").text
    assert c.get("/app/%2e%2e/%2e%2e/etc/passwd").text == "<html>shell</html>"
    (tmp_path / ".src-hash").write_text("abc")
    assert c.get("/app/.src-hash").text == "<html>shell</html>"   # dotfiles stay private


def _frontend(tmp_path):
    fe = tmp_path / "frontend"
    (fe / "src").mkdir(parents=True)
    (fe / "src" / "main.tsx").write_text("v1")
    (fe / "node_modules").mkdir()
    return fe


def test_ensure_app_dist_builds_only_when_sources_change(tmp_path):
    from kb.api.spa import ensure_app_dist
    fe = _frontend(tmp_path)
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        (fe / "dist").mkdir(exist_ok=True)
        (fe / "dist" / "index.html").write_text("built")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert ensure_app_dist(fe, runner) == "built"
    assert ensure_app_dist(fe, runner) == "fresh" and len(calls) == 1
    (fe / "src" / "main.tsx").write_text("v2")
    assert ensure_app_dist(fe, runner) == "built" and len(calls) == 2


def test_ensure_app_dist_keeps_old_dist_on_failure(tmp_path):
    from kb.api.spa import ensure_app_dist
    fe = _frontend(tmp_path)
    fail = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "tsc: error TS1")
    assert ensure_app_dist(fe, fail).startswith("frontend build failed")
    assert not (fe / "dist" / ".src-hash").exists()
    (fe / "node_modules").rmdir()
    assert "web-install" in ensure_app_dist(fe, fail)


def test_ported_graph_redirects_to_the_app(client):
    r = client.get("/graph?focus=x", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/app/graph?focus=x"
    assert client.get("/graph.html", follow_redirects=False).headers["location"] == "/app/graph"

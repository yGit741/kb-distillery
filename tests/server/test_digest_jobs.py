"""Digest jobs on a temp kb: preview, start, progress, cancel. No model call, no network, no real worker process."""
import json
import os
import signal
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.ingest import digest_many, extract
from kb_distillery.ingest import paths as ingest_paths
from kb_distillery.ingest import session as session_mod
from kb_distillery.ingest import verify
from kb_distillery.server.app import create_app
from kb_distillery.server.models.digest_jobs import DigestJob, DigestJobList, DigestPreview
from kb_distillery.services import digest_jobs as svc
from tests.ingest.test_digest_many import GOOD          # a claims.json that validates
from tests.ops.test_view import ENV, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
RAWS = ["raw/web-clips/a.md", "raw/web-clips/b.md"]
AVAIL = {"subscription": {"ok": True, "why": "logged in", "fix": ""}, "api": {"ok": True, "why": "key", "fix": ""},
         "batch": {"ok": True, "why": "key", "fix": ""}, "providers": {}}


class FakeProc:
    pid = 424242

    def __init__(self, alive=False):
        self.alive = alive

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def kb(tmp_path, monkeypatch):
    root = make_repo(str(tmp_path / "kb"), gitignore="meta/.ops/\nmeta/.ingest/\n")
    for raw in RAWS:
        path = os.path.join(root, raw)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {raw}\n\n" + "body text " * 50)
    rows = {raw: {"disposition": "queued"} for raw in RAWS}
    with mock.patch.dict(os.environ, {**ENV, llm.ENV_BACKEND: ""}):
        monkeypatch.setattr(svc, "DEFAULT_ROOT", root)
        for mod in (ingest_paths, verify, digest_many, session_mod):
            monkeypatch.setattr(mod, "ROOT", root)
        monkeypatch.setattr(ingest_paths, "INGEST_ROOT", os.path.join(root, "meta", ".ingest"))
        monkeypatch.setattr(verify, "read_manifest", lambda: rows)
        monkeypatch.setattr(digest_many, "scope_for", lambda raw: {})
        monkeypatch.setattr(digest_many.book_mod, "is_book", lambda path: False)
        monkeypatch.setattr(extract, "extract_text", lambda path, **k: open(path).read())
        monkeypatch.setattr(extract, "_template", lambda raw, scope: {"raw": raw})
        monkeypatch.setattr(llm, "availability", lambda: AVAIL)
        monkeypatch.setattr(llm, "run", lambda *a, **k: pytest.fail("no model call in this test"))
        monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("no model call in this test"))
        monkeypatch.setattr(svc, "_PROCS", {})
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


def fake_llm(monkeypatch, replies=None):
    """llm.run answers each request with GOOD claims (or replies[raw]); records the backends it was asked for."""
    seen = []

    def run(reqs, backend=None, **kw):
        seen.append((backend, len(reqs)))
        by_id = {digest_many.request_id(r): r for r in RAWS}
        return [llm.Result(id=r.id, text=(replies or {}).get(by_id[r.id], json.dumps({**GOOD, "raw": by_id[r.id]})),
                           usd=0.01, backend=backend, model="claude-sonnet-5-5") for r in reqs]

    monkeypatch.setattr(llm, "run", run)
    return seen


def sync_worker(monkeypatch, kb):
    """Spawn runs the worker body in-process, to the end, and returns a finished process."""
    def spawn(root, job_id):
        svc.run_job(job_id, root)
        return FakeProc()

    monkeypatch.setattr(svc, "spawn", spawn)


def test_preview_makes_no_model_call_and_prices_every_backend(client):
    r = client.post("/api/digest/preview", json={"raws": RAWS}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    p = DigestPreview.model_validate(r.json())
    assert p.backend == "subscription" and "logged in" in p.backend_why       # small job, claude logged in
    assert p.provider == "claude" and p.tier and p.depth == "full" and p.model == llm.model_id(digest_many.MODEL)
    assert p.sources == 2 and p.requests == 2 and not p.skipped
    assert p.tokens_in > 0 and p.cost_usd > 0 and p.billed_usd == 0.0         # the subscription bills no tokens
    opts = {o.backend: o for o in p.options}
    assert set(opts) == set(llm.BACKENDS)
    assert opts["batch"].cost_usd == pytest.approx(opts["api"].cost_usd / 2, rel=0.01)
    assert opts["batch"].seconds > 3600 and "hours" in opts["batch"].eta
    assert opts["api"].billed_usd == opts["api"].cost_usd


def test_billing_defaults(kb, monkeypatch):
    assert svc.default_backend(1, kb)[0] == "subscription"
    assert svc.default_backend(6, kb)[0] == "api"                              # above bulk_threshold (5)
    assert svc.default_backend(6, kb, "batch")[0] == "batch"                   # an explicit choice wins
    with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nid = "t"\nname = "T"\nschema_version = "1.0"\n\n[llm]\nbulk_threshold = 10\n')
    assert svc.default_backend(6, kb)[0] == "subscription"
    monkeypatch.setattr(llm, "availability", lambda: {**AVAIL, "subscription": {"ok": False, "why": "no", "fix": ""}})
    assert svc.default_backend(1, kb)[0] == "api"
    with mock.patch.dict(os.environ, {llm.ENV_BACKEND: "batch"}):
        assert svc.default_backend(1, kb) == ("batch", f"${llm.ENV_BACKEND}")
    with pytest.raises(svc.JobError) as e:
        svc.default_backend(1, kb, "carrier-pigeon")
    assert e.value.status == 422


def test_preview_and_start_refuse_bad_input(client):
    for body in ({"raws": []}, {"raws": ["raw/web-clips/missing.md"]}, {"raws": RAWS, "backend": "nope"},
                 {"raws": RAWS, "model": "nope"}):
        assert client.post("/api/digest/preview", json=body, headers=LOOPBACK).status_code == 422, body
        assert client.post("/api/digest/jobs", json=body, headers=LOOPBACK).status_code == 422, body
    assert client.get("/api/digest/jobs/nope").status_code == 404
    assert client.get("/api/digest/jobs/../etc").status_code == 404


def test_a_job_digests_each_source_once_and_records_its_page(client, kb, monkeypatch):
    seen = fake_llm(monkeypatch)
    sync_worker(monkeypatch, kb)
    done = []

    def digest_one(raw, claims_path):
        with open(claims_path, encoding="utf-8") as f:
            assert json.load(f)["raw"] == raw                                 # the filled claims reach the session
        done.append(raw)
        sha = f"s{len(done)}"
        os.makedirs(ingest_paths.session_dir(sha), exist_ok=True)
        with open(os.path.join(ingest_paths.session_dir(sha), "plan.json"), "w") as f:
            json.dump({"wiki_slug": os.path.basename(raw)[:-3]}, f)
        return sha

    monkeypatch.setattr(digest_many, "digest_one", digest_one)
    r = client.post("/api/digest/jobs", json={"raws": RAWS, "backend": "api"}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    job = DigestJob.model_validate(client.get(f"/api/digest/jobs/{job_id}").json())
    assert job.status == "done" and job.backend == "api" and done == RAWS
    assert [s.status for s in job.sources] == ["finalized", "finalized"]
    assert [s.page for s in job.sources] == ["wiki/a.md", "wiki/b.md"]
    assert seen == [("api", 1), ("api", 1)] and job.spent_usd == pytest.approx(0.02)   # one fill per source
    assert os.path.isfile(os.path.join(kb, "meta", ".jobs", job_id, "job.json"))
    listed = DigestJobList.model_validate(client.get("/api/digest/jobs").json())
    assert [j.id for j in listed.jobs] == [job_id]

    with client.stream("GET", f"/api/digest/jobs/{job_id}/events") as s:      # a finished job: one frame, then the end
        text = "".join(s.iter_text())
    assert "event: job" in text and "event: end" in text and '"status": "done"' in text


def test_batch_job_sends_one_batch_and_a_rejected_fill_fails_only_its_source(client, kb, monkeypatch):
    seen = fake_llm(monkeypatch, replies={RAWS[0]: "no json"})
    sync_worker(monkeypatch, kb)
    done = []
    monkeypatch.setattr(digest_many, "digest_one", lambda raw, path: done.append(raw) or "s")
    r = client.post("/api/digest/jobs", json={"raws": RAWS, "backend": "batch"}, headers=LOOPBACK)
    job = DigestJob.model_validate(client.get(f"/api/digest/jobs/{r.json()['id']}").json())
    assert seen == [("batch", 2)] and done == [RAWS[1]]
    by = {s.raw: s for s in job.sources}
    assert by[RAWS[0]].status == "failed" and "rejected" in by[RAWS[0]].note
    assert by[RAWS[1]].status == "finalized" and job.status == "done"


def test_a_failed_digest_fails_the_job_when_nothing_finalized(client, kb, monkeypatch):
    fake_llm(monkeypatch)
    sync_worker(monkeypatch, kb)

    def boom(raw, path):
        raise RuntimeError("finalize failed (rolled back)")

    monkeypatch.setattr(digest_many, "digest_one", boom)
    r = client.post("/api/digest/jobs", json={"raws": RAWS}, headers=LOOPBACK)
    job = client.get(f"/api/digest/jobs/{r.json()['id']}").json()
    assert job["status"] == "failed" and all("finalize failed" in s["note"] for s in job["sources"])


def test_start_refuses_a_second_live_job_and_an_open_session(client, kb, monkeypatch):
    monkeypatch.setattr(svc, "spawn", lambda root, job_id: FakeProc(alive=True))
    r = client.post("/api/digest/jobs", json={"raws": RAWS[:1]}, headers=LOOPBACK)
    assert r.status_code == 200 and r.json()["status"] == "queued"
    again = client.post("/api/digest/jobs", json={"raws": RAWS[1:]}, headers=LOOPBACK)
    assert again.status_code == 409 and "still running" in again.json()["detail"]
    svc._PROCS.clear()                                                         # the worker is gone (and never wrote a pid)
    monkeypatch.setattr(svc, "START_GRACE", 0.0)
    assert client.get(f"/api/digest/jobs/{r.json()['id']}").json()["status"] == "failed"

    monkeypatch.setattr(session_mod, "find_open_session", lambda raw: "abc" if raw == RAWS[0] else None)
    blocked = client.post("/api/digest/jobs", json={"raws": RAWS}, headers=LOOPBACK)
    assert blocked.status_code == 409 and "already open" in blocked.json()["detail"]


def test_cancel_kills_the_worker_group_and_rolls_back_the_session_in_flight(client, kb, monkeypatch):
    proc = FakeProc(alive=True)
    monkeypatch.setattr(svc, "spawn", lambda root, job_id: proc)
    job_id = client.post("/api/digest/jobs", json={"raws": RAWS}, headers=LOOPBACK).json()["id"]

    # the worker had finalized a, and was half way through finalizing b (a page promoted, its backup kept)
    page = os.path.join(kb, "wiki", "b.md")
    with open(page, "w", encoding="utf-8") as f:
        f.write("half promoted\n")
    sid = session_mod.session_id(ingest_paths.sha1_file(RAWS[1]), {})
    os.makedirs(os.path.join(ingest_paths.session_dir(sid), "backup"))
    with open(os.path.join(ingest_paths.session_dir(sid), "backup", "b.md"), "w", encoding="utf-8") as f:
        f.write("old page\n")
    ingest_paths.save_session(sid, {"raw": RAWS[1], "sha1": sid, "status": "finalizing", "backup_files": ["wiki/b.md"],
                                    "new_files": [], "modified_files": ["wiki/b.md"], "scope": {}})
    job = svc._load(kb, job_id)
    job.update(status="running", current=RAWS[1], pid=proc.pid)
    job["sources"][0].update(status="finalized", page="wiki/a.md")
    job["sources"][1]["status"] = "digesting"
    svc._save(kb, job)

    kills = []

    def killpg(pid, sig):
        kills.append((pid, sig))
        proc.alive = False

    monkeypatch.setattr(os, "killpg", killpg)
    r = client.delete(f"/api/digest/jobs/{job_id}", headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = DigestJob.model_validate(r.json())
    assert kills == [(proc.pid, signal.SIGTERM)]
    assert out.status == "cancelled" and [s.status for s in out.sources] == ["finalized", "cancelled"]
    assert "rolled back" in out.sources[1].note
    assert open(page, encoding="utf-8").read() == "old page\n"                  # the backup is back
    assert ingest_paths.load_session(sid)["status"] == "aborted"
    assert client.delete(f"/api/digest/jobs/{job_id}", headers=LOOPBACK).status_code == 409   # already ended


def test_read_only_server_refuses_job_writes(client, monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    assert client.post("/api/digest/jobs", json={"raws": RAWS}, headers=LOOPBACK).status_code == 405
    assert client.delete("/api/digest/jobs/x", headers=LOOPBACK).status_code == 405


def test_worker_cli_needs_a_job_id():
    assert svc.main([]) == 2


def test_the_real_worker_process_runs_a_job_in_its_own_group(kb):
    """`_spawn` starts `python -m kb_distillery.services.digest_jobs run <id>` (here on a job with nothing left to do)."""
    job = {"id": "20261108-000000-abcdef", "status": "queued", "created": "", "created_ts": 0, "backend": "api",
           "model": "claude-sonnet-5-5", "provider": "claude", "tier": "standard", "depth": "full", "pid": None,
           "current": None, "spent_usd": 0.0, "error": None, "sources": []}
    svc._save(kb, job)
    proc = svc._spawn(kb, job["id"])
    assert proc.wait(120) == 0, open(os.path.join(svc.job_dir(kb, job["id"]), "worker.log")).read()
    done = svc._load(kb, job["id"])
    assert done["status"] == "done" and done["pid"] == proc.pid

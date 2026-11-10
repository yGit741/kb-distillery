"""POST /api/ingest and its job over HTTP on a temp kb repo: the LLM and the fetch are monkeypatched, the real kb is never written."""
import json
import os
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.ingest import catalog, paths as ingest_paths
from kb_distillery.proposals import service as proposals
from kb_distillery.server.app import create_app
from kb_distillery.server.models.ingest_ui import IngestJob, IngestStarted
from kb_distillery.services import inbox_add, ingest_ui as svc
from tests.ops.test_view import ENV, make_repo

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
NOTE = b"# Tensor rank notes\n\nA short note about tensor rank and low-rank structure.\n"
CLAIMS = {"raw": "x", "title": "Tensor rank notes", "problem": "How to measure tensor rank.", "method": "Count terms.",
          "results": ["Rank bounds the size of a decomposition.", "Low rank means cheap storage."],
          "equations": [], "concepts": ["tensor rank", "Low Rank", "alpha"], "open_questions": [], "citekey": "", "url": "",
          "year": None, "authors": []}


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path / "kb"), gitignore="meta/.ops/\n.local/\n")
    with open(os.path.join(root, "wiki", "alpha.md"), "w", encoding="utf-8") as f:
        f.write("---\ntype: idea\nlayer: concept\n---\n\n# Alpha\n\nText.\n\n## Connections\n- [Beta](beta.md)\n\n## My notes\n\nMine.\n")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(svc, "DEFAULT_ROOT", root), mock.patch.object(proposals, "DEFAULT_ROOT", root), \
         mock.patch.object(inbox_add, "DEFAULT_ROOT", root), mock.patch.object(catalog, "ROOT", root), \
         mock.patch.object(ingest_paths, "ROOT", root), \
         mock.patch.object(catalog, "CATALOG_LOG_DIR", os.path.join(root, "meta", ".catalog")), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        yield root


@pytest.fixture
def client(kb):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake_llm():
    seen = []

    def ask(prompt, backend=None, **kw):
        seen.append({"backend": backend, **kw})
        return llm.Result(id="r0", text=json.dumps(CLAIMS), backend=backend or "subscription", model="m")
    with mock.patch.object(llm, "ask", ask):
        yield seen


def wait(client, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        job = IngestJob.model_validate(client.get(f"/api/ingest/{job_id}").json())
        if job.status != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


def upload(client, name="notes.md", data=NOTE, **fields):
    return client.post("/api/ingest", files={"file": (name, data, "text/markdown")}, data=fields, headers=LOOPBACK)


def test_upload_markdown_ends_in_one_proposal(client, kb, fake_llm):
    r = upload(client, tier="full", backend="api")
    assert r.status_code == 200, r.text
    job = wait(client, IngestStarted.model_validate(r.json()).job_id)
    assert job.status == "done", job.error
    assert [s.name for s in job.steps] == ["fetch", "convert", "digest", "propose"]
    assert [s.state for s in job.steps] == ["skipped", "done", "done", "done"]
    assert fake_llm[0]["backend"] == "api" and fake_llm[0]["model"] == "standard"
    raws = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(kb, "raw")) for f in fs]
    assert any(p.endswith("notes.md") for p in raws) and not os.listdir(os.path.join(kb, "raw", "inbox"))
    p = proposals.get(job.proposal_id, kb)
    kinds = {o["slug"]: o["kind"] for o in p["revisions"][p["current"]]["ops"]}
    assert kinds["alpha"] == "edit_page"
    assert sorted(k for k in kinds.values() if k == "create_page") == ["create_page"] * 3        # source, two new ideas
    assert "tensor-rank" in kinds and "low-rank" in kinds
    assert p["producer"]["kind"] == "ingest" and p["producer"]["context"]["tier"] == "full"
    assert p["status"] == "open" and sorted(job.pages) == sorted(kinds)
    assert not os.path.exists(os.path.join(kb, "wiki", "tensor-rank.md"))                 # nothing landed in the wiki
    alpha = [o for o in p["revisions"][p["current"]]["ops"] if o["slug"] == "alpha"][0]["new_text"]
    assert "Mine." in alpha and alpha.index("Tensor rank notes") < alpha.index("## My notes")


def test_listed_tier_makes_no_model_call(client, kb, fake_llm):
    job = wait(client, upload(client, tier="listed").json()["job_id"])
    assert job.status == "done" and [s.state for s in job.steps][2] == "skipped" and fake_llm == []
    assert proposals.get(job.proposal_id, kb)["counts"]["hunks"] >= 1


def test_url_is_fetched_then_digested(client, kb, fake_llm):
    with mock.patch.object(svc.scrap, "_fetch", return_value=(b"<html><body><p>Tensor rank page</p></body></html>", "text/html")):
        r = client.post("/api/ingest", json={"url": "https://example.org/a/tensor", "tier": "easy"}, headers=LOOPBACK)
        job = wait(client, r.json()["job_id"])
    assert job.status == "done", job.error
    assert job.steps[0].state == "done" and "example-org" in job.steps[0].detail
    assert fake_llm[0]["model"] == "light"


@pytest.mark.parametrize("url", ["ftp://example.org/x", "http://localhost/x", "http://127.0.0.1:8765/api", "https://10.0.0.5/x",
                                 "https://user:pw@example.org/x", "not a url", "http://intranet/x"])
def test_url_is_validated(client, url):
    assert client.post("/api/ingest", json={"url": url}, headers=LOOPBACK).status_code == 422


def test_bad_inputs(client, kb):
    assert upload(client, "tool.exe", b"MZ").status_code == 415
    assert upload(client, "empty.md", b"").status_code == 422
    assert upload(client, tier="thorough").status_code == 422
    assert upload(client, collection="no-such-page").status_code == 422
    assert client.post("/api/ingest", data={"tier": "full"}, headers=LOOPBACK).status_code in (415, 422)
    assert client.get("/api/ingest/nope").status_code == 404
    assert upload(client).status_code == 200
    r = client.post("/api/ingest", files={"file": ("notes.md", NOTE)}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_model_failure_is_calm_and_nothing_is_proposed(client, kb):
    with mock.patch.object(llm, "ask", return_value=llm.Result(id="r0", error="rate limited")):
        job = wait(client, upload(client).json()["job_id"])
    assert job.status == "failed" and job.proposal_id is None and "try again" in job.error
    assert [s.state for s in job.steps][2] == "failed"
    assert proposals.list_proposals(root=kb) == []


def test_same_source_twice_is_a_duplicate(client, kb, fake_llm):
    wait(client, upload(client).json()["job_id"])
    sha = inbox_add._sha(NOTE)
    with open(os.path.join(kb, "meta", "corpus.tsv"), "w", encoding="utf-8") as f:           # lint is mocked: seed the row
        f.write("path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n"
                f"raw/web-clips/notes.md\t{sha}\tweb\tqueued\t\t\t\n")
    job = wait(client, upload(client, "again.md").json()["job_id"])
    assert job.status == "failed" and "already" in job.error


def test_events_stream_ends_with_the_final_job(client, kb, fake_llm):
    job_id = upload(client).json()["job_id"]
    body = client.get(f"/api/ingest/{job_id}/events").text
    frames = [f for f in body.split("\n\n") if f.startswith("event:")]
    assert frames[0].startswith("event: job") and frames[-1].startswith("event: end")
    last = [json.loads(f.split("data: ", 1)[1]) for f in frames if f.startswith("event: job")][-1]
    assert last["status"] == "done" and last["proposal_id"]


def test_read_only_server_refuses(client, kb, monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    assert upload(client).status_code == 405

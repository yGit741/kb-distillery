"""Corpus tables, raw preview/file/thumb and the digest action (stubbed: a test never starts a digest)."""
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.corpus import CorpusTable, DigestResult, RawPreview
from kb_distillery.services import corpus

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.mark.parametrize("fmt", corpus.FORMATS)
def test_every_format_on_the_real_vault(client, fmt):
    r = client.get("/api/corpus", params={"format": fmt})
    assert r.status_code == 200
    body = r.json()
    table = CorpusTable.model_validate(body)
    legacy = corpus.build_corpus(fmt)
    assert set(body) >= set(legacy)                                  # a superset of the legacy keys
    assert table.format == fmt and table.count == len(table.rows) == legacy["count"]
    assert [c.key for c in table.columns] == [c["key"] for c in legacy["columns"]]
    for row, old in zip(body["rows"], legacy["rows"]):
        assert set(row) >= set(old)


def test_unknown_or_missing_format_is_400_with_the_format_list(client):
    for q in ({"format": "inbox"}, {"format": "nope"}, {}):
        r = client.get("/api/corpus", params=q)
        assert r.status_code == 400
        assert r.json() == {"error": "unknown format", "formats": list(corpus.FORMATS)}


@pytest.fixture
def raw(tmp_path):
    d = tmp_path / "raw" / "printed-docs"
    d.mkdir(parents=True)
    (d / "2000-x.pdf").write_bytes(b"%PDF-1.4 not really")
    (d / "2000-note.md").write_text("hello")
    (d / "2000-pic.png").write_bytes(b"\x89PNG fake")
    (d / "2000-data.bin").write_bytes(b"\x00")
    (tmp_path / "raw" / "inbox").mkdir()
    (tmp_path / "raw" / "inbox" / "y.pdf").write_bytes(b"%PDF")
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", d / "evil.pdf")
    with mock.patch.object(corpus, "ROOT", str(tmp_path)):
        yield tmp_path


def test_preview_keys_match_the_legacy_preview(client, raw):
    rel = "raw/printed-docs/2000-note.md"
    with mock.patch("kb_distillery.ingest.extract.extract_text", return_value="hello text"):
        body = client.get(f"/api/raw/{rel}").json()
        short = client.get("/api/raw/printed-docs/2000-note.md").json()   # the raw/ prefix is optional
        legacy, err = corpus.build_preview(rel)
    assert err is None
    RawPreview.model_validate(body)
    assert set(body) >= set(legacy) and body["text"] == "hello text" and short == body
    assert body["format"] == "printed-docs" and body["exists"] is True


def test_file_and_thumb(client, raw):
    r = client.get("/api/raw/raw/printed-docs/2000-note.md/file")
    assert r.status_code == 200 and r.text == "hello" and r.headers["content-type"].startswith("text/plain")
    assert client.get("/api/raw/raw/printed-docs/2000-data.bin/file").status_code == 415
    t = client.get("/api/raw/raw/printed-docs/2000-pic.png/thumb")      # images are served as they are
    assert t.status_code == 200 and t.headers["content-type"] == "image/png" and t.content.startswith(b"\x89PNG")
    with mock.patch("kb_distillery.api.assets.thumbnail_png", return_value=b"PNGDATA") as thumb:
        t = client.get("/api/raw/raw/printed-docs/2000-x.pdf/thumb?w=500")
    assert t.status_code == 200 and t.content == b"PNGDATA"
    assert thumb.call_args.args[1] == 500
    with mock.patch("kb_distillery.api.assets.thumbnail_png", return_value=None):
        assert client.get("/api/raw/raw/printed-docs/2000-x.pdf/thumb").status_code == 415
    assert client.get("/api/raw/raw/printed-docs/2000-note.md/thumb").status_code == 415


BAD = ("raw/printed-docs/../../secret.txt", "raw/%2e%2e/secret.txt", "../secret.txt", "raw/printed-docs/evil.pdf",
       "raw/inbox/y.pdf", "raw/printed-docs/missing.pdf", "meta/corpus.tsv", "/etc/passwd")


@pytest.mark.parametrize("bad", BAD)
def test_raw_traversal_is_refused_on_every_raw_route(client, raw, bad):
    for suffix in ("", "/file", "/thumb"):
        assert client.get(f"/api/raw/{bad}{suffix}").status_code == 404, (bad, suffix)
    with mock.patch.object(corpus, "run_action") as run:
        # the test client folds "../" before sending, so that URL never reaches the raw route (legacy refuses it)
        assert client.post(f"/api/raw/{bad}/digest", headers=LOOPBACK).status_code in (400, 404)
    run.assert_not_called()


def test_digest_is_refused_without_a_loopback_origin_and_is_stubbed(client, raw):
    url = "/api/raw/raw/printed-docs/2000-x.pdf/digest"
    canned = {"exit": 0, "stdout": "ok", "stderr": "", "command": "python3 -m kb_distillery.ingest easy-digest x"}
    with mock.patch.object(corpus, "run_action", return_value=(canned, None)) as run, \
         mock.patch("subprocess.run", side_effect=AssertionError("a digest was started")):
        assert client.post(url).status_code == 403
        assert client.post(url, headers={"Origin": "https://evil.example"}).status_code == 403
        run.assert_not_called()
        r = client.post(url, headers=LOOPBACK)
        assert r.status_code == 200
        DigestResult.model_validate(r.json())
        assert r.json() == canned
        run.assert_called_once_with("easy-digest", "raw/printed-docs/2000-x.pdf")


def test_digest_service_error_is_400(client, raw):
    with mock.patch.object(corpus, "run_action", return_value=(None, "boom")):
        r = client.post("/api/raw/raw/printed-docs/2000-x.pdf/digest", headers=LOOPBACK)
    assert r.status_code == 400 and r.json() == {"error": "boom"}

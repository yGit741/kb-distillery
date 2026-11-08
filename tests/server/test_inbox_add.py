"""POST /api/inbox/files and /api/inbox/link-folder on a temp kb repo: no model, no network, the real kb is never written."""
import hashlib
import os
import re
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.ingest import catalog, paths as ingest_paths
from kb_distillery.server import security
from kb_distillery.server.app import create_app
from kb_distillery.server.models.inbox_add import InboxAddResult, LinkFolderResult
from kb_distillery.services import inbox_add as svc
from tests.ops.test_view import ENV, commits, git, head_files, make_repo

SUBJECT = re.compile(r"^kb\(catalog\): (?P<summary>.+) \(kb-\d+\.\d+\.\d+\)$")
LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path / "kb"), gitignore="meta/.ops/\n.local/\n")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch.object(svc, "DEFAULT_ROOT", root), \
         mock.patch.object(catalog, "ROOT", root), \
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


def post(client, files):
    return client.post("/api/inbox/files", files=[("files", f) for f in files], headers=LOOPBACK)


def test_two_files_one_duplicate_one_refused(client, kb):
    n = commits(kb)
    r = post(client, [("a note.md", b"# A\n\nsome text\n", "text/markdown"), ("page.html", b"<p>hi</p>", "text/html"),
                      ("tool.exe", b"MZ", "application/octet-stream")])
    assert r.status_code == 200, r.text
    out = InboxAddResult.model_validate(r.json())
    by = {f.name: f for f in out.files}
    assert by["a note.md"].status == "added" and by["page.html"].status == "added"
    assert by["a note.md"].raw_path and not by["a note.md"].raw_path.startswith("raw/inbox/")
    assert os.path.isfile(os.path.join(kb, by["a note.md"].raw_path))
    assert by["tool.exe"].status == "refused" and "unsupported" in by["tool.exe"].reason
    assert not os.listdir(os.path.join(kb, "raw", "inbox"))                 # nothing left unsorted
    assert commits(kb) == n + 1 and out.commit == git(kb, "rev-parse", "HEAD") and out.version.startswith("kb-")
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "add 2 sources from the app"
    assert git(kb, "log", "-1", "--format=%s").startswith("kb(catalog): ")
    assert any(p.startswith("raw/") for p in head_files(kb))

    # the same bytes again: in the corpus once lint has seen them (seeded here, lint is mocked), or still in the inbox
    sha = hashlib.sha1(b"# A\n\nsome text\n").hexdigest()[:12]
    with open(os.path.join(kb, "meta", "corpus.tsv"), "w", encoding="utf-8") as f:
        f.write("path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n"
                f"{by['a note.md'].raw_path}\t{sha}\tweb\tqueued\t\t\t\n")
    git(kb, "add", "-A")
    git(kb, "commit", "-q", "-m", "chore: corpus (retro)")
    n = commits(kb)
    again = InboxAddResult.model_validate(post(client, [("renamed.md", b"# A\n\nsome text\n", "text/markdown")]).json())
    assert [f.status for f in again.files] == ["duplicate"] and again.commit is None
    assert commits(kb) == n and not os.path.exists(os.path.join(kb, "raw", "inbox", "renamed.md"))


def test_same_batch_duplicate_and_name_collision(client, kb):
    out = InboxAddResult.model_validate(post(client, [("x.md", b"one", "text/markdown"), ("y.md", b"one", "text/markdown"),
                                                      ("x.md", b"two", "text/markdown")]).json())
    assert [f.status for f in out.files] == ["added", "duplicate", "added"]
    assert len({f.raw_path for f in out.files if f.raw_path}) == 2          # same name, different bytes: suffixed, not overwritten


def test_nothing_added_makes_no_commit(client, kb):
    n = commits(kb)
    out = InboxAddResult.model_validate(post(client, [("a.exe", b"MZ", "application/octet-stream")]).json())
    assert out.files[0].status == "refused" and out.commit is None and commits(kb) == n


def test_link_folder_adds_once_and_is_idempotent(client, kb, tmp_path):
    src = tmp_path / "sources"
    (src / "sub").mkdir(parents=True)
    (src / "a.md").write_bytes(b"alpha")
    (src / "sub" / "b.png").write_bytes(PNG)
    (src / "ignored.bin").write_bytes(b"x")
    n = commits(kb)
    r = client.post("/api/inbox/link-folder", json={"path": str(src)}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = LinkFolderResult.model_validate(r.json())
    assert out.linked and out.files_catalogued == 2 and out.skipped == 1 and out.commit
    assert commits(kb) == n + 1
    assert git(kb, "log", "-1", "--format=%s").startswith("kb(catalog): link folder sources (kb-")

    with open(os.path.join(kb, "meta", "corpus.tsv"), "w", encoding="utf-8") as f:     # lint is mocked: record what it would
        f.write("path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n")
        for sub in ("a.md", "b.png"):
            data = (src / sub).read_bytes() if sub == "a.md" else PNG
            f.write(f"raw/x/{sub}\t{hashlib.sha1(data).hexdigest()[:12]}\tx\tqueued\t\t\t\n")
    git(kb, "add", "-A")
    git(kb, "commit", "-q", "-m", "chore: corpus (retro)")
    n = commits(kb)
    again = LinkFolderResult.model_validate(client.post("/api/inbox/link-folder", json={"path": str(src)}, headers=LOOPBACK).json())
    assert again.linked and again.files_catalogued == 0 and again.commit is None and commits(kb) == n


def test_link_folder_refusals(client, kb, tmp_path):
    inside = os.path.join(kb, "wiki")
    for path, word in [(inside, "inside"), (str(tmp_path), "contains"), (str(tmp_path / "nope"), "existing"), ("relative/dir", "absolute")]:
        r = client.post("/api/inbox/link-folder", json={"path": path}, headers=LOOPBACK)
        assert r.status_code == 422 and word in r.json()["detail"], (path, r.text)


def test_the_body_cap_applies(client, kb):
    assert "/api/inbox/files" in security.UPLOAD_PATHS and security.MAX_UPLOAD_BYTES == 64 * 1024 * 1024
    mb = 1024 * 1024
    with mock.patch.object(security, "MAX_UPLOAD_BYTES", 6 * mb):          # the upload cap, scaled down: above the 4 MB default
        assert post(client, [("big.md", b"z" * 7 * mb, "text/markdown")]).status_code == 413
        assert post(client, [("five.md", b"y" * 5 * mb, "text/markdown")]).status_code == 200      # over 4 MB, under the upload cap
    assert not os.path.exists(os.path.join(kb, "raw", "inbox", "big.md"))


def test_an_open_ops_session_is_a_409(client, kb):
    with mock.patch("kb_distillery.ops.core.current_session", return_value={"op": "digest", "target": "x"}):
        assert post(client, [("a.md", b"a", "text/markdown")]).status_code == 409


def test_read_only_server_refuses_both(kb, monkeypatch):
    monkeypatch.setenv("KB_READ_ONLY", "1")
    n = commits(kb)
    with TestClient(create_app()) as c:
        assert post(c, [("a.md", b"a", "text/markdown")]).status_code == 405
        assert c.post("/api/inbox/link-folder", json={"path": "/tmp"}, headers=LOOPBACK).status_code == 405
    assert commits(kb) == n


def test_clean_name():
    assert svc.clean_name("My Paper (v2).PDF") == "My-Paper-v2.pdf"
    assert svc.clean_name("../../etc/passwd") == "passwd"
    assert svc.clean_name("") == "untitled"

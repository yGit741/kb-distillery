"""POST /api/kb/import(/validate): a zip upload or a git URL becomes a new kb. Temp dirs only; never ~/knowledge, no network."""
import io
import os
import tempfile
import zipfile

import pytest
from fastapi.testclient import TestClient

from kb_distillery import import_kb, llm
from kb_distillery.config import kb as kbconfig
from kb_distillery.server import security
from kb_distillery.server.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
PAGE = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Alpha\n\nSee [beta](beta.md).\n"
BETA = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Beta\n\nBack to [alpha](alpha.md).\n"
BAD = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Bad\n\nSee [gone](missing.md).\n"


@pytest.fixture
def world(monkeypatch, tmp_path):
    bases = tmp_path / "kbs"
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("KB_BASES_DIR", str(bases))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("KB", "KB_ROOT", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "nokey"))
    monkeypatch.setattr(llm, "_which", lambda n: None)
    monkeypatch.setattr(import_kb, "_clone", lambda *a: pytest.fail("no network in tests"))
    return bases


@pytest.fixture
def client(world):
    with TestClient(create_app()) as c:
        yield c


def make_zip(pages=None, top="notes"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in (pages or {"alpha.md": PAGE, "beta.md": BETA}).items():
            z.writestr(f"{top}/{name}" if top else name, text)
    return buf.getvalue()


def upload(client, path, data, name="my-notes.zip", **fields):
    return client.post(path, files={"file": (name, data, "application/zip")}, data=fields, headers=ORIGIN)


@pytest.fixture
def tmpdir_of_its_own(tmp_path, monkeypatch):
    own = tmp_path / "tmp"
    own.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(own))
    return own


def test_validate_zip_previews_without_writing(client, world, tmpdir_of_its_own):
    r = upload(client, "/api/kb/import/validate", make_zip())
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["id"], j["name"], j["pages"], j["ok"]) == ("my-notes", "My notes", 2, True)
    assert j["errors"] == [] and j["source"] == "my-notes.zip"
    assert not world.exists() or not os.listdir(world)
    assert os.listdir(tmpdir_of_its_own) == []                              # temp dirs are removed


def test_validate_reports_errors_and_taken_id(client, world):
    j = upload(client, "/api/kb/import/validate", make_zip({"alpha.md": BAD})).json()
    assert j["ok"] is False and j["pages"] == 1 and any("missing" in e for e in j["errors"])
    assert upload(client, "/api/kb/import", make_zip({"alpha.md": BAD})).status_code == 422
    assert not world.exists() or not os.listdir(world)                      # nothing written on failure
    upload(client, "/api/kb/import", make_zip(), id="taken")
    j = upload(client, "/api/kb/import/validate", make_zip(), id="taken").json()
    assert j["ok"] is False and "already exists" in " ".join(j["errors"])


def test_import_zip_creates_the_kb(client, world):
    r = upload(client, "/api/kb/import", make_zip(), id="fresh")
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["id"], j["pages"], j["root"]) == ("fresh", 2, str(world.resolve() / "fresh"))
    cfg = kbconfig.load_dir(j["root"], "fresh")
    assert cfg.id == "fresh"
    assert os.path.isfile(os.path.join(j["root"], "wiki", "alpha.md"))
    with open(os.path.join(j["root"], "kb.toml"), encoding="utf-8") as f:
        assert 'source = "my-notes.zip"' in f.read()                         # the upload's name, not its temp path


def test_default_id_comes_from_the_file_name(client, world):
    assert upload(client, "/api/kb/import", make_zip(), name="Reading List.zip").json()["id"] == "reading-list"


def test_import_git_url_with_mocked_clone(client, world, monkeypatch):
    seen = {}

    def fake_clone(url, ref, dest):
        seen.update(url=url, ref=ref)
        os.makedirs(dest)
        for name, text in {"alpha.md": PAGE, "beta.md": BETA}.items():
            with open(os.path.join(dest, name), "w", encoding="utf-8") as f:
                f.write(text)
        return "abc123"

    monkeypatch.setattr(import_kb, "_clone", fake_clone)
    r = client.post("/api/kb/import/validate", json={"git_url": "https://example.com/me/notes.git#v1"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["ref"], r.json()["commit"], r.json()["pages"]) == ("notes", "v1", "abc123", 2)
    r = client.post("/api/kb/import", json={"git_url": "https://example.com/me/notes.git", "id": "from-git"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "from-git" and seen["url"] == "https://example.com/me/notes.git"


@pytest.mark.parametrize("url", ["/etc", "file:///tmp/x", "--upload-pack=x", "", "notes"])
def test_git_url_must_be_remote(client, url):
    r = client.post("/api/kb/import/validate", json={"git_url": url}, headers=ORIGIN)
    assert r.status_code == 422 and "git URL" in r.json()["detail"]


def test_clone_failure_is_422(client, monkeypatch):
    def boom(url, ref, dest):
        raise import_kb.BundleError(f"could not clone {url}: nope")

    monkeypatch.setattr(import_kb, "_clone", boom)
    r = client.post("/api/kb/import", json={"git_url": "https://example.com/x.git"}, headers=ORIGIN)
    assert r.status_code == 422 and "could not clone" in r.json()["detail"]


def test_bad_bodies(client):
    assert upload(client, "/api/kb/import/validate", b"not a zip").status_code == 422
    assert client.post("/api/kb/import/validate", json={"nope": 1}, headers=ORIGIN).status_code == 422
    assert client.post("/api/kb/import/validate", content=b"x", headers={**ORIGIN, "Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/kb/import/validate", files={"id": (None, "x")}, headers=ORIGIN).status_code == 422
    assert client.post("/api/kb/import/validate", json={"git_url": "https://example.com/x.git"}).status_code == 403   # no Origin


def test_unsafe_zip_is_422(client, world):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("alpha.md", PAGE)
        z.writestr("../escaped.md", PAGE)
    r = upload(client, "/api/kb/import", buf.getvalue())
    assert r.status_code == 422 and "unsafe" in r.json()["detail"]


def test_upload_cap_is_larger_only_on_the_import_routes(client):
    big = b"x" * (security.MAX_BODY_BYTES + 1024)
    assert upload(client, "/api/kb/import/validate", big).status_code == 422          # reached the handler: not a zip
    r = client.post("/api/kb/list", content=big, headers={**ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_odd_json_types_are_422_not_500(client):
    for body in ({"git_url": 5}, {"git_url": ["x"]}, {"git_url": "https://example.com/x.git", "id": 3}):
        assert client.post("/api/kb/import/validate", json=body, headers=ORIGIN).status_code == 422


def test_zip_bomb_and_control_chars(client, world):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(import_kb.MAX_ENTRIES + 1):
            z.writestr(f"{i}.md", "")
    assert upload(client, "/api/kb/import/validate", buf.getvalue()).status_code == 422
    r = upload(client, "/api/kb/import", make_zip(), name="bad\x01name.zip", id="ctl")
    assert r.status_code == 200
    assert kbconfig.load_dir(r.json()["root"], "ctl").id == "ctl"                  # kb.toml still parses


def test_credentials_in_a_git_url_are_not_recorded(client, world, monkeypatch):
    def fake_clone(url, ref, dest):
        os.makedirs(dest)
        with open(os.path.join(dest, "a.md"), "w", encoding="utf-8") as f:
            f.write(PAGE.replace("[beta](beta.md)", "nothing"))
        return "c0ffee"

    monkeypatch.setattr(import_kb, "_clone", fake_clone)
    j = client.post("/api/kb/import/validate", json={"git_url": "https://token@example.com/me/n.git"}, headers=ORIGIN).json()
    assert "token" not in j["source"]


# --- the knowledge library: a local folder of bundles ---

@pytest.fixture
def library(world, tmp_path):
    lib = tmp_path / "lib"
    (lib / "notes" / "wiki").mkdir(parents=True)
    (lib / "notes" / "wiki" / "alpha.md").write_text(PAGE)
    (lib / "notes" / "wiki" / "beta.md").write_text(BETA)
    (lib / "empty").mkdir()
    (lib / ".hidden").mkdir()
    (lib / ".hidden" / "x.md").write_text(PAGE)
    (lib / "zipped.zip").write_bytes(make_zip())
    (lib / "junk.zip").write_bytes(b"not a zip")
    return lib


def test_library_unset_is_empty(client):
    assert client.get("/api/kb/library").json() == {"path": None, "bundles": []}


def test_library_set_scan_clear(client, library):
    r = client.put("/api/kb/library", json={"path": str(library)}, headers=ORIGIN)
    assert r.status_code == 200
    body = client.get("/api/kb/library").json()
    assert body["path"] == os.path.realpath(library)
    assert [(b["name"], b["kind"]) for b in body["bundles"]] == [("notes", "folder"), ("zipped", "zip")]
    assert not any(b["added"] for b in body["bundles"])
    assert client.put("/api/kb/library", json={"path": None}, headers=ORIGIN).json() == {"path": None, "bundles": []}


def test_library_rejects_a_missing_or_relative_folder(client, library):
    assert client.put("/api/kb/library", json={"path": str(library / "nope")}, headers=ORIGIN).status_code == 422
    assert client.put("/api/kb/library", json={"path": "relative/dir"}, headers=ORIGIN).status_code == 422


def test_import_from_a_library_path_and_added_flag(client, library, world):
    client.put("/api/kb/library", json={"path": str(library)}, headers=ORIGIN)
    src = str(library / "notes")
    r = client.post("/api/kb/import/validate", json={"path": src}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["pages"] == 2 and r.json()["ok"]
    r = client.post("/api/kb/import", json={"path": src, "id": "from-lib"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["id"] == "from-lib"
    added = {b["name"]: b["added"] for b in client.get("/api/kb/library").json()["bundles"]}
    assert added == {"notes": True, "zipped": False}


def test_import_path_outside_the_library_is_422(client, library, tmp_path):
    outside = tmp_path / "outside"
    (outside / "wiki").mkdir(parents=True)
    (outside / "wiki" / "alpha.md").write_text(PAGE)
    for body in ({"path": str(outside)}, {"path": str(library / ".." / "outside")}):
        assert client.post("/api/kb/import/validate", json=body, headers=ORIGIN).status_code == 422
    client.put("/api/kb/library", json={"path": str(library)}, headers=ORIGIN)
    assert client.post("/api/kb/import/validate", json={"path": str(outside)}, headers=ORIGIN).status_code == 422


def test_import_path_without_a_library_is_422(client, library):
    assert client.post("/api/kb/import/validate", json={"path": str(library / "notes")}, headers=ORIGIN).status_code == 422

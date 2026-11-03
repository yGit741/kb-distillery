"""Chat attachments: upload limits, traversal, per-session read scope, PDF text, flag off. No network, no LLM."""
import io
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import paths
from kb_distillery.server.app import create_app
from kb_distillery.services import chat_agent, chat_attachments as svc

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


def make_pdf(text="Hello attachment"):
    """A one-page PDF with a text layer, built by hand (no fixture file, no renderer)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    objs += [f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CACHE_PATH", str(tmp_path / ".cache"))
    return tmp_path


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def up(client, name, data, session="s1"):
    return client.post("/api/chat/attachments", data={"session": session}, files={"file": (name, data)},
                       headers=LOOPBACK)


@pytest.mark.flag("agent-mode", False)
def test_flag_off_is_disabled(client):
    assert up(client, "a.md", b"x").status_code == 404
    assert client.get("/api/chat/attachments/s1").status_code == 404
    assert client.delete("/api/chat/attachments/s1/abcdef012345", headers=LOOPBACK).status_code == 404


@pytest.mark.flag("agent-mode", True)
def test_upload_list_delete(client, cache):
    r = up(client, "../../My Notes.md", b"# hi")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "text" and body["bytes"] == 4 and body["name"] == "My-Notes.md"
    stored = cache / ".cache" / "chat" / "s1" / "attachments"
    assert [p.name for p in stored.iterdir()] == [f"{body['id']}__My-Notes.md"]
    assert [a["id"] for a in client.get("/api/chat/attachments/s1").json()["attachments"]] == [body["id"]]
    assert client.delete(f"/api/chat/attachments/s1/{body['id']}", headers=LOOPBACK).json() == {"attachments": []}
    assert client.delete(f"/api/chat/attachments/s1/{body['id']}", headers=LOOPBACK).status_code == 404


@pytest.mark.flag("agent-mode", True)
def test_limits(client, monkeypatch):
    assert up(client, "run.exe", b"x").status_code == 415
    assert up(client, "noext", b"x").status_code == 415
    assert up(client, "a.md", b"").status_code == 400
    monkeypatch.setattr(svc, "MAX_BYTES", 10)
    assert up(client, "big.txt", b"x" * 11).status_code == 413
    assert not os.path.exists(os.path.join(svc.session_dir("s1"))) or not os.listdir(svc.session_dir("s1"))
    monkeypatch.setattr(svc, "MAX_BYTES", 20 * 1024 * 1024)
    for i in range(svc.MAX_FILES):
        assert up(client, f"f{i}.txt", b"x").status_code == 200
    assert up(client, "one-more.txt", b"x").status_code == 409
    assert up(client, "other.txt", b"x", session="s2").status_code == 200      # the limit is per session


@pytest.mark.flag("agent-mode", True)
def test_body_cap_allows_uploads_but_not_other_routes(client):
    big = b"x" * (5 * 1024 * 1024)
    assert up(client, "five.txt", big).status_code == 200
    assert client.post("/api/chat", content=big, headers={**LOOPBACK, "Content-Type": "application/json"}).status_code == 413


@pytest.mark.flag("agent-mode", True)
@pytest.mark.parametrize("bad", ["../x", "a/b", "..", "a b", "", "x" * 65, "a\\b", "%2e%2e"])
def test_bad_session_ids(client, bad):
    r = up(client, "a.md", b"x", session=bad)
    assert r.status_code in (400, 422)
    assert not os.path.exists(paths.CACHE_PATH)
    assert client.get(f"/api/chat/attachments/{bad}").status_code in (400, 404, 405, 422)


@pytest.mark.flag("agent-mode", True)
def test_bad_attachment_id_on_delete(client):
    assert client.delete("/api/chat/attachments/s1/..%2f..", headers=LOOPBACK).status_code in (400, 404)
    assert client.delete("/api/chat/attachments/s1/not-an-id", headers=LOOPBACK).status_code == 400


@pytest.mark.flag("agent-mode", True)
def test_pdf_text_extracted_once(client, cache):
    r = up(client, "paper.pdf", make_pdf("Hello attachment"))
    assert r.status_code == 200 and r.json()["kind"] == "pdf"
    (entry,) = svc.resolve("s1", [r.json()["id"]])
    assert "Hello attachment" in open(entry["text_path"], encoding="utf-8").read()
    assert svc.prompt_note([entry]).endswith(f"paper.pdf: {entry['text_path']}")
    assert [a["name"] for a in svc.listing("s1")] == ["paper.pdf"]          # the .txt is not a second attachment
    client.delete(f"/api/chat/attachments/s1/{r.json()['id']}", headers=LOOPBACK)
    assert not os.path.exists(entry["text_path"])


@pytest.mark.flag("agent-mode", True)
def test_fake_pdf_rejected(client):
    assert up(client, "x.pdf", b"not a pdf").status_code == 400
    assert svc.listing("s1") == []


@pytest.mark.flag("agent-mode", True)
def test_images_become_image_blocks(client):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    r = up(client, "pic.PNG", png)
    assert r.json()["kind"] == "image"
    entries = svc.resolve("s1", [r.json()["id"], "ffffffffffff"])           # unknown ids are skipped
    assert len(entries) == 1
    from kb_distillery.llm import agent
    import asyncio

    async def first(gen):
        return [m async for m in gen]
    (msg,) = asyncio.run(first(agent._prompt_input("what is this", svc.image_paths(entries))))
    blocks = msg["message"]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[-1] == {"type": "text", "text": "what is this"}
    assert agent._prompt_input("q", ()) == "q"


# ── per-session read scope ──
@pytest.fixture
def two_sessions(client):
    ids = {}
    for s in ("mine", "other"):
        up(client, "n.md", f"secret of {s}".encode(), session=s)
        ids[s] = svc.listing(s)[0]["path"]
    token = chat_agent.ATTACH_DIR.set(svc.session_dir("mine"))
    yield ids
    chat_agent.ATTACH_DIR.reset(token)


@pytest.mark.flag("agent-mode", True)
def test_read_scope_is_the_current_session(two_sessions):
    pol = chat_agent.tool_policy
    assert pol("Read", {"file_path": two_sessions["mine"]}).allow
    assert not pol("Read", {"file_path": two_sessions["other"]}).allow
    mine_dir = svc.session_dir("mine")
    assert pol("Glob", {"path": mine_dir, "pattern": "*"}).allow
    assert pol("Grep", {"path": mine_dir, "pattern": "secret"}).allow
    assert not pol("Grep", {"path": svc.session_dir("other"), "pattern": "secret"}).allow
    assert not pol("Glob", {"path": svc.chat_root(), "pattern": "**/*"}).allow
    assert not pol("Glob", {"path": mine_dir, "pattern": "../../*/attachments/*"}).allow
    assert not pol("Grep", {"path": mine_dir, "pattern": "x", "glob": "/etc/*"}).allow
    assert not pol("Read", {"file_path": mine_dir + "/../../other/attachments/" + os.path.basename(two_sessions["other"])}).allow


@pytest.mark.flag("agent-mode", True)
def test_read_scope_rejects_symlinks(two_sessions, tmp_path):
    mine_dir = svc.session_dir("mine")
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    os.symlink(outside, os.path.join(mine_dir, "link.txt"))
    os.symlink(svc.session_dir("other"), os.path.join(mine_dir, "dirlink"))
    pol = chat_agent.tool_policy
    assert not pol("Read", {"file_path": os.path.join(mine_dir, "link.txt")}).allow
    assert not pol("Read", {"file_path": os.path.join(mine_dir, "dirlink", os.path.basename(two_sessions["other"]))}).allow
    # a symlink elsewhere pointing into the dir is not honoured either
    elsewhere = tmp_path / "via"
    os.symlink(mine_dir, elsewhere)
    assert not pol("Read", {"file_path": str(elsewhere / os.path.basename(two_sessions["mine"]))}).allow


@pytest.mark.flag("agent-mode", True)
def test_no_attachments_no_access(client):
    up(client, "n.md", b"x", session="other")
    p = svc.listing("other")[0]["path"]
    assert not chat_agent.tool_policy("Read", {"file_path": p}).allow       # ATTACH_DIR unset: no session


@pytest.mark.flag("agent-mode", False)
def test_flag_off_denies_attachment_reads(cache):
    d = svc.session_dir("mine")
    os.makedirs(d)
    p = os.path.join(d, "abcdef012345__n.md")
    open(p, "w").write("x")
    token = chat_agent.ATTACH_DIR.set(d)
    try:
        assert not chat_agent.tool_policy("Read", {"file_path": p}).allow
    finally:
        chat_agent.ATTACH_DIR.reset(token)


# ── chat wiring ──
def _post_chat(client, **extra):
    from unittest import mock
    from kb_distillery.services import chat as chat_data

    def stream(question, **kw):
        stream.kw = kw
        yield ("done", {})
    with mock.patch("kb_distillery.server.routers.chat.chat_agent.sdk_info", return_value={"available": True}), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.stream_agent", stream), \
         mock.patch("kb_distillery.server.routers.chat.chat_agent.build_agent_system", return_value="SYS"), \
         mock.patch.object(chat_data, "load_api_key", return_value=("sk-ant-api03-" + "x" * 30, "env")):
        r = client.post("/api/chat", json={"question": "hi", "backend": "agent", **extra}, headers=LOOPBACK)
    return r, getattr(stream, "kw", {})


@pytest.mark.flag("agent-mode", True)
def test_chat_resolves_attachment_ids_per_session(client):
    a = up(client, "a.md", b"x", session="mine").json()["id"]
    r, kw = _post_chat(client, attachments=[a, "ffffffffffff"], attachment_session="mine")
    assert r.status_code == 200 and [e["name"] for e in kw["attachments"]] == ["a.md"]
    assert kw["attachment_session"] == "mine"
    _, kw = _post_chat(client, attachment_session="mine")                       # turn 2: no new files, scope stays
    assert kw["attachment_session"] == "mine" and "attachments" not in kw
    _, kw = _post_chat(client, attachments=[a], attachment_session="other")      # another session's id resolves to nothing
    assert kw["attachments"] == []
    r, _ = _post_chat(client, attachments=[a], attachment_session="../x")
    assert r.status_code == 400


@pytest.mark.flag("agent-mode", False)
def test_chat_flag_off_ignores_attachments(client):
    _, kw = _post_chat(client, attachments=["abcdef012345"], attachment_session="mine")
    assert "attachments" not in kw

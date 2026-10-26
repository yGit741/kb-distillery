"""Think API against a temp vault (the real think/ is never written): list/read/save, the optimistic
lock, quick capture under a day heading, name safety and the Origin rule. No git: kb(think) sweeps
these files later (kb.ops.core), the service itself never commits."""
import datetime
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.api.models.think import ThinkList, ThinkNote, ThinkWriteResult
from kb.services import think as think_data

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}
NOW = datetime.datetime(2026, 10, 26, 14, 5)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "think").mkdir()
    (tmp_path / "think" / "thesis-decision.md").write_text("# Thesis\n\nstill open\n")
    (tmp_path / "think" / "experiment").mkdir()  # subfolders are not notes
    with mock.patch.object(think_data, "DEFAULT_ROOT", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def client(vault):
    return TestClient(create_app())


def test_list_and_get(client):
    data = ThinkList.model_validate(client.get("/api/think").json())
    assert [n.name for n in data.notes] == ["thesis-decision.md"]
    assert data.capture_note == "inbox.md"
    note = ThinkNote.model_validate(client.get("/api/think/thesis-decision.md").json())
    assert "still open" in note.text and note.mtime > 0
    assert client.get("/api/think/missing.md").status_code == 404


def test_save_create_and_conflict(client, vault):
    r = client.put("/api/think/new-idea.md", json={"text": "# hm\n"}, headers=LOOPBACK)
    res = ThinkWriteResult.model_validate(r.json())
    assert res.created and (vault / "think" / "new-idea.md").read_text() == "# hm\n"
    # save with a stale base_mtime → 409, file untouched
    stale = res.mtime - 10
    r = client.put("/api/think/new-idea.md", json={"text": "clobber", "base_mtime": stale}, headers=LOOPBACK)
    assert r.status_code == 409 and (vault / "think" / "new-idea.md").read_text() == "# hm\n"
    # save with the fresh mtime → ok
    r = client.put("/api/think/new-idea.md", json={"text": "# hm2\n", "base_mtime": res.mtime}, headers=LOOPBACK)
    assert not ThinkWriteResult.model_validate(r.json()).created


def test_create_only_refuses_existing(client, vault):
    r = client.put("/api/think/thesis-decision.md", json={"text": "", "create": True}, headers=LOOPBACK)
    assert r.status_code == 409 and "still open" in (vault / "think" / "thesis-decision.md").read_text()


def test_lock_rejects_older_mtime_too(vault):
    """A restore moves mtime backwards; the lock must catch both directions."""
    import os
    from kb.services import think as td
    p = vault / "think" / "thesis-decision.md"
    base = os.stat(p).st_mtime
    os.utime(p, (base - 100, base - 100))
    with pytest.raises(td.ThinkError) as e:
        td.save_note("thesis-decision.md", "x", base_mtime=base, root=str(vault))
    assert e.value.status == 409


def test_service_name_safety(vault):
    from kb.services import think as td
    for bad in ["../x.md", "a/b.md", ".h.md", "x.md\n", "a\nb.md", "x" * 200 + ".md", "no-ext"]:
        with pytest.raises(td.ThinkError) as e:
            td.save_note(bad, "x", root=str(vault))
        assert e.value.status == 400, bad


def test_name_safety(client):
    # "../" is normalised away before routing and falls to the legacy catch-all (501) — never our router
    for bad in ["../wiki/x.md", "a/b.md", ".hidden.md", "no-extension"]:
        assert client.put(f"/api/think/{bad}", json={"text": "x"}, headers=LOOPBACK).status_code in (400, 404, 501)


def test_capture_creates_and_appends(client, vault):
    with mock.patch.object(think_data.datetime, "datetime", mock.Mock(now=lambda: NOW)):
        client.post("/api/think/capture", json={"text": "first thought"}, headers=LOOPBACK)
        client.post("/api/think/capture", json={"text": "second\nwith detail"}, headers=LOOPBACK)
    text = (vault / "think" / "inbox.md").read_text()
    assert text.startswith("# Inbox")
    assert text.count("## 2026-10-26") == 1
    assert "- 14:05 — first thought" in text
    assert "- 14:05 — second\n  with detail" in text
    assert text.index("first thought") < text.index("second")
    assert client.post("/api/think/capture", json={"text": "  "}, headers=LOOPBACK).status_code == 400


def test_capture_respects_later_sections(vault):
    inbox = vault / "think" / "inbox.md"
    inbox.write_text("# Inbox\n\n## 2026-10-26\n\n- 09:00 — old\n\n## 2026-10-20\n\n- 08:00 — older\n")
    think_data.capture("new", root=str(vault), now=NOW)
    text = inbox.read_text()
    assert text.index("old") < text.index("- 14:05 — new") < text.index("older")


def test_mutations_need_loopback_origin(client):
    assert client.put("/api/think/x.md", json={"text": "x"}).status_code in (400, 403)
    assert client.post("/api/think/capture", json={"text": "x"}).status_code in (400, 403)

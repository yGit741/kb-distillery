"""/api/pages/{slug}/flags on a temp kb (tests/proposals/conftest.py); kb_distillery.llm.ask is patched, never called."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.server.app import create_app
from kb_distillery.server.models.page_flags import PageFlag, PageFlagCount, PageFlagFixReply, PageFlagList
from tests.proposals.conftest import kb, read, write  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _flag(client, text="The first claim is strong.", note="too strong", slug="alpha", **kw):
    r = client.post(f"/api/pages/{slug}/flags", json={"text": text, "note": note, "block_at": 1, **kw}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    return PageFlag.model_validate(r.json())


def _flags(client, slug="alpha"):
    return PageFlagList.model_validate(client.get(f"/api/pages/{slug}/flags").json()).flags


def _reply(edits, reply="Fixed."):
    return llm.Result(id="r0", text=json.dumps({"reply": reply, "edits": edits}), backend="subscription")


def test_create_list_count_delete(client, kb):  # noqa: F811
    a = _flag(client)
    b = _flag(client, text="More text here.", note="check the date")
    assert a.id != b.id and a.resolved_by is None and not a.orphaned and a.block_at == 1
    assert [f.id for f in _flags(client)] == [a.id, b.id]
    assert os.path.isfile(os.path.join(kb, ".local", "flags", "alpha.json"))
    assert PageFlagCount.model_validate(client.get("/api/pages/alpha/flags/count").json()).open == 2
    assert client.delete(f"/api/pages/alpha/flags/{a.id}", headers=LOOPBACK).status_code == 200
    assert [f.id for f in _flags(client)] == [b.id]
    assert client.delete(f"/api/pages/alpha/flags/{a.id}", headers=LOOPBACK).status_code == 404
    assert _flags(client, "beta") == []


def test_bad_requests(client, kb):  # noqa: F811
    assert client.post("/api/pages/alpha/flags", json={"text": "  "}, headers=LOOPBACK).status_code == 400
    assert client.post("/api/pages/alpha/flags", json={"text": "x" * 3000}, headers=LOOPBACK).status_code == 400
    assert client.post("/api/pages/nope/flags", json={"text": "x"}, headers=LOOPBACK).status_code == 404
    assert client.get("/api/pages/nope/flags").status_code == 404
    with mock.patch.object(llm, "ask") as ask:
        assert client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK).status_code == 400  # none open
        ask.assert_not_called()


def test_fix_makes_one_proposal_and_resolves_flags(client, kb):  # noqa: F811
    before = read(kb, "alpha")
    a = _flag(client, note="too strong")
    b = _flag(client, text="More text here.", note="outdated")
    edits = [{"before": "is strong.", "after": "may hold.", "reason": "too strong"},
             {"before": "More text here.", "after": "Less text here.", "reason": "outdated"}]
    with mock.patch.object(llm, "ask", return_value=_reply(edits)) as ask:
        r = client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    out = PageFlagFixReply.model_validate(r.json())
    assert out.proposal_id and out.hunks >= 1 and set(out.flag_ids) == {a.id, b.id} and out.skipped == []
    assert read(kb, "alpha") == before  # nothing written directly
    prompt = ask.call_args.args[0]
    assert ask.call_count == 1 and "too strong" in prompt and "outdated" in prompt and "UNTOUCHABLE" in prompt
    p = client.get(f"/api/proposals/{out.proposal_id}").json()
    assert p["producer"]["kind"] == "flags" and set(p["producer"]["context"]["flag_ids"]) == {a.id, b.id}
    new_text = p["revisions"][0]["ops"][0]["new_text"]
    assert "may hold." in new_text and "Less text here." in new_text and "Mine, keep me." in new_text
    assert [f.resolved_by for f in _flags(client)] == [out.proposal_id] * 2
    assert PageFlagCount.model_validate(client.get("/api/pages/alpha/flags/count").json()).open == 0
    assert client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK).status_code == 400  # nothing open now


def test_my_notes_never_edited_and_nothing_proposed_keeps_flags_open(client, kb):  # noqa: F811
    _flag(client)
    edits = [{"before": "Mine, keep me.", "after": "Gone.", "reason": ""}]
    with mock.patch.object(llm, "ask", return_value=_reply(edits)):
        out = PageFlagFixReply.model_validate(
            client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK).json())
    assert out.proposal_id is None and "My notes" in out.skipped[0].reason and out.flag_ids == []
    assert "Mine, keep me." in read(kb, "alpha")
    assert _flags(client)[0].resolved_by is None


def test_span_gone_from_the_page_is_orphaned(client, kb):  # noqa: F811
    gone = _flag(client, text="a sentence that was rewritten away")
    live = _flag(client)
    rows = {f.id: f for f in _flags(client)}
    assert rows[gone.id].orphaned and not rows[live.id].orphaned
    assert PageFlagCount.model_validate(client.get("/api/pages/alpha/flags/count").json()).orphaned == 1
    with mock.patch.object(llm, "ask", return_value=_reply(
            [{"before": "is strong.", "after": "may hold.", "reason": ""}])) as ask:
        out = PageFlagFixReply.model_validate(
            client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK).json())
    assert out.orphaned == [gone.id] and out.flag_ids == [live.id]
    assert "a sentence that was rewritten away" not in ask.call_args.args[0]
    assert {f.id: f.resolved_by for f in _flags(client)}[gone.id] is None


def test_only_orphans_open_is_a_400(client, kb):  # noqa: F811
    _flag(client, text="not on the page")
    with mock.patch.object(llm, "ask") as ask:
        r = client.post("/api/pages/alpha/flags/fix", json={}, headers=LOOPBACK)
        ask.assert_not_called()
    assert r.status_code == 400 and "orphaned" in r.json()["detail"]


def test_read_only_server_refuses_writes(client, kb, monkeypatch):  # noqa: F811
    monkeypatch.setenv("KB_READ_ONLY", "1")
    assert client.post("/api/pages/alpha/flags", json={"text": "x"}, headers=LOOPBACK).status_code == 405
    assert client.get("/api/pages/alpha/flags").status_code == 200


def test_rendered_text_counts_as_on_the_page(client, kb):  # noqa: F811
    f = _flag(client, text="A second paragraph links Beta.")  # the page holds [Beta](beta.md)
    assert not f.orphaned

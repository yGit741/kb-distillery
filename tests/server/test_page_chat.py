"""/api/pages/{slug}/chat on a temp kb (tests/proposals/conftest.py); kb_distillery.llm.ask is patched, never called."""
import json
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery import llm
from kb_distillery.server.app import create_app
from kb_distillery.server.models.page_chat import MentionList, PageChatReply, PageChatThread
from tests.proposals.conftest import kb, read  # noqa: F401  (the fixture)

LOOPBACK = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(kb):  # noqa: F811
    with TestClient(create_app()) as c:
        yield c


def _reply(edits, reply="Softened."):
    return llm.Result(id="r0", text=json.dumps({"reply": reply, "edits": edits}), backend="subscription")


def _post(client, edits, **body):
    payload = {"message": "soften this, check against @beta", "mentions": ["beta"],
               "selections": [{"block_at": 1, "text": "The first claim is strong."}], **body}
    with mock.patch.object(llm, "ask", return_value=_reply(edits)) as ask:
        r = client.post("/api/pages/alpha/chat", json=payload, headers=LOOPBACK)
    assert r.status_code == 200, r.text
    return PageChatReply.model_validate(r.json()), ask


def test_happy_path_makes_a_proposal_not_a_write(client, kb):  # noqa: F811
    before = read(kb, "alpha")
    out, ask = _post(client, [{"before": "is strong.", "after": "may hold.", "reason": "too strong",
                               "sources": ["beta"]}])
    assert out.proposal_id and out.hunks == 1 and out.skipped == [] and out.reply == "Softened."
    assert read(kb, "alpha") == before                       # nothing written directly
    prompt = ask.call_args.args[0]
    assert "The first claim is strong." in prompt and "[page: beta]" in prompt and "UNTOUCHABLE" in prompt
    p = client.get(f"/api/proposals/{out.proposal_id}").json()
    assert p["producer"]["kind"] == "chat" and p["producer"]["context"]["mentions"] == ["beta"]
    assert "may hold." in p["revisions"][0]["ops"][0]["new_text"]
    t = PageChatThread.model_validate(client.get("/api/pages/alpha/chat").json())
    assert [m.role for m in t.messages] == ["user", "assistant"] and t.messages[1].proposal_id == out.proposal_id
    assert os.path.isfile(os.path.join(kb, ".local", "chat", "alpha.json"))


def test_before_not_found_is_skipped(client, kb):  # noqa: F811
    out, _ = _post(client, [{"before": "nowhere on the page", "after": "x", "reason": "", "sources": []},
                            {"before": "More text here.", "after": "Other text.", "reason": "", "sources": []}])
    assert out.hunks == 1 and [s.reason for s in out.skipped] == ["text not found on the page"]


def test_unknown_mention_is_listed_not_404(client, kb):  # noqa: F811
    out, ask = _post(client, [], mentions=["no-such-paper", "../wiki/beta", "beta"])
    assert out.unknown_mentions == ["no-such-paper", "../wiki/beta"] and out.proposal_id is None
    assert "[page: no-such-paper]" not in ask.call_args.args[0]


def test_my_notes_never_edited(client, kb):  # noqa: F811
    out, _ = _post(client, [{"before": "Mine, keep me.", "after": "Gone.", "reason": "", "sources": []}])
    assert out.proposal_id is None and "My notes" in out.skipped[0].reason
    assert "Mine, keep me." in read(kb, "alpha")


def test_unknown_page_and_mentions_picker(client, kb):  # noqa: F811
    with mock.patch.object(llm, "ask") as ask:
        assert client.post("/api/pages/nope/chat", json={"message": "hi"}, headers=LOOPBACK).status_code == 404
        ask.assert_not_called()
    hits = MentionList.model_validate(client.get("/api/pages/mentions?q=be").json()).pages
    assert hits[0].slug == "beta"
    assert {h.slug for h in MentionList.model_validate(client.get("/api/pages/mentions?q=").json()).pages} == \
        {"alpha", "beta", "gamma"}

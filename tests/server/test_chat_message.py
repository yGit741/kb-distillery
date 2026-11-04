"""POST /api/chat/message: queue a message into the live agent turn."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.chat_live import ChatMessageResult
from kb_distillery.services import chat_live

ORIGIN = {"Origin": "http://127.0.0.1:8765"}


class Live:
    def __init__(self):
        self.got = []

    def send(self, text):
        self.got.append(text)
        return True


@pytest.mark.flag("agent-mode", True)
def test_message_reaches_the_live_turn():
    live = Live()
    chat_live.register("sess", live)
    try:
        r = TestClient(create_app()).post("/api/chat/message", json={"session": "sess", "text": " more "}, headers=ORIGIN)
    finally:
        chat_live.unregister(live)
    assert r.status_code == 200 and ChatMessageResult(**r.json()).ok
    assert live.got == ["more"]


@pytest.mark.flag("agent-mode", True)
def test_no_live_turn_is_a_404_with_a_hint():
    r = TestClient(create_app()).post("/api/chat/message", json={"session": "none", "text": "hi"}, headers=ORIGIN)
    assert r.status_code == 404 and r.json()["error"] and r.json()["hint"]


@pytest.mark.flag("agent-mode", False)
def test_the_endpoint_is_dark_with_the_flag_off():
    live = Live()
    chat_live.register("sess", live)
    try:
        r = TestClient(create_app()).post("/api/chat/message", json={"session": "sess", "text": "hi"}, headers=ORIGIN)
    finally:
        chat_live.unregister(live)
    assert r.status_code == 404 and live.got == []

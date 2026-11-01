"""GET/PUT /api/flags: effective values, owner-token refusal, build flags refused, overrides persist."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.flags import FlagsSnapshot
from kb_distillery.services import flags as svc

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
TOKEN = "owner-secret"


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "flags.json"
    with mock.patch.object(svc, "OVERRIDES_PATH", path), \
         mock.patch.object(svc, "keychain_token", lambda: TOKEN), \
         mock.patch.object(svc, "create_keychain_token", lambda: True):
        yield TestClient(create_app()), path


def by_name(body):
    return {f["name"]: f for f in body["flags"]}


def test_get_lists_registry_with_effective_values(client):
    c, _ = client
    r = c.get("/api/flags")
    assert r.status_code == 200
    body = FlagsSnapshot.model_validate(r.json()).model_dump()
    assert body["env"] == "local" and body["overrides"] == {}
    f = by_name(body)
    assert f["screen.lifecycle"]["value"] is True and f["screen.lifecycle"]["source"] == "registry"
    assert f["ui.system-flags-tab"]["kind"] == "runtime" and f["ui.system-flags-tab"]["value"] is False


def test_put_without_or_with_wrong_token_is_403(client):
    c, path = client
    assert c.put("/api/flags/ui.system-flags-tab", json={"value": True}, headers=ORIGIN).status_code == 403
    r = c.put("/api/flags/ui.system-flags-tab", json={"value": True}, headers={**ORIGIN, "X-KB-Owner-Token": "agent"})
    assert r.status_code == 403 and not path.exists()


def test_put_refuses_build_flags_and_unknown(client):
    c, _ = client
    h = {**ORIGIN, "X-KB-Owner-Token": TOKEN}
    assert c.put("/api/flags/screen.share", json={"value": True}, headers=h).status_code == 409
    assert c.put("/api/flags/nope.flag", json={"value": True}, headers=h).status_code == 404


def test_put_persists_and_clears(client):
    c, path = client
    h = {**ORIGIN, "X-KB-Owner-Token": TOKEN}
    r = c.put("/api/flags/ui.system-flags-tab", json={"value": True}, headers=h)
    assert r.status_code == 200 and r.json()["overrides"] == {"ui.system-flags-tab": True}
    assert json.loads(path.read_text())["ui.system-flags-tab"]["value"] is True
    f = by_name(c.get("/api/flags").json())["ui.system-flags-tab"]
    assert f["value"] is True and f["source"] == "override" and f["registry_value"] is False
    assert c.put("/api/flags/ui.system-flags-tab", json={"value": None}, headers=h).json()["overrides"] == {}


def test_put_needs_loopback_origin(client):
    c, _ = client
    r = c.put("/api/flags/ui.system-flags-tab", json={"value": True}, headers={"X-KB-Owner-Token": TOKEN})
    assert r.status_code == 403


def test_missing_keychain_item_is_created_and_refused(tmp_path):
    made = []
    with pytest.raises(svc.FlagRefused) as e:
        svc.check_owner("x", read=lambda: None, create=lambda: made.append(1) or True)
    assert e.value.status == 403 and made == [1] and "security find-generic-password" in str(e.value)

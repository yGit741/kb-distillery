"""GET /api/share/status — nothing deployed yet, and a deployed status with its chip."""
from unittest import mock

from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.share import ShareStatus


class FakeStatus:
    value = None

    def read(self):
        return self.value


def get(value):
    FakeStatus.value = value
    with TestClient(create_app()) as c, mock.patch("kb_distillery.publish.cloudflare.contracts.StatusFile", FakeStatus):
        return c.get("/api/share/status")


def test_no_deploy_yet():
    r = get(None)
    assert r.status_code == 200 and r.json() == {"status": None, "chip": None}
    ShareStatus.model_validate(r.json())


def test_deployed_has_chip_and_legacy_keys():
    status = {"state": "deployed", "sha": "a" * 40, "kb_version": "1.0.3", "at": "2026-10-24T00:00:00+00:00",
              "error": None, "url": "https://kb.example"}
    r = get(status)
    body = r.json()
    ShareStatus.model_validate(body)
    assert set(body) == {"status", "chip"} and body["status"] == status
    assert body["chip"]["cls"] == "is-deployed" and body["chip"]["href"] == "https://kb.example"

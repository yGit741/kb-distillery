"""GET /api/kb/inbox and POST /api/kb/inbox/pull with the site mocked: no network, no keychain, no ~/knowledge."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery import import_kb, inbox
from kb_distillery.server.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8765"}
ITEMS = [
    {"item": "20260102T030405Z-aaaaaaaa", "status": "pending", "kind": "zip", "at": "2026-01-02T03:04:05Z",
     "uploader": "me@example.com", "kb_id": "notes", "kit": None, "size": 10, "pages": 3, "warnings": 0},
    {"item": "20260101T030405Z-bbbbbbbb", "status": "imported", "kind": "git", "at": "2026-01-01T03:04:05Z",
     "uploader": "me@example.com", "kb_id": "old", "git_url": "https://example.com/old.git", "pages": 0, "warnings": 1},
    {"item": "20251231T030405Z-cccccccc", "status": "failed", "kind": "zip", "at": "2025-12-31T03:04:05Z",
     "uploader": "me@example.com", "kb_id": "bad", "error": "id taken"},
]


class FakeClient:
    reported = []

    def __init__(self, *a, **k):
        pass

    def items(self, status="pending"):
        return [i for i in ITEMS if status == "all" or i["status"] == status]

    def bundle(self, item):
        return b"zip"

    def report(self, item, **body):
        FakeClient.reported.append((item, body))


@pytest.fixture
def client(monkeypatch):
    for k in (inbox.ENV_URL, inbox.ENV_TOKEN):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(inbox, "keychain_token", lambda: pytest.fail("no keychain in tests"))
    FakeClient.reported = []
    with TestClient(create_app()) as c:
        yield c


def test_list_returns_every_status(client, monkeypatch):
    monkeypatch.setattr(inbox, "Client", FakeClient)
    j = client.get("/api/kb/inbox").json()
    assert j["configured"] is True and j["error"] == ""
    assert [i["status"] for i in j["items"]] == ["pending", "imported", "failed"]
    assert j["items"][0]["pages"] == 3 and j["items"][2]["error"] == "id taken"


def test_not_configured_is_a_hint_not_an_error(client, monkeypatch):
    monkeypatch.setattr(inbox, "site_url", lambda: (_ for _ in ()).throw(inbox.NotConfigured("no site to ask")))
    r = client.get("/api/kb/inbox")
    assert r.status_code == 200 and r.json()["configured"] is False and r.json()["items"] == []
    assert r.json()["guide"] == "" or r.json()["guide"].endswith("docs/guides/import-a-bundle.md#from-the-site-inbox")


def test_unreachable_site_is_reported_inline(client, monkeypatch):
    class Down(FakeClient):
        def items(self, status="pending"):
            raise inbox.InboxError("cannot reach https://x")

    monkeypatch.setattr(inbox, "Client", Down)
    j = client.get("/api/kb/inbox").json()
    assert j["configured"] is True and j["error"] == "cannot reach https://x" and j["items"] == []


def test_pull_imports_pending_and_reports_back(client, monkeypatch):
    monkeypatch.setattr(inbox, "Client", FakeClient)
    monkeypatch.setattr(import_kb, "import_bundle", lambda source, **kw: "/bases/notes")
    r = client.post("/api/kb/inbox/pull", headers=ORIGIN)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["imported"] == [{"item": "20260102T030405Z-aaaaaaaa", "kb_id": "notes", "error": ""}]
    assert j["failed"] == [] and j["unreported"] == []
    assert FakeClient.reported == [("20260102T030405Z-aaaaaaaa", {"status": "imported", "kb_id": "notes"})]


def test_pull_failure_is_listed(client, monkeypatch):
    monkeypatch.setattr(inbox, "Client", FakeClient)

    def boom(source, **kw):
        raise import_kb.BundleError("not valid")

    monkeypatch.setattr(import_kb, "import_bundle", boom)
    j = client.post("/api/kb/inbox/pull", headers=ORIGIN).json()
    assert j["imported"] == [] and j["failed"][0]["error"] == "not valid"


def test_pull_needs_set_up_and_a_loopback_origin(client, monkeypatch):
    assert client.post("/api/kb/inbox/pull", headers=ORIGIN).status_code == 409        # no site/token in the env
    assert client.post("/api/kb/inbox/pull").status_code == 403

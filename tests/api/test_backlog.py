"""GET /api/backlog validates against its model, empty and with items."""
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.backlog import BacklogList
from kb_distillery.services import backlog as bl


def test_empty_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_BACKLOG_DIR", str(tmp_path / "none"))
    r = TestClient(create_app()).get("/api/backlog")
    assert r.status_code == 200 and BacklogList.model_validate(r.json()).items == []


def test_items_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_BACKLOG_DIR", str(tmp_path))
    bl.add_item("Try a calmer graph legend", why="less noise", area="graph", size="s")
    r = TestClient(create_app()).get("/api/backlog")
    body = BacklogList.model_validate(r.json())
    assert [(i.title, i.status, i.plan_status, i.drift.level) for i in body.items] == \
        [("Try a calmer graph legend", "inbox", "no-plan", "none")]

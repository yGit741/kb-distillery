"""GET /api/ops — canned snapshot; the refresh flag reaches the service; a failure is 500 {"error"}."""
from unittest import mock

from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.api.models.ops import OpsSnapshot

CANNED = {"subject": "nightly", "doc": {"blocks": []}, "runs": [{"at": "t"}], "legacy_extra": 1,
          "queue": {"holder": None, "waiters": [], "stale_after": 1200}}


def test_ops_model_and_refresh_flag():
    with TestClient(create_app()) as c, \
         mock.patch("kb.services.ops.build_ops_snapshot", return_value=CANNED) as svc:
        r = c.get("/api/ops")
        assert r.status_code == 200 and r.json() == CANNED
        OpsSnapshot.model_validate(r.json())
        svc.assert_called_with(refresh=False)
        c.get("/api/ops?refresh=1")
        svc.assert_called_with(refresh=True)


def test_ops_failure_shape():
    with TestClient(create_app()) as c, \
         mock.patch("kb.services.ops.build_ops_snapshot", side_effect=RuntimeError("boom")):
        r = c.get("/api/ops")
    assert r.status_code == 500 and r.json() == {"error": "RuntimeError: boom"}


def test_ops_snapshot_carries_live_queue(tmp_path, monkeypatch):
    """The queue is read fresh on every call (outside the 60 s cache) from the git common dir."""
    import json, os, socket, subprocess, time
    from kb.services import ops
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    now = time.time()
    rows = [{"pr": 7, "branch": "infra/a", "pid": os.getpid(), "host": socket.gethostname(), "ts": now - 30, "hb": now - 30},
            {"pr": 8, "branch": "infra/b", "pid": 2 ** 22 + 12345, "host": socket.gethostname(), "ts": now, "hb": now}]
    (tmp_path / ".git" / "kb-merge-queue.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(ops, "vault_root", lambda: str(tmp_path))
    monkeypatch.setitem(ops._cache, "data", {"subject": "s", "doc": {}})
    monkeypatch.setitem(ops._cache, "at", time.monotonic())
    with TestClient(create_app()) as c:
        q = c.get("/api/ops").json()["queue"]
    assert q["holder"]["pr"] == 7 and q["holder"]["alive"] is True and not q["holder"]["stale"]
    assert 29 <= q["holder"]["age"] <= 40
    assert [w["pr"] for w in q["waiters"]] == [8] and q["waiters"][0]["alive"] is False and q["waiters"][0]["stale"]
    (tmp_path / ".git" / "kb-merge-queue.jsonl").write_text("")
    assert ops.build_ops_snapshot()["queue"] == {"holder": None, "waiters": [], "stale_after": 1200}

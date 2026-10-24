"""GET /api/ops — canned snapshot; the refresh flag reaches the service; a failure is 500 {"error"}."""
from unittest import mock

from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.api.models.ops import OpsSnapshot

CANNED = {"subject": "nightly", "doc": {"blocks": []}, "runs": [{"at": "t"}], "legacy_extra": 1}


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

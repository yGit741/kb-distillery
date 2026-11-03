"""GET /api/ops — canned snapshot; the refresh flag reaches the service; a failure is 500 {"error"}."""
from unittest import mock

from fastapi.testclient import TestClient

from kb_distillery.server.app import create_app
from kb_distillery.server.models.ops import OpsSnapshot

CANNED = {"subject": "nightly", "doc": {"blocks": []}, "runs": [{"at": "t"}], "legacy_extra": 1,
          "queue": {"holder": None, "waiters": [], "stale_after": 1200}, "deploy": None, "maintainer": True}


def test_ops_model_and_refresh_flag():
    with TestClient(create_app()) as c, \
         mock.patch("kb_distillery.services.ops.build_ops_snapshot", return_value=CANNED) as svc:
        r = c.get("/api/ops")
        assert r.status_code == 200 and r.json() == CANNED
        OpsSnapshot.model_validate(r.json())
        svc.assert_called_with(refresh=False)
        c.get("/api/ops?refresh=1")
        svc.assert_called_with(refresh=True)


def test_ops_failure_shape():
    with TestClient(create_app()) as c, \
         mock.patch("kb_distillery.services.ops.build_ops_snapshot", side_effect=RuntimeError("boom")):
        r = c.get("/api/ops")
    assert r.status_code == 500 and r.json() == {"error": "RuntimeError: boom"}


def test_ops_snapshot_carries_live_queue(tmp_path, monkeypatch):
    """The queue is read fresh on every call (outside the 60 s cache) from the git common dir."""
    import json, os, socket, subprocess, time
    from kb_distillery.services import ops
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


def _owner_fixture(root, shas, status, last_cycle):
    import json
    cache = root / ".cache" / "share"
    cache.mkdir(parents=True)
    (cache / "owner.json").write_text(json.dumps({"shas": shas, "last_cycle_at": last_cycle, "rollbacks": 1}))
    (cache / "status.json").write_text(json.dumps(status))


def test_deploy_state_from_owner_fixture(tmp_path):
    """live / main / last outcome / queued / rollbacks / owner liveness, all from fixture files."""
    import datetime
    from kb_distillery.services import ops
    now = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    iso = lambda m: datetime.datetime.fromtimestamp(now - m * 60, datetime.timezone.utc).isoformat()
    _owner_fixture(tmp_path, {
        "a" * 40: {"state": "deployed", "at": iso(120)},
        "b" * 40: {"state": "rolled-back", "at": iso(60), "error": "unhealthy: /api/health 500"},
        "c" * 40: {"state": "building", "at": iso(1), "cycles": 1},
        "d" * 40: {"state": "rolled-back", "at": iso(60 * 24 * 9)},  # older than 7 days
    }, {"state": "failed", "sha": "b" * 40, "at": iso(60)}, iso(2))
    plist = tmp_path / "owner.plist"
    plist.write_text("x")
    d = ops.deploy_state(str(tmp_path), now=now, plist=str(plist), main=("c" * 40, now - 45 * 60))
    from kb_distillery.server.models.ops import DeployState
    DeployState.model_validate(d)
    assert d["live_sha"] == "a" * 40 and d["main_sha"] == "c" * 40
    assert d["behind"] is True and d["behind_minutes"] == 45
    assert d["deploying"] == "c" * 40 and d["queued"] == ["c" * 40]
    assert d["last_outcome"] == "rolled-back" and d["last_reason"] == "unhealthy: /api/health 500"
    assert d["rollbacks_7d"] == 1
    assert d["owner_installed"] is True and d["owner_alive"] is True and d["heartbeat_age"] == 60  # the in-flight step (1 min) is newer than the cycle start


def test_deploy_state_missing_is_unknown_not_ok(tmp_path):
    from kb_distillery.services import ops
    d = ops.deploy_state(str(tmp_path), plist=str(tmp_path / "none.plist"), main=(None, None))
    assert d["live_sha"] is None and d["behind"] is None and d["last_outcome"] is None
    assert d["owner_installed"] is False and d["owner_alive"] is False


def test_deploy_state_status_json_newer_direct_deploy(tmp_path):
    """A direct deploy (status.json only) newer than the owner's last deployed sha is what is live."""
    import datetime
    from kb_distillery.services import ops
    now = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    _owner_fixture(tmp_path, {"a" * 40: {"state": "deployed", "at": "2026-10-25T10:00:00+00:00"}},
                   {"state": "deployed", "sha": "e" * 40, "at": "2026-10-25T11:00:00+00:00"}, "2026-10-25T09:00:00+00:00")
    d = ops.deploy_state(str(tmp_path), now=now, plist=str(tmp_path / "none"), main=("e" * 40, now - 3600))
    assert d["live_sha"] == "e" * 40 and d["behind"] is False and d["behind_minutes"] == 0
    assert d["owner_alive"] is False  # last cycle 3 h ago


def test_deploy_state_stale_failed_network_is_not_queued(tmp_path):
    """A failed-network entry recorded before the live deploy is superseded, not queued."""
    import datetime
    from kb_distillery.services import ops
    now = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    iso = lambda m: datetime.datetime.fromtimestamp(now - m * 60, datetime.timezone.utc).isoformat()
    _owner_fixture(tmp_path, {
        "a" * 40: {"state": "deployed", "at": iso(10)},
        "b" * 40: {"state": "failed-network", "at": iso(30)},
        "c" * 40: {"state": "superseded", "at": iso(40)},
        "e" * 40: {"state": "failed-network", "at": iso(1)},
    }, {}, iso(1))
    d = ops.deploy_state(str(tmp_path), now=now, plist=str(tmp_path / "none"), main=("e" * 40, now))
    assert d["queued"] == ["e" * 40]


def test_maintainer_ops_is_false_for_a_fresh_kb_and_true_once_it_opted_in(tmp_path, monkeypatch):
    """A new kb has no nightly, deploy owner or publisher: the System screen leaves those tiles out."""
    from kb_distillery import publish
    from kb_distillery.ops import core
    from kb_distillery.services import ops
    monkeypatch.setattr(core, "NIGHTLY_PLIST", str(tmp_path / "none.plist"))
    monkeypatch.setattr(ops, "OWNER_PLIST", str(tmp_path / "none-owner.plist"))
    monkeypatch.setattr(publish, "current", lambda *a, **k: publish.NullPublisher(str(tmp_path), reason="none"))
    assert ops.maintainer_ops(str(tmp_path)) is False
    (tmp_path / "meta" / "ops").mkdir(parents=True)
    (tmp_path / "meta" / "ops" / "sync.toml").write_text("")
    assert ops.maintainer_ops(str(tmp_path)) is True
    (tmp_path / "meta" / "ops" / "sync.toml").unlink()
    monkeypatch.setattr(publish, "current", lambda *a, **k: object())
    assert ops.maintainer_ops(str(tmp_path)) is True


def test_deploy_state_default_root_is_the_engine_not_the_kb(tmp_path, monkeypatch):
    """The owner runs from the engine with no KB: the tile must read the engine's .cache/share even when the app
    serves a kb elsewhere (vault_root() points at the kb), or it reports 'owner not running'."""
    import datetime
    from kb_distillery.publish.cloudflare import contracts, owner
    from kb_distillery.services import ops
    engine, kb = tmp_path / "engine", tmp_path / "kb"
    engine.mkdir()
    kb.mkdir()
    monkeypatch.delenv("KB_SHARE_OWNER_STATUS", raising=False)
    monkeypatch.setattr(contracts, "REPO", engine)
    monkeypatch.setattr(owner, "primary_root", lambda r: r)
    monkeypatch.setattr(ops, "vault_root", lambda: str(kb))
    now = datetime.datetime(2026, 11, 3, 17, 0, tzinfo=datetime.timezone.utc)
    _owner_fixture(engine, {}, {}, (now - datetime.timedelta(minutes=2)).isoformat())
    d = ops.deploy_state(now=now.timestamp(), plist=str(tmp_path / "none"), main=(None, None))
    assert d["owner_alive"] is True and d["heartbeat_age"] == 120

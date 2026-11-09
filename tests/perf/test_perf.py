"""The perf bench's server half against the fixture kb: report shape only, no browser."""
import json

from kb_distillery.perf.__main__ import ENDPOINTS, TOP_KEYS, main, table


def test_report_shape(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--no-browser", "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert tuple(sorted(rep)) == tuple(sorted(TOP_KEYS))
    assert sorted(rep["server_ms"]) == sorted(ENDPOINTS)
    for r in rep["server_ms"].values():
        assert set(r) == {"cold_ms", "warm_ms", "bytes", "status"}
        assert r["cold_ms"] >= 0 and r["warm_ms"] >= 0
    for ep, r in rep["server_ms"].items():
        if ep != "/app":                      # /app is 404 where the web build is absent
            assert r["status"] == 200, ep
    assert isinstance(rep["pages"], int)
    assert rep["browser_ms"] == {"skipped": "--no-browser"}
    assert {"load_avg", "listeners_before", "mode"} <= set(rep["env"])
    assert "/api/graph" in table(rep)


def test_idle_adds_reopen(tmp_path):
    out = tmp_path / "r.json"
    assert main(["--no-browser", "--idle", "1", "--out", str(out)]) == 0
    assert all("reopen_ms" in r for r in json.loads(out.read_text())["server_ms"].values())

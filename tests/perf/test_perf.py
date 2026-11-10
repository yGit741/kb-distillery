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


def test_table_marks_skipped_tabs():
    row = {"ms": 120, "api_requests": 3, "timed_out": False}
    skip = {"ms": None, "api_requests": 0, "timed_out": False, "skipped": "not in the nav for this flag set"}
    rep = {"kb": "k", "pages": 1, "env": {"load_avg": [0, 0, 0]}, "server_ms": {},
           "browser_ms": {"initial": {"ms": 5, "api_requests": 0, "timed_out": False}, "tabs": ["/app/graph", "/app/think"],
                          "pass1": {"/app/graph": row, "/app/think": skip}, "pass2": {"/app/graph": row, "/app/think": skip}}}
    lines = table(rep).splitlines()
    assert any(line.startswith("/app/think") and line.split()[1] == "skipped" and "FAIL" not in line for line in lines)
    assert any(line.startswith("/app/graph") and "120" in line for line in lines)

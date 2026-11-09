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
    assert rep["server_ms"]["/api/health"]["status"] == 200
    assert rep["browser_ms"] == {"skipped": "--no-browser"}
    assert {"load_avg", "listeners_before", "mode"} <= set(rep["env"])
    assert "/api/graph" in table(rep)

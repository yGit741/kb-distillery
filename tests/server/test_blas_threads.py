"""The server process caps BLAS at one thread before numpy loads (the warm thread's similar-to products must not
starve the event loop on a busy machine); a value the user set is kept."""
from unittest import mock

from kb_distillery.server import __main__ as server_main


def test_limit_blas_threads_sets_every_var_to_one():
    env = {}
    server_main.limit_blas_threads(env)
    assert env == {v: "1" for v in server_main.BLAS_THREAD_VARS}
    assert set(server_main.BLAS_THREAD_VARS) == {"OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"}


def test_limit_blas_threads_keeps_a_value_already_set():
    env = {"OPENBLAS_NUM_THREADS": "4"}
    server_main.limit_blas_threads(env)
    assert env["OPENBLAS_NUM_THREADS"] == "4"
    assert env["OMP_NUM_THREADS"] == "1"


def test_main_caps_blas_threads_before_serving(monkeypatch):
    import os

    import uvicorn

    from kb_distillery.graph import cache

    for var in server_main.BLAS_THREAD_VARS:
        monkeypatch.setenv(var, "unset-by-test")      # recorded, so the value main() sets is undone after the test
        monkeypatch.delenv(var)
    monkeypatch.setattr(cache, "start_refresher", lambda: None)
    seen = {}
    monkeypatch.setattr(uvicorn, "run", mock.Mock(side_effect=lambda *a, **k: seen.update(
        {v: os.environ.get(v) for v in server_main.BLAS_THREAD_VARS})))
    assert server_main.main(["--no-open", "--no-build"]) == 0
    assert seen == {v: "1" for v in server_main.BLAS_THREAD_VARS}

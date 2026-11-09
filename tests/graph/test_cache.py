"""The graph snapshot cache: a second call reuses the build, any change rebuilds, KB_GRAPH_CACHE=0 never caches."""
import os
import threading
import time

import pytest

from kb_distillery.graph import cache, snapshot


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv(cache.ENV, raising=False)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def counted(monkeypatch):
    calls = []
    real = snapshot.build_graph_snapshot

    def counting(*a, **k):
        calls.append(k)
        return real(*a, **k)

    monkeypatch.setattr(snapshot, "build_graph_snapshot", counting)
    return calls


def _a_page():
    root = snapshot.ROOT
    return next(os.path.join(root, r) for r, *_ in snapshot.load_pages(root).values())


def test_second_call_does_not_rebuild(counted):
    first = cache.cached_graph_snapshot()
    second = cache.cached_graph_snapshot()
    assert len(counted) == 1
    assert first == second and first is not second     # a copy: callers may add top-level keys


def test_editing_a_page_rebuilds(counted):
    cache.cached_graph_snapshot()
    path = _a_page()
    st = os.stat(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
    cache.cached_graph_snapshot()
    assert len(counted) == 2


def test_adding_and_deleting_a_page_rebuilds(counted):
    cache.cached_graph_snapshot()
    extra = os.path.join(snapshot.ROOT, "wiki", "zz-cache-probe.md")
    try:
        with open(extra, "w", encoding="utf-8") as f:
            f.write("---\ntype: concept\n---\n# Probe\n")
        cache.cached_graph_snapshot()
        assert len(counted) == 2
    finally:
        os.remove(extra)
    cache.cached_graph_snapshot()
    assert len(counted) == 3


def test_layers_are_cached_separately(counted):
    cache.cached_graph_snapshot()
    cache.cached_graph_snapshot(layer="raw")
    cache.cached_graph_snapshot(layer="raw")
    assert len(counted) == 2


def test_disabled_builds_every_time(counted, monkeypatch):
    monkeypatch.setenv(cache.ENV, "0")
    cache.cached_graph_snapshot()
    cache.cached_graph_snapshot()
    assert len(counted) == 2


def test_concurrent_callers_share_one_build(monkeypatch):
    calls = []
    real = snapshot.build_graph_snapshot

    def slow(*a, **k):
        calls.append(1)
        time.sleep(0.3)
        return real(*a, **k)

    monkeypatch.setattr(snapshot, "build_graph_snapshot", slow)
    ts = [threading.Thread(target=cache.cached_graph_snapshot) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(calls) == 1


def test_signature_is_cheap_and_stable():
    t = time.perf_counter()
    a = cache.signature(snapshot.ROOT)
    assert time.perf_counter() - t < 0.1
    assert a == cache.signature(snapshot.ROOT)

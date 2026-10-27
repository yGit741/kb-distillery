"""Card vector store: load, neighbours, similarity, and the guards (missing store, mixed models)."""
import sqlite3

import numpy as np
import pytest

from kb.search import vectors


def _db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE vectors (slug TEXT PRIMARY KEY, hash TEXT, model TEXT, dim INTEGER, vec BLOB, at TEXT)")
    for slug, model, vec in rows:
        v = np.asarray(vec, dtype=np.float32)
        con.execute("INSERT INTO vectors VALUES (?, 'h', ?, ?, ?, 't')", (slug, model, len(v), v.tobytes()))
    con.commit()
    con.close()
    return str(path)


def test_neighbours_and_similarity(tmp_path):
    db = _db(tmp_path / "v.sqlite", [("a", "m", [1, 0, 0]), ("b", "m", [0.9, 0.1, 0]), ("c", "m", [0, 0, 2])])
    v = vectors.load(db)
    assert len(v) == 3 and v.model == "m"
    assert [s for s, _ in v.neighbours("a", 2)] == ["b", "c"]
    assert v.similarity("a", "c") == pytest.approx(0.0) and v.similarity("a", "b") > 0.99
    assert v.neighbours("missing") == [] and v.similarity("a", "missing") is None


def test_missing_store_is_none(tmp_path):
    assert vectors.load(str(tmp_path / "nope.sqlite")) is None


def test_mixed_models_refuse(tmp_path):
    db = _db(tmp_path / "v.sqlite", [("a", "m1", [1, 0]), ("b", "m2", [0, 1])])
    with pytest.raises(ValueError, match="mixes models"):
        vectors.load(db)

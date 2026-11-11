"""Embedding report: status of the store, pages behind, near-duplicates, clusters by meaning and the 2D map."""
import sqlite3

import numpy as np

from kb_distillery.search import vectors
from kb_distillery.services import embedding as svc


def _store(tmp_path, rows, cards=None, model="m"):
    """A vector store and its cards folder; a row's hash matches its card unless the card text is given."""
    db, cards_dir = tmp_path / "vectors.sqlite", tmp_path / "qmd-cards"
    cards_dir.mkdir()
    texts = {slug: f"# Title of {slug}\n\nsummary\n" for slug, _ in rows}
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE vectors (slug TEXT PRIMARY KEY, hash TEXT, model TEXT, dim INTEGER, vec BLOB, at TEXT)")
    for slug, vec in rows:
        v = np.asarray(vec, dtype=np.float32)
        con.execute("INSERT INTO vectors VALUES (?, ?, ?, ?, ?, 't')", (slug, vectors._card_hash(texts[slug]), model, len(v), v.tobytes()))
    con.commit()
    con.close()
    texts.update(cards or {})
    for slug, text in texts.items():
        if text is not None:
            (cards_dir / f"{slug}.md").write_text(text, encoding="utf-8")
    return str(db), str(cards_dir)


def _blobs(n_per=20, dim=8, seed=1):
    """Three well-separated groups of unit-ish vectors: a*, b*, c*."""
    rng = np.random.RandomState(seed)
    rows = []
    for g, name in enumerate("abc"):
        centre = np.zeros(dim)
        centre[g] = 1
        rows += [(f"{name}{i:02d}", centre + rng.normal(0, 0.05, dim)) for i in range(n_per)]
    return rows


def test_no_store_reports_not_built(tmp_path):
    r = svc.build_embedding_report(str(tmp_path / "nope.sqlite"), str(tmp_path / "cards"))
    assert r["built"] is False and r["ok"] is False and "vectors-build" in r["line"]
    assert r["clusters"] == [] and r["points"] == []


def test_fresh_store_is_ok_and_counts(tmp_path):
    db, cards = _store(tmp_path, _blobs())
    r = svc.build_embedding_report(db, cards)
    assert r["built"] and r["ok"] and (r["cards"], r["vectors"], r["dim"], r["model"]) == (60, 60, 8, "m")
    assert r["missing"] == r["changed"] == r["removed"] == []


def test_pages_behind_are_listed_with_titles(tmp_path):
    rows = _blobs()
    db, cards = _store(tmp_path, rows, cards={"a00": "# Edited\n\nnew summary\n", "new-page": "# New page\n\ns\n", "b00": None})
    r = svc.build_embedding_report(db, cards)
    assert r["ok"] is False
    assert r["changed"] == [{"slug": "a00", "title": "Edited"}]
    assert r["missing"] == [{"slug": "new-page", "title": "New page"}]
    assert r["removed"] == [{"slug": "b00", "title": "b00"}]


def test_clusters_recover_the_groups(tmp_path):
    db, cards = _store(tmp_path, _blobs())
    r = svc.build_embedding_report(db, cards)
    assert r["k"] == len(r["clusters"]) and sum(c["size"] for c in r["clusters"]) == 60
    assert [c["id"] for c in r["clusters"]] == list(range(r["k"]))
    assert [c["size"] for c in r["clusters"]] == sorted((c["size"] for c in r["clusters"]), reverse=True)
    by_slug = {p["slug"]: p["cluster"] for p in r["points"]}
    for name in "abc":                       # a group is never split from itself across the two other groups
        assert not {by_slug[f"{name}{i:02d}"] for i in range(20)} & {by_slug[f"{o}{i:02d}"] for o in "abc" if o != name for i in range(20)}
    assert r["silhouette"] > 0.5
    assert all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in r["points"])
    assert r["clusters"][0]["central"][0]["title"].startswith("Title of ")


def test_kmeans_with_three_groups_is_exact():
    m = svc._unit(np.asarray([v for _, v in _blobs()], dtype=np.float32))
    labels, _ = svc.kmeans(m, 3)
    assert [len(set(labels[i:i + 20].tolist())) for i in (0, 20, 40)] == [1, 1, 1] and len(set(labels.tolist())) == 3
    assert svc.silhouette(m, labels) > 0.9


def test_too_few_pages_make_one_cluster(tmp_path):
    db, cards = _store(tmp_path, [("a", [1, 0]), ("b", [0, 1]), ("c", [1, 1])])
    r = svc.build_embedding_report(db, cards)
    assert r["k"] == 1 and r["clusters"][0]["size"] == 3 and len(r["points"]) == 3


def test_near_duplicates_are_pairs_once_closest_first(tmp_path):
    db, cards = _store(tmp_path, [("a", [1, 0, 0]), ("b", [1, 0.01, 0]), ("c", [0, 1, 0]), ("d", [1, 0.1, 0])])
    r = svc.build_embedding_report(db, cards)
    pairs = [(d["a"]["slug"], d["b"]["slug"]) for d in r["duplicates"]]
    assert pairs[0] == ("a", "b") and ("b", "a") not in pairs and all("c" not in p for p in pairs)
    assert all(d["cosine"] >= svc.DUPLICATE_COSINE for d in r["duplicates"])


def test_mixed_models_report_the_reason(tmp_path):
    db, cards = _store(tmp_path, [("a", [1, 0])])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO vectors VALUES ('z', 'h', 'other', 2, ?, 't')", (np.asarray([0, 1], dtype=np.float32).tobytes(),))
    con.commit()
    con.close()
    r = svc.build_embedding_report(db, cards)
    assert r["ok"] is False and "mixes models" in r["line"] and r["points"] == []

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


def test_near_pairs_sit_between_near_and_duplicate_closest_first(tmp_path):
    # a·b ~0.9 (near), a·e = 1 (duplicate), c alone
    db, cards = _store(tmp_path, [("a", [1, 0, 0]), ("b", [1, 0.5, 0]), ("c", [0, 0, 1]), ("e", [1, 0, 0])])
    r = svc.build_embedding_report(db, cards)
    pairs = [(d["a"]["slug"], d["b"]["slug"]) for d in r["near"]]
    assert ("a", "b") in pairs and ("a", "e") not in pairs and all("c" not in p for p in pairs)
    assert all(svc.NEAR_COSINE <= d["cosine"] < svc.DUPLICATE_COSINE for d in r["near"])
    assert [d["cosine"] for d in r["near"]] == sorted((d["cosine"] for d in r["near"]), reverse=True)
    assert r["near"][0]["a"]["title"] == "Title of a"


def test_isolated_pages_are_the_furthest_from_any_other(tmp_path):
    rows = _blobs(n_per=20) + [("lone", [0, 0, 0, 0, 0, 0, 0, 1])]
    db, cards = _store(tmp_path, rows)
    r = svc.build_embedding_report(db, cards)
    assert r["isolated"][0]["slug"] == "lone"
    assert r["isolated"][0]["nearest"] < 0.2
    assert len(r["isolated"]) <= svc.ISOLATED_MAX


def test_isolated_needs_three_pages():
    assert svc.isolated(np.eye(2, dtype=np.float32), ["a", "b"]) == []


def test_mixed_models_report_the_reason(tmp_path):
    db, cards = _store(tmp_path, [("a", [1, 0])])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO vectors VALUES ('z', 'h', 'other', 2, ?, 't')", (np.asarray([0, 1], dtype=np.float32).tobytes(),))
    con.commit()
    con.close()
    r = svc.build_embedding_report(db, cards)
    assert r["ok"] is False and "mixes models" in r["line"] and r["points"] == []


def test_components_order_variance_and_name_both_ends(tmp_path):
    db, cards = _store(tmp_path, _blobs())
    r = svc.build_embedding_report(db, cards)
    assert r["spectrum"] == sorted(r["spectrum"], reverse=True) and 0.99 < sum(r["spectrum"]) <= 1.001
    assert [c["index"] for c in r["components"]] == list(range(len(r["components"]))) and len(r["components"]) <= svc.AXES
    first = r["components"][0]
    assert first["variance"] == r["spectrum"][0] and r["components"][1]["cumulative"] > first["cumulative"]
    ends = [{p["slug"][0] for p in first[k]} for k in ("low", "high")]
    assert all(len(e) == 1 for e in ends) and ends[0] != ends[1]          # each end is one group, and not the same one
    p = r["points"][0]
    assert len(p["pc"]) == len(r["components"]) and (p["x"], p["y"]) == (p["pc"][0], p["pc"][1])
    assert 1.5 < r["effective_dim"] < 3 and 0 < r["mean_cosine"] < 1      # three groups: two directions carry it


def test_pca_is_the_same_on_every_run():
    m = svc._unit(np.asarray([v for _, v in _blobs()], dtype=np.float32))
    a, b = svc.pca(m), svc.pca(m.copy())
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]


def test_identical_vectors_have_no_components(tmp_path):
    db, cards = _store(tmp_path, [(f"p{i}", [1, 0, 0]) for i in range(3)])
    r = svc.build_embedding_report(db, cards)
    assert r["components"] == [] and r["spectrum"] == [] and all(p["pc"] == [] and p["x"] == 0.5 for p in r["points"])


def test_map_is_reused_until_the_store_changes_and_titles_stay_live(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_GRAPH_CACHE", "1")
    db, cards = _store(tmp_path, _blobs())
    calls = []
    real = svc._map
    monkeypatch.setattr(svc, "_map", lambda v: calls.append(1) or real(v))
    first = svc.build_embedding_report(db, cards)
    (tmp_path / "qmd-cards" / "a00.md").write_text("# Renamed\n\nsummary\n", encoding="utf-8")
    second = svc.build_embedding_report(db, cards)
    assert len(calls) == 1 and first["k"] == second["k"]
    assert next(p for p in second["points"] if p["slug"] == "a00")["title"] == "Renamed"
    con = sqlite3.connect(db)
    con.execute("DELETE FROM vectors WHERE slug = 'c19'")
    con.commit()
    con.close()
    assert len(svc.build_embedding_report(db, cards)["points"]) == 59 and len(calls) == 2


def test_identical_off_axis_vectors_are_not_a_noise_component():
    for n in (2, 5, 17, 39):
        m = svc._unit(np.tile(np.asarray([0.3, 0.4, 0.5], dtype=np.float32), (n, 1)))
        coords, ratios, effective = svc.pca(m)
        assert coords.shape == (n, 0) and ratios == [] and effective == 0.0


def test_spectrum_is_never_longer_than_the_rank():
    m = svc._unit(np.asarray([[1, 0, 0], [0, 1, 0]], dtype=np.float32))
    coords, ratios, _ = svc.pca(m)
    assert coords.shape[1] == len(ratios) == 1


def test_similarity_counts_every_pair_once_and_each_pages_nearest(tmp_path):
    db, cards = _store(tmp_path, _blobs())
    sim = svc.build_embedding_report(db, cards)["similarity"]
    assert sim["pairs"] == 60 * 59 // 2 == sum(sim["counts"]) and sum(sim["nearest"]) == sim["pages"] == 60 and sim["sampled"] is False
    assert len(sim["edges"]) == len(sim["counts"]) + 1 == len(sim["nearest"]) + 1 and sim["edges"][-1] == 1.0
    p, near = sim["percentiles"], sim["nearest_percentiles"]
    assert p["p1"] <= p["p50"] <= p["p99"] and near["p50"] > p["p50"]      # a nearest neighbour is closer than a random pair
    assert p["p50"] < 0.3 and near["p50"] > 0.9                             # three far-apart groups, tight inside


def test_similarity_needs_two_pages(tmp_path):
    db, cards = _store(tmp_path, [("a", [1, 0])])
    assert svc.build_embedding_report(db, cards)["similarity"] is None


def test_sample_pairs_stay_in_range_and_follow_the_seed(tmp_path):
    db, cards = _store(tmp_path, _blobs())
    close = svc.sample_pairs(0.9, 1.0, n=5, seed=1, db_path=db, cards_dir=cards)
    assert close["count"] == 3 * (20 * 19 // 2) and len(close["pairs"]) == 5
    assert all(0.9 <= d["cosine"] <= 1.0 and d["a"]["slug"][0] == d["b"]["slug"][0] and d["a"]["slug"] != d["b"]["slug"] for d in close["pairs"])
    assert [d["cosine"] for d in close["pairs"]] == sorted((d["cosine"] for d in close["pairs"]), reverse=True)
    assert close["pairs"][0]["a"]["title"].startswith("Title of ")
    key = lambda r: [(d["a"]["slug"], d["b"]["slug"]) for d in r["pairs"]]      # noqa: E731
    assert key(close) == key(svc.sample_pairs(0.9, 1.0, n=5, seed=1, db_path=db, cards_dir=cards))
    assert key(close) != key(svc.sample_pairs(0.9, 1.0, n=5, seed=2, db_path=db, cards_dir=cards))
    far = svc.sample_pairs(-1.0, 0.5, n=50, seed=0, db_path=db, cards_dir=cards)
    assert far["count"] == 3 * 20 * 20 and len(far["pairs"]) == svc.PAIRS_MAX
    assert all(d["a"]["slug"][0] != d["b"]["slug"][0] for d in far["pairs"])


def test_sample_pairs_without_a_store_or_matches_is_empty(tmp_path):
    assert svc.sample_pairs(0, 1, db_path=str(tmp_path / "no.sqlite"), cards_dir=str(tmp_path)) == {"count": 0, "pairs": []}
    db, cards = _store(tmp_path, _blobs())
    assert svc.sample_pairs(0.5, 0.6, db_path=db, cards_dir=cards) == {"count": 0, "pairs": []}


def test_large_stores_measure_pairs_on_a_sample_of_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "PAIR_ROWS_MAX", 30)
    db, cards = _store(tmp_path, _blobs())
    sim = svc.build_embedding_report(db, cards)["similarity"]
    assert sim["sampled"] is True and sim["pages"] == 30 and sim["pairs"] == 30 * 29 // 2
    assert svc.sample_pairs(0.9, 1.0, n=3, db_path=db, cards_dir=cards)["count"] <= 30 * 29 // 2


def test_every_bar_holds_exactly_the_pairs_the_sampler_finds_for_its_edges(tmp_path):
    rng = np.random.RandomState(7)
    rows = [(f"p{i:03d}", rng.normal(size=6)) for i in range(120)] + [("twin-a", [1, 2, 3, 4, 5, 6]), ("twin-b", [1, 2, 3, 4, 5, 6])]
    db, cards = _store(tmp_path, rows)
    sim = svc.build_embedding_report(db, cards)["similarity"]
    assert sim["edges"][0] < 0 and sim["counts"][-1] >= 1               # negative cosines and the identical pair are both counted
    for i, count in enumerate(sim["counts"]):
        assert svc.sample_pairs(sim["edges"][i], sim["edges"][i + 1], n=1, db_path=db, cards_dir=cards)["count"] == count


def test_a_broken_vector_does_not_break_the_report(tmp_path):
    db, cards = _store(tmp_path, _blobs() + [("broken", [float("nan")] * 8)])
    r = svc.build_embedding_report(db, cards)
    assert r["similarity"]["pairs"] == 61 * 60 // 2

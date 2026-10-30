"""Card vector store: load, neighbours, similarity, the guards (missing store, mixed models), where it lives
(the selected kb's .cache) and whether it is behind the cards it is built from."""
import os
import shutil
import sqlite3
import subprocess

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


# --- where the store lives, and whether it is behind its cards -------------------------------------------

def _cards(path, texts):
    path.mkdir(parents=True, exist_ok=True)
    for slug, text in texts.items():
        (path / f"{slug}.md").write_text(text, encoding="utf-8")
    return str(path)


def _db_hashed(path, cards):
    """A store as vectors.mjs writes it: one row per card, hash of its trimmed text."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE vectors (slug TEXT PRIMARY KEY, hash TEXT, model TEXT, dim INTEGER, vec BLOB, at TEXT)")
    for slug, text in cards.items():
        con.execute("INSERT INTO vectors VALUES (?, ?, 'm', 2, ?, 't')",
                    (slug, vectors._card_hash(text), np.asarray([1, 0], dtype=np.float32).tobytes()))
    con.commit()
    con.close()
    return str(path)


def test_store_and_cards_live_in_the_selected_kb_cache():
    """The kb-split regression: the reader must look in the selected kb's .cache, next to the cards it embeds
    — never in the explorer checkout (which holds no vault since the split)."""
    from kb import paths
    from kb.search import cards
    assert vectors.DB_PATH == os.path.join(paths.CACHE_PATH, "vectors.sqlite")
    assert vectors.CARDS_DIR == cards.CARDS_DIR
    assert os.path.realpath(paths.CACHE_PATH) == os.path.realpath(os.path.join(paths.ROOT, ".cache"))
    if paths.KB is not None:            # split layout: the vault is a kb folder, not this checkout
        assert not os.path.realpath(vectors.DB_PATH).startswith(os.path.realpath(paths.CHECKOUT_ROOT) + os.sep)


def test_status_missing_store_is_not_ok(tmp_path):
    ok, line = vectors.status(str(tmp_path / "nope.sqlite"), str(tmp_path / "cards"))
    assert not ok and "no vector store" in line and "vectors-build" in line


def test_status_store_without_cards_is_not_ok(tmp_path):
    db = _db_hashed(tmp_path / "v.sqlite", {"a": "# A\n\nx\n"})
    ok, line = vectors.status(db, str(tmp_path / "cards"))
    assert not ok and "no cards" in line


def test_status_up_to_date(tmp_path):
    texts = {"a": "# A\n\nfirst\n", "b": "# B\n\nsecond\n"}
    ok, line = vectors.status(_db_hashed(tmp_path / "v.sqlite", texts), _cards(tmp_path / "cards", texts))
    assert ok and line == "2 vectors for 2 cards"


def test_status_behind_counts_missing_changed_removed(tmp_path):
    db = _db_hashed(tmp_path / "v.sqlite", {"a": "# A\n\nold\n", "b": "# B\n\nsame\n", "gone": "# G\n\nx\n"})
    cards_dir = _cards(tmp_path / "cards", {"a": "# A\n\nnew\n", "b": "# B\n\nsame\n", "fresh": "# F\n\ny\n"})
    f = vectors.freshness(db, cards_dir)
    assert (f["missing"], f["changed"], f["removed"]) == (["fresh"], ["a"], ["gone"])
    ok, line = vectors.status(db, cards_dir)
    assert not ok and "1 missing, 1 changed, 1 removed" in line


def test_card_hash_matches_vectors_mjs():
    """freshness() compares against hashes vectors.mjs wrote: both must hash the same bytes the same way."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    text = "  # Title — עברית\n\nsummary line\n\n"
    js = ('const c=require("node:crypto");let t="";process.stdin.on("data",d=>t+=d).on("end",()=>'
          'console.log(c.createHash("sha256").update(t.trim()).digest("hex").slice(0,16)))')
    out = subprocess.run([node, "-e", js], input=text, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == vectors._card_hash(text)

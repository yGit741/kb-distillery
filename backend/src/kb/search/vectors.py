"""Read the card vectors (`.cache/vectors.sqlite`, built by `tools/qmd/vectors.mjs`): one unit vector per
page from its title + summary, the same model the qmd search service uses. For graph math — nearest pages
now, link closeness later — never for stating facts.

    python -m kb.search.vectors neighbours <slug> [-k 8]     (pixi run vectors -- neighbours aep)
    python -m kb.search.vectors status                         (exit 1 when missing or behind the cards)

The store is per knowledge base (`<kb>/.cache/`); `pixi run vectors-build [-- --kb <id>]` writes it there.
"""
import argparse
import hashlib
import os
import sqlite3
import sys

import numpy as np          # installed with opencv-python-headless (pixi pypi deps)

from kb import paths

DB_PATH = os.path.join(paths.CACHE_PATH, "vectors.sqlite")
CARDS_DIR = os.path.join(paths.CACHE_PATH, "qmd-cards")    # = kb.search.cards.CARDS_DIR, what vectors.mjs embeds


class Vectors:
    """slugs, a row-normalised float32 matrix, and the model that made it."""

    def __init__(self, slugs, matrix, model):
        self.slugs = list(slugs)
        self.index = {s: i for i, s in enumerate(self.slugs)}
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) if len(matrix) else np.ones((0, 1))
        self.m = matrix / np.where(norms == 0, 1, norms)
        self.model = model

    def __len__(self):
        return len(self.slugs)

    def similarity(self, a, b):
        """Cosine of two pages' vectors, or None when either has no vector."""
        if a not in self.index or b not in self.index:
            return None
        return float(self.m[self.index[a]] @ self.m[self.index[b]])

    def neighbours(self, slug, k=8):
        """[(slug, cosine)] of the k closest other pages, best first ([] when `slug` has no vector)."""
        if slug not in self.index or len(self) < 2:
            return []
        sims = self.m @ self.m[self.index[slug]]
        sims[self.index[slug]] = -np.inf
        top = np.argsort(-sims)[:k]
        return [(self.slugs[j], round(float(sims[j]), 4)) for j in top]


def load(db_path=None):
    """The store, or None when it was never built."""
    db_path = db_path or DB_PATH
    if not os.path.exists(db_path):
        return None
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT slug, model, dim, vec FROM vectors ORDER BY slug").fetchall()
    finally:
        con.close()
    if not rows:
        return Vectors([], np.zeros((0, 0), dtype=np.float32), None)
    models = {r[1] for r in rows}
    if len(models) > 1:                 # half-rebuilt after a model change: vectors don't compare
        raise ValueError(f"{db_path} mixes models {sorted(models)} — rerun `pixi run vectors-build`")
    dim = rows[0][2]
    m = np.stack([np.frombuffer(r[3], dtype=np.float32, count=dim) for r in rows])
    return Vectors([r[0] for r in rows], m, rows[0][1])


def _card_hash(text):
    """The hash vectors.mjs stores: sha256 of the trimmed card text, first 16 hex chars."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def freshness(db_path=None, cards_dir=None):
    """How the store compares with the cards it is built from → {'cards', 'vectors', 'missing', 'changed',
    'removed'} (slug lists for the last three), or None when there is no store. Up to date = all three empty."""
    db_path, cards_dir = db_path or DB_PATH, cards_dir or CARDS_DIR
    if not os.path.exists(db_path):
        return None
    cards = {}
    if os.path.isdir(cards_dir):
        for f in os.listdir(cards_dir):
            if f.endswith(".md"):
                with open(os.path.join(cards_dir, f), encoding="utf-8") as fh:
                    cards[f[:-3]] = _card_hash(fh.read())
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        have = dict(con.execute("SELECT slug, hash FROM vectors").fetchall())
    finally:
        con.close()
    return {"cards": len(cards), "vectors": len(have),
            "missing": sorted(set(cards) - set(have)),
            "changed": sorted(s for s in cards.keys() & have.keys() if cards[s] != have[s]),
            "removed": sorted(set(have) - set(cards))}


def status(db_path=None, cards_dir=None):
    """(ok, one line) for `vectors status` and the launcher: missing or behind the cards is not ok."""
    db_path = db_path or DB_PATH
    f = freshness(db_path, cards_dir)
    if f is None:
        return False, f"no vector store at {db_path} — run `pixi run vectors-build`"
    if not f["cards"]:
        return False, f"no cards in {cards_dir or CARDS_DIR} — run `pixi run qmd-cards` (or lint) first"
    behind = [f"{len(f[k])} {k}" for k in ("missing", "changed", "removed") if f[k]]
    line = f"{f['vectors']} vectors for {f['cards']} cards"
    if behind:
        return False, f"{line}, behind ({', '.join(behind)}) — run `pixi run vectors-build`"
    return True, line


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vectors")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("neighbours", help="the pages closest in meaning to <slug>")
    n.add_argument("slug")
    n.add_argument("-k", type=int, default=8)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        ok, line = status()
        v = load() if ok else None
        print(f"{line} · {v.m.shape[1] if v and len(v) else 0} dims · {v.model}" if v else line)
        return 0 if ok else 1
    v = load()
    if v is None:
        print(f"no vector store at {DB_PATH} — run `pixi run vectors-build`")
        return 1
    hits = v.neighbours(a.slug, a.k)
    if not hits:
        print(f"{a.slug}: no vector (no summary yet, or a course)")
        return 1
    for s, c in hits:
        print(f"{c:.3f}  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build the page vectors (`<kb>/.cache/vectors.sqlite`) in Python: one unit vector per page from its card (title +
description, `kb_distillery.search.cards`). The reader is `kb_distillery.search.vectors`; the graph's topic colouring,
meaning map and missing links read the file. `scripts/qmd/vectors.mjs` writes the same table with node and the qmd
model; this does it with a local model and no node.

    distill search vectors-build [--kb <id|path>] [--model bge-small]     (python -m kb_distillery.search.vectors_build)
    distill search vectors-build --all                                     every knowledge base in the bases dir
    distill search vectors-build --status                                  what is built, what is behind

Only cards whose text changed are re-embedded; a card that is gone loses its row; rows made by another model are
dropped first (the reader refuses a file that mixes models). The embedding model is an optional dependency, imported
only when something has to be embedded:  pip install 'kb-distillery[vectors]'  (bge-small, ONNX, CPU)  or
'kb-distillery[vectors-qwen]'  (the Qwen3 models, sentence-transformers + torch).
"""
import argparse
import os
import sqlite3
import sys
import time

import numpy as np

from kb_distillery.config import kb as kbconfig
from kb_distillery.search import cards, vectors

SCHEMA = ("CREATE TABLE IF NOT EXISTS vectors (slug TEXT PRIMARY KEY, hash TEXT NOT NULL, model TEXT NOT NULL, "
          "dim INTEGER NOT NULL, vec BLOB NOT NULL, at TEXT NOT NULL)")       # what vectors.mjs creates

# key: (backend, model id, install extra)
MODELS = {
    "bge-small": ("fastembed", "BAAI/bge-small-en-v1.5", "vectors"),
    "qwen3-0.6b": ("sentence-transformers", "Qwen/Qwen3-Embedding-0.6B", "vectors-qwen"),
    "qwen3-4b": ("sentence-transformers", "Qwen/Qwen3-Embedding-4B", "vectors-qwen"),
    "qwen3-8b": ("sentence-transformers", "Qwen/Qwen3-Embedding-8B", "vectors-qwen"),
}
DEFAULT_MODEL = "bge-small"


class NothingToEmbed(RuntimeError):
    """This kb has no wiki/ or no page with a description."""


class EmbedderMissing(RuntimeError):
    """The optional embedding package is not installed."""


class Embedder:
    """One loaded model: `passages(texts)` -> one float vector per text. Imports the backend here, not at module load."""

    def __init__(self, key=DEFAULT_MODEL):
        self.backend, self.model_id, extra = MODELS[key]
        try:
            if self.backend == "fastembed":
                from fastembed import TextEmbedding
                cache = os.environ.get("FASTEMBED_CACHE_PATH") or os.path.join(os.path.expanduser("~"), ".cache", "fastembed")
                self.model = TextEmbedding(self.model_id, cache_dir=cache)
            else:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_id)
                self.model.max_seq_length = 1024
        except ImportError as e:
            raise EmbedderMissing(f"the embedding model {key} needs an optional package ({e.name}): "
                                  f"pip install 'kb-distillery[{extra}]'") from e

    def passages(self, texts):
        if self.backend == "fastembed":
            return [np.asarray(v, dtype=np.float32) for v in self.model.passage_embed(texts, batch_size=64)]
        return list(self.model.encode(texts, batch_size=32, normalize_embeddings=True))


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n else v


def read_cards(root):
    """{slug: card text}, the cards folder synced with wiki/ first."""
    cards_dir = os.path.join(root, ".cache", "qmd-cards")
    if not os.path.isdir(os.path.join(root, "wiki")):
        raise NothingToEmbed(f"{root} has no wiki/ folder")
    cards.build(os.path.join(root, "wiki"), cards_dir)
    out = {}
    for f in sorted(os.listdir(cards_dir)):
        if f.endswith(".md"):
            with open(os.path.join(cards_dir, f), encoding="utf-8") as fh:
                out[f[:-3]] = fh.read()
    return out


def build(root, model=DEFAULT_MODEL, make=None):
    """Sync one kb's vector store with its cards -> {'embedded', 'removed', 'unchanged'}. `make(model_key)` builds the
    embedder on first need (default `Embedder`); a store already up to date never loads a model."""
    model_id = MODELS[model][1]
    texts = read_cards(root)
    if not texts:
        raise NothingToEmbed(f"no cards for {root} (no page has a description yet) — nothing to embed")
    os.makedirs(os.path.join(root, ".cache"), exist_ok=True)
    con = sqlite3.connect(os.path.join(root, ".cache", "vectors.sqlite"))
    try:
        con.execute(SCHEMA)
        con.execute("DELETE FROM vectors WHERE model != ?", (model_id,))
        have = dict(con.execute("SELECT slug, hash FROM vectors"))
        hashes = {s: vectors._card_hash(t) for s, t in texts.items()}
        todo = [s for s in texts if have.get(s) != hashes[s]]
        gone = sorted(set(have) - set(texts))
        if todo:
            emb = (make or Embedder)(model)
            vecs = emb.passages([texts[s] for s in todo])
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            con.executemany(
                "INSERT OR REPLACE INTO vectors (slug, hash, model, dim, vec, at) VALUES (?, ?, ?, ?, ?, ?)",
                [(s, hashes[s], model_id, len(v), _unit(v).tobytes(), now) for s, v in zip(todo, vecs)])
        con.executemany("DELETE FROM vectors WHERE slug = ?", [(s,) for s in gone])
        con.commit()
    finally:
        con.close()
    return {"embedded": len(todo), "removed": len(gone), "unchanged": len(texts) - len(todo)}


def status(root, model=DEFAULT_MODEL):
    db = os.path.join(root, ".cache", "vectors.sqlite")
    ok, line = vectors.status(db, os.path.join(root, ".cache", "qmd-cards"))
    if ok:
        have = vectors.load(db).model
        if have != MODELS[model][1]:
            ok, line = False, f"{line}, built with {have}, not {MODELS[model][1]}"
    return ("ok      " if ok else "behind  ") + line


def targets(every):
    """[(name, folder)]: every kb in the bases dir, or the selected one."""
    if every:
        return sorted(kbconfig.discover().items())
    root = kbconfig.vault_root()
    return [(os.path.basename(os.path.realpath(root)), root)]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vectors-build", description="build .cache/vectors.sqlite (pick the kb with --kb <id|path>)")
    ap.add_argument("--all", action="store_true", help="every knowledge base in the bases dir")
    ap.add_argument("--model", choices=sorted(MODELS), default=DEFAULT_MODEL)
    ap.add_argument("--status", action="store_true", help="report only")
    a = ap.parse_args(argv)
    found = targets(a.all)
    if not found:
        print(f"no knowledge base found under {kbconfig.bases_dir()}", file=sys.stderr)
        return 1
    if a.status:
        for name, root in found:
            print(f"{name:30s} {status(root, a.model)}")
        return 0
    emb = []

    def make(key):                      # one model load shared by every kb in this run
        if not emb:
            emb.append(Embedder(key))
        return emb[0]

    failed = 0
    for name, root in found:
        try:
            r = build(root, a.model, make)
        except EmbedderMissing as e:        # the same for every kb: stop
            print(f"vectors-build: {e}", file=sys.stderr)
            return 1
        except NothingToEmbed as e:         # this kb only: go on with the others
            print(f"{name:30s} skipped: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:              # noqa: BLE001 - a model download or runtime failure: a clean line, not a traceback
            print(f"vectors-build: {name}: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        else:
            print(f"{name:30s} embedded {r['embedded']}, removed {r['removed']}, unchanged {r['unchanged']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

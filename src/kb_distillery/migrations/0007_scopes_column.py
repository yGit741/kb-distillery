"""Scopes (schema 0.13): corpus.tsv gets a 7th column `scopes`.

A scope is a personal working set of raw files; membership is a comma-separated list of
`scope-*` slugs per corpus row (hand-editable, like `collection`). The column starts empty.
Idempotent: a manifest that already has the column is left alone.
"""
import os

PRODUCES = (0, 13)
MANIFEST = os.path.join("meta", "corpus.tsv")
HEADER = "path\tsha1\tkind\tdisposition\tslug\tcollection"


def apply(root):
    path = os.path.join(root, MANIFEST)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if any(l.startswith("path\t") and l.split("\t")[-1] == "scopes" for l in lines):
        return
    out = []
    for line in lines:
        if line.startswith("path\t"):
            out.append(line + "\tscopes")
        elif not line or line.startswith("#"):
            out.append(line)
        else:
            parts = line.split("\t")
            parts += [""] * (6 - len(parts))
            out.append("\t".join(parts[:6] + [""]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

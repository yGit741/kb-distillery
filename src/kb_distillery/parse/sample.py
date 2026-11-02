"""Stratified, seeded page picks for measuring the verifier: spread over the book and over page types, split into a
build set (60%, used to find what code misses) and an unseen set (40%, the holdout that gates the flag)."""
from __future__ import annotations

import random
from collections import defaultdict

from .layer import MATH_CLASSES

SEGMENTS = 10
MATH_SHARE = 0.12          # share of glyphs in a math font / symbol class that makes a page "math"


def page_type(layer) -> str:
    n = len(layer.glyphs)
    if not n:
        return "blank"
    if layer.figures:
        return "figure"
    math = sum(1 for g in layer.glyphs if g.cls in MATH_CLASSES)
    return "math" if math / n >= MATH_SHARE else "prose"


def stratify(types: dict, n: int = 100, seed: int = 7, build: int = 60) -> dict:
    """`types` {1-based page: type} -> {"build": [...], "unseen": [...], "cells": {cell: count}}.
    Cells are (tenth of the document, page type). Each non-empty cell gets a pick before any gets a second; build and
    unseen are dealt cell by cell so both cover the cells."""
    pages = sorted(p for p, t in types.items() if t != "blank")
    share_of = build / n if n > 0 else 0.0                 # the requested split, not the clipped count
    n = min(n, len(pages))
    if not pages or n <= 0:
        return {"build": [], "unseen": [], "cells": {}}
    rng = random.Random(seed)
    cells: dict = defaultdict(list)
    for i, p in enumerate(pages):
        cells[(i * SEGMENTS // len(pages), types[p])].append(p)
    for v in cells.values():
        rng.shuffle(v)
    picked: list = []
    keys = sorted(cells)
    while len(picked) < n and any(cells[k] for k in keys):
        order = [k for k in keys if cells[k]]
        # a round: one pick from each cell that still has pages, biggest cells first once n runs short
        if len(order) > n - len(picked):
            order = sorted(order, key=lambda k: -len(cells[k]))[: n - len(picked)]
        for k in order:
            picked.append((k, cells[k].pop()))
    # deal: keep the running build share at build/n
    share, got_build = min(share_of, 0.9), 0              # a holdout always exists when there are 2+ picks
    out = {"build": [], "unseen": []}
    for i, (k, p) in enumerate(sorted(picked, key=lambda kp: (kp[0], rng.random()))):
        if got_build < round(share * (i + 1)):
            out["build"].append(p)
            got_build += 1
        else:
            out["unseen"].append(p)
    out["build"].sort()
    out["unseen"].sort()
    counts: dict = defaultdict(int)
    for k, _ in picked:
        counts["%d:%s" % k] += 1
    out["cells"] = dict(sorted(counts.items()))
    return out


def sample(pdf: str, n: int = 100, seed: int = 7, build: int = 60) -> dict:
    """Classify every page of `pdf` from its text layer, then stratify."""
    import fitz
    from . import layer as L
    doc = fitz.open(pdf)
    try:
        types = {p.number + 1: page_type(L.read_page(p)) for p in doc}
    finally:
        doc.close()
    res = stratify(types, n, seed, build)
    res["types"] = {t: sum(1 for v in types.values() if v == t) for t in sorted(set(types.values()))}
    return res

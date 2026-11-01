"""Structure checks over a run of Markdown pages: theorem-like statements and equation tags count up in sequence,
every Figure / Table caption sits next to its figure or table, and (given the layers) nothing the PDF numbers is
dropped or made up. Flags reuse `reconcile.Flag`: dropped | repeated | out-of-order | orphan-caption | invented-label.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .layer import PageLayer
from .reconcile import Flag

WORDS = "Theorem|Lemma|Proposition|Corollary|Definition|Remark|Example|Claim|Conjecture|Fact|Observation|Assumption"
STATEMENT = re.compile(r"^[ \t>#*_]*(%s)\s+(\d+(?:\.\d+)*)\b" % WORDS, re.M)
CAPTION = re.compile(r"^[ \t>#*_]*(Figure|Fig\.|Table)\s+(\d+(?:\.\d+)*)\s*[.:]", re.M)
DISPLAY = [re.compile(p, re.S) for p in (r"\$\$(.+?)\$\$", r"\\\[(.+?)\\\]",
                                          r"\\begin\{(equation|align|gather|multline)\*?\}(.+?)\\end\{\1\*?\}")]
TAG = re.compile(r"\\tag\*?\{\(?(\d+(?:\.\d+)*)\)?\}|(?:\\q?quad|\\eqno)\s*\(?(\d+(?:\.\d+)*)\)?\s*$")


def _num(s: str) -> tuple:
    return tuple(int(x) for x in s.split("."))


def _kind(word: str) -> str:
    return "Figure" if word.startswith("Fig") else word


def statements(md: str) -> list:
    return [(m.group(1), m.group(2)) for m in STATEMENT.finditer(md)]


def captions(md: str) -> list:
    return [(_kind(m.group(1)), m.group(2)) for m in CAPTION.finditer(md)]


def equation_tags(md: str) -> list:
    out = []
    for rx in DISPLAY:
        for m in rx.finditer(md):
            body = m.group(m.lastindex)
            for t in TAG.finditer(body.strip()):
                out.append(t.group(1) or t.group(2))
    # a bare "(2.1)" paragraph right after a display
    for m in re.finditer(r"(?:\$\$|\\\])\s*\n\s*\((\d+(?:\.\d+)*)\)\s*$", md, re.M):
        out.append(m.group(1))
    return out


def _sequence(labels: list, page: int, label: str, prev: tuple | None) -> tuple:
    """Flags for one counter's labels on a page, and the last number seen (carried to the next page)."""
    flags = []
    for s in labels:
        n = _num(s)
        if prev is not None:
            if len(n) == len(prev) and n[:-1] == prev[:-1]:
                if n[-1] == prev[-1]:
                    flags.append(Flag("repeated", page, "%s %s appears twice" % (label, s), label))
                elif n[-1] < prev[-1]:
                    flags.append(Flag("out-of-order", page, "%s %s comes after %s" % (label, s, ".".join(map(str, prev))), label))
                elif n[-1] > prev[-1] + 1:
                    flags.append(Flag("dropped", page, "%s %s follows %s: %s missing" % (
                        label, s, ".".join(map(str, prev)), ".".join(map(str, prev[:-1] + (prev[-1] + 1,)))), label))
            elif len(n) == len(prev) and n[:-1] < prev[:-1]:
                flags.append(Flag("out-of-order", page, "%s %s comes after %s" % (label, s, ".".join(map(str, prev))), label))
            elif n[-1] != 1:
                flags.append(Flag("dropped", page, "%s %s starts a new group not at 1" % (label, s), label))
        prev = n
    return flags, prev


def _adjacent(md: str, caption_at: int, want: str) -> bool:
    blocks = [b for b in re.split(r"\n\s*\n", md)]
    pos, idx = 0, 0
    for i, b in enumerate(blocks):
        pos = md.find(b, pos)
        if pos <= caption_at < pos + len(b):
            idx = i
            break
        pos += len(b)
    probe = re.compile(r"!\[[^\]]*\]\(" if want == "Figure" else r"^\s*\|.*\|", re.M)
    near = blocks[max(0, idx - 1): idx + 2]
    return any(probe.search(b) for b in near)


def layer_lines(layer: PageLayer) -> str:
    rows = defaultdict(list)
    for w in layer.words:
        rows[w.line].append(w.text)
    return "\n".join(" ".join(rows[k]) for k in sorted(rows))


def _layer_eq(text: str) -> list:
    out = []
    for ln in text.splitlines():
        m = re.search(r"\((\d+(?:\.\d+)*)\)\s*$", ln)
        if m and not re.search(r"[a-z]{4,}", ln[:m.start()]):
            out.append(m.group(1))
    return out


def check_structure(pages_md: list, layers: list | None = None, first_page: int = 1, shared: bool = True) -> list:
    """Flags for a run of consecutive pages. With `layers`, labels and captions the PDF has must all be in the output.
    `shared`: Theorem / Lemma / ... count on one counter (amsthm default); False gives each word its own."""
    if layers is not None and len(layers) != len(pages_md):
        raise ValueError("%d Markdown pages for %d PDF pages" % (len(pages_md), len(layers)))
    flags: list = []
    pages = [first_page + i for i in range(len(pages_md))]
    seq = [(p, w, n) for p, md in zip(pages, pages_md) for w, n in statements(md)]

    def run(keyfn):
        fl, last = [], {}
        for p in pages:
            by = defaultdict(list)
            for pp, w, n in seq:
                if pp == p:
                    by[keyfn(w)].append(n)
            for k, labs in by.items():
                f, last[k] = _sequence(labs, p, k, last.get(k))
                fl.extend(f)
        return fl

    flags += run((lambda w: "Theorem-like") if shared else (lambda w: w))
    last_eq = None
    for p, md in zip(pages, pages_md):
        f, last_eq = _sequence(equation_tags(md), p, "Equation", last_eq)
        flags += f
    last_cap: dict = {}
    for p, md in zip(pages, pages_md):
        by = defaultdict(list)
        for m in CAPTION.finditer(md):
            kind = _kind(m.group(1))
            by[kind].append(m.group(2))
            if not _adjacent(md, m.start(), kind):
                flags.append(Flag("orphan-caption", p, "%s %s has no %s beside it" % (
                    kind, m.group(2), "figure" if kind == "Figure" else "table"), kind))
        for kind, labs in by.items():
            f, last_cap[kind] = _sequence(labs, p, kind, last_cap.get(kind))
            flags += f
    if layers:
        for p, md, layer in zip(pages, pages_md, layers):
            text = layer_lines(layer)
            pdf = Counter(statements(text)) + Counter(captions(text)) + Counter(("Equation", t) for t in _layer_eq(text))
            got = Counter(statements(md)) + Counter(captions(md)) + Counter(("Equation", t) for t in equation_tags(md))
            for (k, n), c in sorted((pdf - got).items()):
                flags.append(Flag("dropped", p, "%s %s is on the PDF page but not in the output" % (k, n), k))
            for (k, n), c in sorted((got - pdf).items()):
                flags.append(Flag("invented-label", p, "%s %s is in the output but not on the PDF page" % (k, n), k))
    return flags

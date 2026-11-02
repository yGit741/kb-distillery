"""Fake-error generator: take Markdown known to be right, plant one mistake of a known kind, and see whether the
verifier notices. `variants` yields every site of one kind (exhaustive, so a catch rate is a real count);
`measure` runs a checker over pages x kinds and reports caught / total per kind.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .reconcile import _MATH_RES

KINDS = ("drop_word", "iff_to_if", "add_tilde", "add_dot", "add_hat", "stray_bar", "invented_row",
         "swap_numbers", "change_number")
CONFUSIONS = (("iff", "if"), ("then", "than"), ("than", "then"), ("affect", "effect"), ("effect", "affect"),
              ("principal", "principle"), ("principle", "principal"))
_ACC_CTX = re.compile(r"\\(?:tilde|widetilde|hat|widehat|bar|overline|dot|ddot|vec|check|breve|text|textbf|mathrm|"
                      r"mathbf|operatorname|begin|end|label|tag|ref|eqref|mathbb|mathfrak|mathcal)\s*\{?[^{}]*$")


@dataclass
class Mutation:
    kind: str
    md: str
    detail: str


def _spans(md: str) -> tuple:
    """(math spans as (start, end) of the inner source, protected spans: math + images + links + HTML)."""
    math, prot = [], []
    for rx in _MATH_RES:
        for m in rx.finditer(md):
            math.append((m.start(m.lastindex), m.end(m.lastindex)))
            prot.append(m.span())
    for rx in (r"!\[[^\]]*\]\([^)]*\)", r"\]\([^)]*\)", r"<[^>\n]+>"):
        prot += [m.span() for m in re.finditer(rx, md)]
    return math, prot


def _free(prot: list, a: int, b: int) -> bool:
    return not any(a < pe and b > ps for ps, pe in prot)


def _prose_matches(md: str, rx: str) -> list:
    _, prot = _spans(md)
    return [m for m in re.finditer(rx, md) if _free(prot, m.start(), m.end())]


def _letters_in_math(md: str):
    math, _ = _spans(md)
    seen = set()
    for a, b in math:
        src = md[a:b]
        for m in re.finditer(r"(?<![A-Za-z\\])([A-Za-z])(?![A-Za-z])", src):
            if _ACC_CTX.search(src[:m.start()]) or a + m.start() in seen:
                continue
            seen.add(a + m.start())
            yield a + m.start(), m.group(1)


def _cut(md: str, a: int, b: int, new: str) -> str:
    return md[:a] + new + md[b:]


def variants(md: str, kind: str, limit: int = 80, seed: int = 0):
    """Yield `Mutation`s of `kind` over `md`, one per site (at most `limit`, sampled with `seed`)."""
    sites = _sites(md, kind)
    random.Random(seed).shuffle(sites)
    for fn in sites[:limit]:
        m = fn()
        if m and m.md != md:
            yield m


def _sites(md: str, kind: str) -> list:
    out = []
    if kind == "drop_word":
        for m in _prose_matches(md, r"(?<![\w\\])[A-Za-z]{2,}(?![\w])"):
            out.append(lambda m=m: Mutation(kind, _cut(md, m.start(), m.end(), ""), "dropped '%s'" % m.group(0)))
    elif kind == "iff_to_if":
        for a, b in CONFUSIONS:
            for m in _prose_matches(md, r"\b%s\b" % a):
                out.append(lambda m=m, a=a, b=b: Mutation(kind, _cut(md, m.start(), m.end(), b), "%s -> %s" % (a, b)))
    elif kind in ("add_tilde", "add_dot", "add_hat", "stray_bar"):
        cmd = {"add_tilde": "tilde", "add_dot": "dot", "add_hat": "hat", "stray_bar": "overline"}[kind]
        for pos, ch in _letters_in_math(md):
            out.append(lambda pos=pos, ch=ch: Mutation(kind, _cut(md, pos, pos + 1, "\\%s{%s}" % (cmd, ch)),
                                                       "\\%s on '%s'" % (cmd, ch)))
    elif kind == "invented_row":
        lines = md.split("\n")
        rows = [i for i, l in enumerate(lines) if re.match(r"^\s*\|.*\|\s*$", l) and not re.match(r"^\s*\|[\s:|-]+\|\s*$", l)]
        for i in rows:
            def make(i=i):
                cells = lines[i].strip().strip("|").split("|")
                fake = ["%d" % (9000 + k * 7 + i) if re.search(r"\d", c) else "zorb%d" % k for k, c in enumerate(cells)]
                new = lines[:i + 1] + ["| " + " | ".join(fake) + " |"] + lines[i + 1:]
                return Mutation(kind, "\n".join(new), "invented row after line %d" % (i + 1))
            out.append(make)
    elif kind in ("swap_numbers", "change_number"):
        nums = _prose_matches(md, r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")
        if kind == "change_number":
            for m in nums:
                t = m.group(0)
                new = t[:-1] + str((int(t[-1]) + 3) % 10)
                out.append(lambda m=m, new=new: Mutation(kind, _cut(md, m.start(), m.end(), new), "%s -> %s" % (m.group(0), new)))
        else:
            for i, a in enumerate(nums):
                for b in nums[i + 1:]:
                    if a.group(0) != b.group(0):
                        def make(a=a, b=b):
                            s = _cut(md, b.start(), b.end(), a.group(0))
                            return Mutation(kind, _cut(s, a.start(), a.end(), b.group(0)), "swapped %s and %s" % (a.group(0), b.group(0)))
                        out.append(make)
    else:
        raise ValueError("unknown mutation kind %r" % kind)
    return out


def measure(pages: list, check, kinds=KINDS, limit: int = 80) -> dict:
    """pages: [(markdown, layer)]; check(markdown, layer) -> list of flags. Returns {kind: (caught, total)}."""
    res = {k: [0, 0] for k in kinds}
    for md, layer in pages:
        for k in kinds:
            for mut in variants(md, k, limit):
                res[k][1] += 1
                res[k][0] += bool(check(mut.md, layer))
    return {k: tuple(v) for k, v in res.items()}

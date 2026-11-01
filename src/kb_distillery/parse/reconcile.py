"""Closed-world check of a parser's Markdown page against the PDF's own text layer.

Nothing lost (every layer word / glyph is in the output), nothing invented (every output token maps to a glyph),
prose words are the PDF's own words (`iff` must not become `if`), and accents / bars / dots / hats sit where the glyphs
put them. Two tiers keep the noise down:

  tier 1  words and numbers. Layer words that are one font, one size, not a math font; output words outside `$...$`
          and in tables. Matched as multisets, so reading order never matters; a layer word may also be satisfied by a
          run of letters / digits inside the output's math.
  tier 2  single glyphs. Everything else (math letters, scripts, big operators, \\mathbb / \\mathfrak classes) as a
          multiset of normal-form characters.

Ignored on purpose: running heads and page numbers (top / bottom band), labels inside a figure, operators and
punctuation, LaTeX spacing and sizing commands. Flags are few and aggregated: one per wrong word, one per glyph kind.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

from .layer import ACCENTS, BIGOP_CHAR, PageLayer

PIECE = re.compile(r"[^\W\d_]+|\d+(?:[.,]\d+)*")
ALNUM = re.compile(r"[^\W_]", re.U)


@dataclass
class Flag:
    kind: str          # lost | invented | replaced | lost-glyphs | invented-glyphs | accent-added | accent-lost |
    page: int          #   accent-moved | number-order | (structure.py: dropped | repeated | out-of-order | orphan-caption)
    detail: str
    where: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- normal forms

def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _greek() -> dict:
    out = {}
    for name in ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau "
                 "upsilon phi chi psi omega").split():
        for cap in (False, True):
            try:
                ch = unicodedata.lookup("GREEK %s LETTER %s" % ("CAPITAL" if cap else "SMALL", name.upper()))
            except KeyError:
                continue
            out[name.capitalize() if cap else name] = norm(ch)
    out.update({"varepsilon": "\u03b5", "vartheta": "\u03b8", "varphi": "\u03c6", "varrho": "\u03c1",
                "varsigma": "\u03c3", "varpi": "\u03c0", "varkappa": "\u03ba"})
    return out


GREEK = _greek()
FUNCS = set("sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln exp lim liminf limsup max min sup "
            "inf det dim ker deg gcd arg Pr hom rank tr".split())
BB_MACROS = {"R", "N", "Z", "Q", "C"}
ACCENT_CMDS = {"tilde": "tilde", "widetilde": "tilde", "hat": "hat", "widehat": "hat", "bar": "bar",
               "overline": "bar", "widebar": "bar", "dot": "dot", "ddot": "ddot", "check": "check", "breve": "breve",
               "acute": "acute", "grave": "grave", "vec": "vec"}
BOUNDARY_CMDS = {"frac", "dfrac", "tfrac", "cfrac", "binom", "over", "atop", "choose", "sqrt", "cdot", "times",
                 "le", "ge", "leq", "geq", "neq", "ne", "in", "to", "mapsto", "pm", "mp"}
SKIP_GROUP = {"label", "ref", "eqref", "cite", "tag*"}
MATH_ENVS = r"equation|align|gather|multline|eqnarray|displaymath|math|flalign"


# ---------------------------------------------------------------- math scanning

def _group(s: str, i: int):
    """Argument starting at s[i]: ({...} group content, next index) or (one token, next index)."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 1, i + 1
        while j < len(s) and depth:
            depth += (s[j] == "{") - (s[j] == "}")
            j += 1
        return s[i + 1:j - 1], j
    if s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+|\\.", s[i:])
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def scan_math(s: str, accents: list | None = None) -> list:
    """Math source -> list of keys: normal-form characters, `x|bb` / `x|fr` for blackboard / fraktur, big-operator
    glyphs, and None for boundaries. Accent commands are recorded in `accents` as (kind, base keys)."""
    items: list = []
    s = re.sub(r"\}\s*\{", "} {", s)
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+\*?)", s[i:])
            if not m:                                              # \\ \, \; \{ ...
                items.append(None)
                i += 2
                continue
            cmd, i = m.group(1), i + m.end()
            if cmd in ("mathbb", "mathfrak"):
                arg, i = _group(s, i)
                for ch in arg:
                    k = norm(ch)
                    items.append(k + ("|bb" if cmd == "mathbb" else "|fr") if k.isalpha() else None)
            elif cmd in BB_MACROS:
                items.append(cmd.lower() + "|bb")
            elif cmd in ACCENT_CMDS:
                arg, i = _group(s, i)
                inner = scan_math(arg)
                if accents is not None:
                    accents.append((ACCENT_CMDS[cmd], "".join(k for k in inner if k)))
                items.extend(inner)
            elif cmd in GREEK:
                items.append(GREEK[cmd])
            elif cmd in FUNCS:
                items.extend(cmd)
            elif "\\" + cmd in BIGOP_CHAR:
                items.append(BIGOP_CHAR["\\" + cmd])
            elif cmd in ("begin", "end"):
                env, i = _group(s, i)
                if env.rstrip("*") in ("array", "tabular", "subarray"):
                    _, i = _group(s, i)
                items.append(None)
            elif cmd in SKIP_GROUP:
                _, i = _group(s, i)
                items.append(None)
            elif cmd == "tag":
                items.append(None)
            else:
                items.append(None)                                  # \frac, \left, \quad, unknown: a boundary
            continue
        if c.isalnum():
            for k in norm(c):
                if k.isalnum():
                    items.append(k)
        elif c in ".," :
            items.append(c)
        elif c in "_^{}$":
            pass
        else:
            items.append(None)
        i += 1
    return items


def math_runs(items: list) -> list:
    """Tier-1 tokens inside math: letter runs of 2+, digit runs (with a decimal point), split at boundaries."""
    runs, cur, kind = [], "", ""

    def flush():
        nonlocal cur, kind
        if cur and (kind == "d" or len(cur) >= 2):
            runs.append(cur)
        cur, kind = "", ""

    for idx, k in enumerate(items):
        if k is None:
            flush()
            continue
        b = k.split("|")[0]
        if k in ".,":
            nxt = items[idx + 1] if idx + 1 < len(items) else None
            if kind == "d" and nxt is not None and nxt.isdigit():
                cur += k
            else:
                flush()
        elif b.isdigit():
            if kind != "d":
                flush()
            cur, kind = cur + b, "d"
        elif b.isalpha():
            if kind != "a":
                flush()
            cur, kind = cur + b, "a"
        else:
            flush()
    flush()
    return runs


# ---------------------------------------------------------------- Markdown side

_MATH_RES = [re.compile(p, re.S) for p in (
    r"\$\$(.+?)\$\$", r"\\\[(.+?)\\\]", r"\\\((.+?)\\\)",
    r"\\begin\{(?:%s)\*?\}(.+?)\\end\{(?:%s)\*?\}" % (MATH_ENVS, MATH_ENVS), r"(?<![\\$])\$([^$\n]+?)\$(?!\$)")]


@dataclass
class Output:
    prose_tokens: list          # tier-1 tokens (words of 2+ letters, numbers) outside math, in order
    prose_singles: list         # tier-2 keys of one-letter prose words
    math_keys: list             # tier-2 keys of every math character / big operator
    math_bag: Counter           # tier-1 style runs found inside math (lenient match for layer words)
    accents: Counter            # (kind, base) -> count
    numbers: list               # prose numbers in order


def parse_markdown(md: str) -> Output:
    md = re.sub(r"(\w)-[ \t]*\n[ \t]*(?=[a-z])", r"\1", md)             # a word the parser left hyphen-broken
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]*)\]\((?:https?:|/|\.|#)[^)]*\)", r"\1", md)
    md = re.sub(r"<[^>\n]+>", " ", md)
    maths = []
    for rx in _MATH_RES:
        md = rx.sub(lambda m: maths.append(m.group(1)) or " ", md)
    accents: list = []
    keys: list = []
    bag: Counter = Counter()
    for m in maths:
        items = scan_math(m, accents)
        keys.extend(k for k in items if k and k not in ".,")
        bag.update(math_runs(items))
    tokens, singles, numbers = [], [], []
    for p in PIECE.findall(norm(md)):
        if p[0].isdigit():
            tokens.append(p)
            numbers.append(p)
        elif len(p) >= 2:
            tokens.append(p)
        else:
            singles.append(p)
    return Output(tokens, singles, keys, bag, Counter(accents), numbers)


# ---------------------------------------------------------------- layer side

def _glyph_pieces(w):
    """(piece, [glyph...]) for each letter run / number in a layer word, aligned with its glyphs."""
    text = w.text
    for m in PIECE.finditer(text):
        yield m.group(0), w.glyphs[m.start():m.end()]


def _key_ok(k: str) -> bool:
    return bool(k) and (k[0].isalnum() or k in BIGOP_CHAR.values())


@dataclass
class LayerBags:
    need1: Counter          # tier-1 tokens that must appear (margins and figure labels left out)
    all1: Counter           # every piece of every layer word (what an output token may map to)
    need2: Counter          # tier-2 glyph keys that must appear
    skip2: Counter          # tier-2 keys of margin / figure glyphs (the output may keep them)
    numbers: list           # tier-1 numbers in reading order
    accents: Counter


def _layer_accents(layer: PageLayer) -> Counter:
    out: Counter = Counter()
    glyphs = [g for g in layer.glyphs if g.char.strip()]
    for a in glyphs:
        kind = ACCENTS.get(a.char[0])
        if kind is None:
            continue
        acx, acy = (a.bbox[0] + a.bbox[2]) / 2, (a.bbox[1] + a.bbox[3]) / 2
        best, bd = None, None
        for b in glyphs:
            if b is a or ACCENTS.get(b.char[0]) or not b.char[0].isalnum():
                continue
            bcy, w = (b.bbox[1] + b.bbox[3]) / 2, b.bbox[2] - b.bbox[0]
            dx = abs((b.bbox[0] + b.bbox[2]) / 2 - acx)
            rise = bcy - acy
            if dx <= max(w, 1.0) * 0.75 and 0.2 * b.size <= rise <= 1.1 * b.size and (bd is None or dx < bd):
                best, bd = b, dx
        if best is not None:
            out[(kind, best.key)] += 1
    for r in layer.rules:
        if r.kind != "overline":
            continue
        under = [g for g in glyphs if g.char[0].isalnum() and min(g.bbox[2], r.bbox[2]) - max(g.bbox[0], r.bbox[0])
                 >= 0.5 * (g.bbox[2] - g.bbox[0]) and r.bbox[3] <= (g.bbox[1] + g.bbox[3]) / 2 <= r.bbox[3] + g.size * 1.2]
        covered = sum(min(g.bbox[2], r.bbox[2]) - max(g.bbox[0], r.bbox[0]) for g in under)
        if under and covered >= 0.7 * (r.bbox[2] - r.bbox[0]) and r.bbox[2] - r.bbox[0] < layer.width * 0.5:
            out[("bar", "".join(g.key for g in sorted(under, key=lambda g: g.bbox[0])))] += 1
    return out


def layer_bags(layer: PageLayer) -> LayerBags:
    need1, all1, need2, skip2 = Counter(), Counter(), Counter(), Counter()
    numbers: list = []
    for w in layer.words:
        exempt = layer.is_margin(w.bbox) or layer.in_figure(w.bbox)
        uniform = w.uniform
        covered = set()
        for piece, gl in _glyph_pieces(w):
            p = norm(piece)
            all1[p] += 1
            if uniform and (p[0].isdigit() or len(piece) >= 2):
                covered.update(id(g) for g in gl)
                if not exempt:
                    need1[p] += 1
                    if p[0].isdigit():
                        numbers.append(p)
        for g in w.glyphs:
            if id(g) in covered:
                continue
            k = g.key
            if _key_ok(k):
                (skip2 if exempt else need2)[k] += 1
    return LayerBags(need1, all1, need2, skip2, numbers, _layer_accents(layer))


# ---------------------------------------------------------------- comparison

def _pair(extra: Counter, missing: Counter):
    """Pair output words with layer words they most likely replaced (edit distance), return (pairs, extra, missing)."""
    ex, mi = list(extra.elements()), list(missing.elements())
    pairs = []
    cand = sorted(((difflib.SequenceMatcher(None, e, m).ratio(), e, m) for e in set(ex) for m in set(mi)),
                  key=lambda t: (-t[0], t[1], t[2]))
    for ratio, e, m in cand:
        if ratio < 0.6:
            break
        if e in ex and m in mi:
            ex.remove(e)
            mi.remove(m)
            pairs.append((e, m))
    return pairs, Counter(ex), Counter(mi)


def _fmt(c: Counter, limit: int = 8) -> str:
    items = [("%s x%d" % (k, v) if v > 1 else k) for k, v in sorted(c.items())]
    return ", ".join(items[:limit]) + (" ..." if len(items) > limit else "")


def _glyph_names(c: Counter) -> str:
    return _fmt(Counter({k.replace("|bb", " (blackboard)").replace("|fr", " (fraktur)"): v for k, v in c.items()}))


def reconcile_page(md: str, layer: PageLayer) -> list:
    """Flags for one page: [] means the Markdown is the page's own text, nothing more and nothing less."""
    out = parse_markdown(md)
    bags = layer_bags(layer)
    flags: list = []
    p = layer.page

    # tier 1: words and numbers
    prose = Counter(out.prose_tokens)
    matched = bags.need1 & prose
    rem_need = bags.need1 - matched
    extra = prose - bags.all1                       # output words no layer word can account for
    math_matched = rem_need & out.math_bag
    rem_need = rem_need - math_matched
    consumed = Counter()
    for tok, n in math_matched.items():
        for ch in tok:
            if ch.isalnum():
                consumed[ch] += n
    pairs, extra, rem_need = _pair(extra, rem_need)
    for e, m in sorted(pairs):
        flags.append(Flag("replaced", p, "'%s' where the PDF has '%s'" % (e, m), e))
    for w, n in sorted(extra.items()):
        flags.append(Flag("invented", p, "'%s' is not in the PDF page%s" % (w, " (x%d)" % n if n > 1 else ""), w))
    for w, n in sorted(rem_need.items()):
        flags.append(Flag("lost", p, "'%s' is in the PDF page but not in the output%s" % (w, " (x%d)" % n if n > 1 else ""), w))

    # tier 2: single glyphs (math letters, scripts, classes, big operators)
    got = Counter(k for k in out.math_keys if _key_ok(k)) + Counter(k for k in out.prose_singles if _key_ok(k))
    got = Counter({k: v - consumed.get(k, 0) for k, v in got.items() if v - consumed.get(k, 0) > 0})
    lost = bags.need2 - got
    invented = (got - bags.need2) - bags.skip2
    if lost:
        flags.append(Flag("lost-glyphs", p, "glyphs on the page but not in the output: " + _glyph_names(lost)))
    if invented:
        flags.append(Flag("invented-glyphs", p, "glyphs in the output but not on the page: " + _glyph_names(invented)))

    # accents, bars, dots, hats
    a_out, a_pdf = out.accents - bags.accents, bags.accents - out.accents
    for (kind, base), n in sorted(a_out.items()):
        mate = next((k for k in sorted(a_pdf) if k[0] == kind and a_pdf[k] > 0), None)
        if mate is not None:
            a_pdf[mate] -= 1
            flags.append(Flag("accent-moved", p, "\\%s on '%s' in the output, on '%s' in the PDF" % (kind, base, mate[1]), kind))
        else:
            flags.append(Flag("accent-added", p, "\\%s on '%s' is not in the PDF" % (kind, base), kind))
    for (kind, base), n in sorted(a_pdf.items()):
        if n > 0:
            flags.append(Flag("accent-lost", p, "the PDF has a %s on '%s', the output has none" % (kind, base), kind))

    # numbers keep their order: the output's prose numbers must read as a subsequence of the PDF's
    if out.numbers and not (Counter(out.numbers) - Counter(bags.numbers)):
        it = iter(bags.numbers)
        if not all(any(t == u for u in it) for t in out.numbers):
            flags.append(Flag("number-order", p, "numbers appear in a different order: PDF %s, output %s"
                              % (" ".join(bags.numbers[:6]), " ".join(out.numbers[:6]))))
    return flags


def reconcile_pages(pages_md: list, layers: list) -> dict:
    """{page number: [Flag]} for parallel lists of Markdown pages and layers."""
    if len(pages_md) != len(layers):
        raise ValueError("%d Markdown pages for %d PDF pages" % (len(pages_md), len(layers)))
    return {l.page: reconcile_page(md, l) for md, l in zip(pages_md, layers)}

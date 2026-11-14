"""Two transcripts of one page -> where they disagree.

Each Markdown page becomes one stream of small tokens that does not depend on LaTeX style or on where a reader drew the
line between prose and maths: letters and digits one by one, operators and symbols by one canonical name, scripts as
`_[ ... ]` / `^[ ... ]` (subscript first), fractions as `frac[ ][ ]`, accents as `acc:bar[ ]`. Spacing, sizing commands,
alignment, punctuation and Markdown markup are dropped. Two streams are aligned; every stretch that differs is a
Disagreement that points back at the source characters of both pages.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------- symbol names

GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
         "eta": "η", "theta": "θ", "vartheta": "θ", "iota": "ι", "kappa": "κ", "varkappa": "κ", "lambda": "λ", "mu": "μ",
         "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "π", "rho": "ρ", "varrho": "ρ", "sigma": "σ", "varsigma": "ς",
         "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ",
         "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ",
         "Psi": "Ψ", "Omega": "Ω"}
SYMBOL = {
    "le": "≤", "leq": "≤", "leqslant": "≤", "ge": "≥", "geq": "≥", "geqslant": "≥", "ne": "≠", "neq": "≠",
    "ll": "≪", "gg": "≫", "approx": "≈", "sim": "∼", "simeq": "≃", "cong": "≅", "equiv": "≡", "propto": "∝",
    "asymp": "≍", "lesssim": "≲", "gtrsim": "≳", "prec": "≺", "succ": "≻", "preceq": "⪯", "succeq": "⪰",
    "to": "→", "rightarrow": "→", "longrightarrow": "→", "gets": "←", "leftarrow": "←", "longleftarrow": "←",
    "mapsto": "↦", "longmapsto": "↦", "leftrightarrow": "↔", "Rightarrow": "⇒", "implies": "⇒", "Longrightarrow": "⇒",
    "Leftarrow": "⇐", "impliedby": "⇐", "Leftrightarrow": "⇔", "iff": "⇔", "Longleftrightarrow": "⇔", "uparrow": "↑",
    "downarrow": "↓", "hookrightarrow": "↪", "rightharpoonup": "⇀", "rightsquigarrow": "⇝", "leadsto": "⇝",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "subsetneq": "⊊", "supsetneq": "⊋", "cup": "∪", "cap": "∩", "bigcup": "∪", "bigcap": "∩", "sqcup": "⊔",
    "bigsqcup": "⊔", "setminus": "∖", "backslash": "∖", "smallsetminus": "∖", "emptyset": "∅", "varnothing": "∅",
    "times": "×", "cdot": "·", "centerdot": "·", "bullet": "•", "circ": "∘", "ast": "*", "star": "⋆", "div": "÷",
    "pm": "±", "mp": "∓", "oplus": "⊕", "bigoplus": "⊕", "otimes": "⊗", "bigotimes": "⊗", "odot": "⊙", "bigodot": "⊙",
    "ominus": "⊖", "wedge": "∧", "land": "∧", "bigwedge": "∧", "vee": "∨", "lor": "∨", "bigvee": "∨", "neg": "¬",
    "lnot": "¬", "forall": "∀", "exists": "∃", "nexists": "∄", "infty": "∞", "partial": "∂", "nabla": "∇",
    "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬", "oint": "∮", "ell": "ℓ", "hbar": "ℏ",
    "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "wp": "℘", "angle": "∠", "triangle": "△", "triangleq": "≜", "coloneqq": "≔",
    "doteq": "≐", "perp": "⊥", "bot": "⊥", "top": "⊤", "parallel": "∥", "vdash": "⊢", "dashv": "⊣", "models": "⊨",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉", "lbrace": "{", "rbrace": "}",
    "lbrack": "[", "rbrack": "]", "vert": "|", "lvert": "|", "rvert": "|", "mid": "|", "Vert": "‖", "lVert": "‖",
    "rVert": "‖", "cdots": "…", "ldots": "…", "dots": "…", "dotsc": "…", "dotsb": "…", "dotsm": "…", "vdots": "⋮",
    "ddots": "⋱", "prime": "′", "dagger": "†", "ddagger": "‡", "flat": "♭", "sharp": "♯", "natural": "♮",
    "square": "□", "Box": "□", "blacksquare": "■", "qed": "□", "diamond": "⋄", "colon": ":", "S": "§", "P": "¶",
    "copyright": "©", "pounds": "£", "checkmark": "✓", "lesssim ": "≲", "nmid": "∤", "nsubseteq": "⊈", "top ": "⊤",
    "dag": "†", "amalg": "⨿", "wr": "≀", "bowtie": "⋈", "ltimes": "⋉", "rtimes": "⋊", "nleq": "≰", "ngeq": "≱",
    "nsim": "≁", "ncong": "≇", "lhd": "⊲", "rhd": "⊳", "unlhd": "⊴", "unrhd": "⊵", "therefore": "∴", "because": "∵",
    "complement": "∁", "imath": "ı", "jmath": "ȷ", "eth": "ð", "mho": "℧", "Finv": "Ⅎ", "beth": "ℶ", "gimel": "ℷ",
    "lq": "", "rq": "", "%": "%", "&": "&", "#": "#", "$": "$", "_": "_"}
UNI = {"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-", "‒": "-", "∣": "|", "∥": "‖", "‖": "‖", "⋯": "…", "...": "…",
       "ϵ": "ε", "ϕ": "φ", "ϑ": "θ", "ϱ": "ρ", "ϖ": "π", "∗": "*", "⋅": "·", "∙": "·", "′": "′", "〈": "⟨", "〉": "⟩",
       "⩽": "≤", "⩾": "≥", "≦": "≤", "≧": "≥", "∶": ":", "∼": "∼", "˜": "~", "⟶": "→", "⟵": "←", "⟹": "⇒", "⟺": "⇔",
       "⋃": "∪", "⋂": "∩", "⨁": "⊕", "⨂": "⊗", "⋁": "∨", "⋀": "∧", "∖": "∖", "Σ": "Σ", "Π": "Π", "∆": "Δ", "∅": "∅",
       "⊤": "⊤", "⊺": "⊤", "ℝ": "R|bb", "ℕ": "N|bb", "ℤ": "Z|bb", "ℚ": "Q|bb", "ℂ": "C|bb", "𝔼": "E|bb", "ℙ": "P|bb",
       "𝟙": "1|bb", "★": "⋆", "☆": "⋆", "∎": "□", "■": "□", "▢": "□", "◻": "□", "□": "□", "ﬁ": "fi", "ﬂ": "fl"}
FUNCS = set("sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh coth log ln lg exp lim liminf limsup max min sup "
            "inf arg det dim ker deg gcd hom Pr mod bmod pmod sgn tr Tr rank span diag supp argmax argmin var Var cov "
            "Cov poly polylog sign erf vol conv dist diam card im id Id ess esssup essinf injlim projlim".split())
BOLD = {"mathbf", "boldsymbol", "pmb", "bm", "mathbfit", "bf", "boldmath", "textbf", "bfseries", "symbf", "mathbfcal"}
CAL = {"mathcal": "c", "mathscr": "c", "cal": "c", "mathbb": "bb", "Bbb": "bb", "mathds": "bb", "mathbbm": "bb",
       "mathfrak": "fr", "frak": "fr", "symcal": "c", "symbb": "bb"}
PLAIN = {"mathrm", "text", "textrm", "textit", "textsf", "texttt", "textsc", "textup", "textnormal", "mathit", "mathsf",
         "mathtt", "mathnormal", "operatorname", "operatorname*", "mbox", "hbox", "emph", "rm", "it", "sf", "tt",
         "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle", "mathop", "mathrel", "mathbin", "mathord",
         "mathpunct", "mathopen", "mathclose", "mathinner", "unsure", "ensuremath", "boxed", "fbox", "smash", "small",
         "large", "Large", "normalsize", "footnotesize", "tiny", "scriptsize", "mathstrut", "strut", "noindent",
         "underbrace", "overbrace", "underset", "overset", "stackrel", "substack", "limits", "nolimits", "middle",
         "left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr",
         "bigm", "Bigm", "biggm", "Biggm", "quad", "qquad", "enspace", "enskip", "thinspace", "medspace", "thickspace",
         "negthinspace", "negmedspace", "negthickspace", "nonumber", "notag", "hfill", "hline", "cr", "allowbreak",
         "displaylimits", "relax", "protect", "centering", "break", "newline", "par", "indent", "space", "nobreak",
         "nobreakspace", "lefteqn", "mathsmaller", "mathlarger", "bigstrut", "kern", "mkern", "mskip", "hskip", "vskip"}
DROP_ARG = {"label", "vspace", "hspace", "vspace*", "hspace*", "phantom", "vphantom", "hphantom", "ref", "eqref", "cite",
            "color", "textcolor", "rule", "raisebox", "footnotemark", "pagestyle", "thispagestyle", "bibitem"}
ACCENT = {"bar": "bar", "overline": "bar", "hat": "hat", "widehat": "hat", "tilde": "tilde", "widetilde": "tilde",
          "vec": "vec", "overrightarrow": "vec", "overleftarrow": "lvec", "dot": "dot", "ddot": "ddot", "check": "check",
          "breve": "breve", "acute": "acute", "grave": "grave", "underline": "under", "underbar": "under",
          "mathring": "ring", "widecheck": "check", "overleftrightarrow": "lrvec"}
MARKS = {"\u0303": "tilde", "\u0302": "hat", "\u0304": "bar", "\u0305": "bar", "\u0307": "dot", "\u0308": "ddot",
         "\u20d7": "vec", "\u030c": "check", "\u0306": "breve", "\u0301": "acute", "\u0300": "grave", "\u030a": "ring",
         "\u00af": "bar", "\u02c9": "bar", "\u02c6": "hat", "\u02dc": "tilde", "\u02d9": "dot", "\u00a8": "ddot"}
QUIET_ENVS = {"array", "aligned", "align", "align*", "split", "gathered", "gather", "gather*", "equation", "equation*",
              "multline", "multline*", "eqnarray", "eqnarray*", "alignedat", "alignat", "alignat*", "flalign",
              "flalign*", "subarray", "displaymath", "math", "center", "tabular"}
MATRIX_ENVS = {"pmatrix": "()", "bmatrix": "[]", "Bmatrix": "{}", "vmatrix": "||", "Vmatrix": "‖‖", "matrix": ("", ""),
               "smallmatrix": ("", ""), "cases": ("{", ""), "dcases": ("{", ""), "rcases": ("", "}")}
COLSPEC_ENVS = {"array", "tabular", "subarray", "alignedat", "alignat", "alignat*"}
TWO_ARG = {"frac": "frac", "dfrac": "frac", "tfrac": "frac", "cfrac": "frac", "binom": "binom", "dbinom": "binom",
           "tbinom": "binom"}


@dataclass
class Tok:
    key: str            # what is aligned (bold dropped, prose and text letters case-folded)
    strict: str         # the same with bold kept and the case as written
    math: bool
    a: int              # source characters [a, b)
    b: int


# ---------------------------------------------------------------- LaTeX -> tree

def _lex(s: str, off: int) -> list:
    """[(kind, value, start, end)] with kind in cmd / ch / lb / rb."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+\*?)", s[i:])
            if m:
                out.append(("cmd", m.group(1), off + i, off + i + m.end()))
                i += m.end()
                continue
            nxt = s[i + 1:i + 2]
            if nxt == "\\":
                out.append(("cmd", "\\", off + i, off + i + 2))
            elif nxt and nxt in "{}|%&#$_":
                out.append(("ch", {"|": "‖"}.get(nxt, nxt) if nxt != "{" and nxt != "}" else nxt, off + i, off + i + 2))
                if nxt in "{}":
                    out[-1] = ("esc", nxt, off + i, off + i + 2)
            # \, \; \! \: \  and anything else: spacing, dropped
            i += 2
            continue
        if c == "{":
            out.append(("lb", c, off + i, off + i + 1))
        elif c == "}":
            out.append(("rb", c, off + i, off + i + 1))
        elif not c.isspace() and c != "~":
            out.append(("ch", c, off + i, off + i + 1))
        i += 1
    return out


MAX_DEPTH = 150


def _tree(lx: list, i: int = 0, stop: str = "", depth: int = 0) -> tuple:
    """Nodes: a lexeme tuple, or ("grp", [nodes], start, end). Braces nested deeper than MAX_DEPTH are read as flat."""
    nodes = []
    while i < len(lx):
        k = lx[i]
        if k[0] == "rb":
            if stop == "rb":
                return nodes, i + 1
            i += 1                                                  # a stray brace
            continue
        if k[0] == "lb" and depth >= MAX_DEPTH:
            i += 1
            continue
        if k[0] == "lb":
            inner, j = _tree(lx, i + 1, "rb", depth + 1)
            end = lx[j - 1][3] if j - 1 < len(lx) else k[3]
            nodes.append(("grp", inner, k[2], end))
            i = j
            continue
        nodes.append(k)
        i += 1
    return nodes, i


class _Emit:
    def __init__(self):
        self.toks: list = []

    def add(self, key: str, a: int, b: int, math: bool = True, bold: bool = False, fold: bool = False):
        if not key:
            return
        strict = key + ("|b" if bold and key[:1].isalnum() else "")
        if fold and len(key) == 1:
            key = key.lower()
            strict = key
        self.toks.append(Tok(key, strict, math, a, b))


def _char_keys(c: str) -> list:
    """Canonical keys of one source character (letters, digits, symbols); [] for what is dropped."""
    if c in UNI:
        v = UNI[c]
        return [v] if "|" in v or len(v) == 1 else list(v)
    d = unicodedata.normalize("NFKD", c)
    base = [x for x in d if not unicodedata.combining(x)]
    out = []
    for x in base:
        if x in UNI:
            out.append(UNI[x])
        elif x.isalnum():
            name = unicodedata.name(x, "")
            if "MATHEMATICAL" in name:                                # 𝒯 𝐰 𝔽: styled alphanumerics
                x2 = unicodedata.normalize("NFKC", x)
                tag = "|c" if ("SCRIPT" in name or "CALLIGRAPHIC" in name) else "|bb" if "DOUBLE-STRUCK" in name \
                    else "|fr" if "FRAKTUR" in name else "|b" if "BOLD" in name else ""
                out.append(x2 + tag)
            else:
                out.append(x)
        elif not x.isspace() and x not in "\"'`‘’“”´":
            out.append(x)
    return out


def _walk(nodes: list, em: _Emit, bold: bool = False, style: str = "", fold: bool = False) -> None:
    """Emit the canonical tokens of a node list. `style` is c / bb / fr; `fold` lower-cases (text inside \\text)."""
    i, n = 0, len(nodes)

    def atom(j):                                                    # the argument at j as a node list
        if j >= n:
            return [], j
        nd = nodes[j]
        if nd[0] == "grp":
            return nd[1], j + 1
        return [nd], j + 1

    def span(j):
        return (nodes[j][2], nodes[j][3]) if j < n else (nodes[-1][3], nodes[-1][3])

    while i < n:
        nd = nodes[i]
        kind = nd[0]
        if kind == "grp":
            _walk(nd[1], em, bold, style, fold)
            i += 1
        elif kind == "esc":
            em.add(nd[1], nd[2], nd[3])
            i += 1
        elif kind == "ch":
            c = nd[1]
            if c in "_^'":
                i = _scripts(nodes, i, em, bold, style, fold)
                continue
            if c in ",;.":
                # punctuation is dropped, except a decimal point between digits
                prev_digit = bool(em.toks) and em.toks[-1].key.isdigit()
                nxt = nodes[i + 1] if i + 1 < n else None
                if c == "." and prev_digit and nxt and nxt[0] == "ch" and nxt[1].isdigit():
                    em.add(".", nd[2], nd[3])
                i += 1
                continue
            if c in "&:!?\"`":
                i += 1
                continue
            for key in _char_keys(c):
                if key in MARKS.values():
                    continue
                if style and key[:1].isalnum() and "|" not in key:
                    key = key + "|" + style
                em.add(key, nd[2], nd[3], bold=bold, fold=fold and key.isalpha())
            comb = [MARKS[x] for x in unicodedata.normalize("NFD", c)[1:] if x in MARKS]
            for k in comb:                                           # a precomposed accent: acc after its letter
                em.add("acc:" + k, nd[2], nd[3])
            if c in MARKS and not c.isalnum():                       # a spacing accent glyph after its letter (w¯)
                em.add("acc:" + MARKS[c], nd[2], nd[3])
            i += 1
        else:                                                        # a command
            cmd = nd[1]
            if cmd in BOLD:
                arg, j = atom(i + 1) if (i + 1 < n and nodes[i + 1][0] == "grp") else (nodes[i + 1:], n)
                _walk(arg, em, True, style, fold or cmd == "textbf")
                i = j
            elif cmd in CAL:
                arg, j = atom(i + 1)
                _walk(arg, em, bold, CAL[cmd], fold)
                i = j
            elif cmd in ("text", "textrm", "textit", "textsf", "texttt", "textsc", "textup", "textnormal", "mbox", "hbox",
                         "emph", "mathrm", "operatorname", "operatorname*", "mathsf", "mathtt", "mathit"):
                arg, j = atom(i + 1)
                multi = sum(1 for x in arg if x[0] == "ch" and x[1].isalpha()) > 1
                _walk(arg, em, bold, style, fold or multi)
                i = j
            elif cmd in PLAIN or cmd == "\\":
                i += 1
            elif cmd in DROP_ARG:
                _, i = atom(i + 1)
            elif cmd in TWO_ARG:
                a1, j = atom(i + 1)
                a2, j = atom(j)
                em.add(TWO_ARG[cmd] + "[", nd[2], nd[3])
                _walk(a1, em, bold, style, fold)
                em.add("][", nd[3], nd[3])
                _walk(a2, em, bold, style, fold)
                em.add("]", nd[3], nd[3])
                i = j
            elif cmd == "sqrt":
                j = i + 1
                idx = []
                if j < n and nodes[j][0] == "ch" and nodes[j][1] == "[":
                    k = j + 1
                    while k < n and not (nodes[k][0] == "ch" and nodes[k][1] == "]"):
                        idx.append(nodes[k])
                        k += 1
                    j = k + 1
                arg, j = atom(j)
                em.add("sqrt[", nd[2], nd[3])
                if idx:
                    _walk(idx, em, bold, style, fold)
                    em.add("][", nd[3], nd[3])
                _walk(arg, em, bold, style, fold)
                em.add("]", nd[3], nd[3])
                i = j
            elif cmd in ACCENT:
                arg, j = atom(i + 1)
                _walk(arg, em, bold, style, fold)
                em.add("acc:" + ACCENT[cmd], nd[2], nd[3])
                i = j
            elif cmd in ("begin", "end"):
                arg, j = atom(i + 1)
                env = "".join(x[1] for x in arg if x[0] == "ch")
                if cmd == "begin" and env in COLSPEC_ENVS and j < n and nodes[j][0] == "grp":
                    j += 1
                if env in MATRIX_ENVS:
                    em.add(MATRIX_ENVS[env][0 if cmd == "begin" else 1], nd[2], nd[3])
                elif env not in QUIET_ENVS:
                    em.add("%s:%s" % (cmd, env.rstrip("*")), nd[2], nd[3])
                i = j
            elif cmd == "tag" or cmd == "tag*":
                arg, j = atom(i + 1)
                em.add("tag[", nd[2], nd[3])
                _walk([x for x in arg if not (x[0] == "ch" and x[1] in "()")], em)
                em.add("]", nd[3], nd[3])
                i = j
            elif cmd == "not":
                em.add("not", nd[2], nd[3])
                i += 1
            elif cmd in GREEK:
                em.add(GREEK[cmd], nd[2], nd[3], bold=bold)
                i += 1
            elif cmd in SYMBOL:
                em.add(SYMBOL[cmd], nd[2], nd[3])
                i += 1
            elif cmd in FUNCS or cmd.rstrip("*") in FUNCS:
                for ch in cmd.rstrip("*"):
                    em.add(ch.lower(), nd[2], nd[3])
                i += 1
            else:
                em.add("\\" + cmd, nd[2], nd[3])
                i += 1


def _scripts(nodes: list, i: int, em: _Emit, bold: bool, style: str, fold: bool) -> int:
    """Consecutive scripts and primes on one base, emitted subscript first: `_[ .. ]` then `^[ .. ]`."""
    n = len(nodes)
    sub: list = []
    sup: list = []
    primes: list = []
    first = nodes[i]
    while i < n and nodes[i][0] == "ch" and nodes[i][1] in "_^'":
        c = nodes[i][1]
        if c == "'":
            primes.append(nodes[i])
            i += 1
            continue
        if i + 1 >= n:
            i += 1
            break
        arg = nodes[i + 1]
        (sub if c == "_" else sup).append(arg)
        i += 2
    if sub:
        em.add("_[", first[2], first[3])
        for a in sub:
            _walk(a[1] if a[0] == "grp" else [a], em, bold, style, fold)
        em.add("]", first[3], first[3])
    if sup or primes:
        em.add("^[", first[2], first[3])
        for p in primes:
            em.add("′", p[2], p[3])
        for a in sup:
            _walk(a[1] if a[0] == "grp" else [a], em, bold, style, fold)
        em.add("]", first[3], first[3])
    return i


def math_tokens(src: str, off: int = 0) -> list:
    em = _Emit()
    nodes, _ = _tree(_lex(src, off))
    _walk(nodes, em)
    return em.toks


SMALL = 4


def kept(old: str, new: str) -> float:
    """The share of `old`'s content tokens that `new` still has, in order (1.0 = everything kept, with or without
    additions; also 1.0 when `old` has fewer than SMALL of them). A replacement that keeps little of what it replaces is
    about some other place of the page."""
    def content(md):                                                # letters, digits, symbols: not brackets or accents
        return [t.key.lower() for t in page_tokens(md)[0] if not (t.key.endswith("[") or t.key in ("]", "][")
                                                                    or t.key.startswith("acc:"))]
    a, b = content(old), content(new)
    if len(a) < SMALL:
        return 1.0                                                  # too short to tell: one symbol is the whole formula
    same = sum(blk.size for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return same / len(a)


def dollars(text: str) -> int:
    """Unescaped `$` signs in `text`: a replacement that changes their parity would break every formula after it."""
    return len(re.findall(r"(?<!\\)\$", text))


# ---------------------------------------------------------------- Markdown page -> tokens

_MATH = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\$])\$([^$\n]+?)\$(?!\$)", re.S)
_DROP = re.compile(r"!\[[^\]]*\]\([^)]*\)|</?[A-Za-z][^<>\n$]*?>|^[ \t]*#{1,6}[ \t]+|^[ \t]*[-*+][ \t]+(?=\S)|\*\*|__|"
                   r"(?<![\w\\])[*_](?=\w)|(?<=\w)[*_](?![\w{])|^[ \t]*>[ \t]?|\\unsure(?=\{)|^```\w*[ \t]*$", re.M)


@dataclass
class Span:
    a: int
    b: int
    display: bool


def page_tokens(md: str) -> tuple:
    """(tokens, math spans) of a Markdown page."""
    toks: list = []
    spans: list = []
    pos = 0
    for m in _MATH.finditer(md):
        toks += _prose(md, pos, m.start())
        g = next(i for i in range(1, 5) if m.group(i) is not None)
        spans.append(Span(m.start(), m.end(), g in (1, 2)))
        toks += math_tokens(m.group(g), m.start(g))
        pos = m.end()
    toks += _prose(md, pos, len(md))
    return toks, spans


def _prose(md: str, a: int, b: int) -> list:
    """Prose characters as tokens: letters of a word of two or more are case-folded, a lone letter keeps its case."""
    out: list = []
    text = md[a:b]
    keep = [True] * len(text)
    for m in _DROP.finditer(text):
        for i in range(m.start(), m.end()):
            keep[i] = False
    for m in re.finditer(r"\\unsure\s*\{", text):                    # the reader's wrapper: its braces are not content
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        for i in list(range(m.start(), m.end())) + ([j - 1] if not depth else []):
            keep[i] = False
    i, n = 0, len(text)
    while i < n:
        if not keep[i]:
            i += 1
            continue
        c = text[i]
        if c == "-" and i + 1 < n and text[i + 1] == "\n" and i > 0 and text[i - 1].isalpha():   # hyphen at a line end
            i += 2
            continue
        if c.isalpha():
            j = i
            while j < n and keep[j] and text[j].isalpha():
                j += 1
            word = text[i:j]
            for k, ch in enumerate(word):
                keys = _char_keys(ch)
                for key in keys:
                    if len(word) > 1 and key.isalpha():
                        key = key.lower()
                    out.append(Tok(key, key, False, a + i + k, a + i + k + 1))
                for x in unicodedata.normalize("NFD", ch)[1:]:
                    if x in MARKS and len(word) == 1:
                        out.append(Tok("acc:" + MARKS[x], "acc:" + MARKS[x], False, a + i + k, a + i + k + 1))
            i = j
            continue
        if c in MARKS and out:                                          # w¯ left in prose by a reader
            out.append(Tok("acc:" + MARKS[c], "acc:" + MARKS[c], False, a + i, a + i + 1))
            i += 1
            continue
        if c in ",;.:!?\"'`‘’“”&\\_^~#*" or c.isspace():
            if c == "." and out and out[-1].key.isdigit() and out[-1].b == a + i and i + 1 < n and text[i + 1].isdigit():
                out.append(Tok(".", ".", False, a + i, a + i + 1))
            i += 1
            continue
        for key in _char_keys(c):
            out.append(Tok(key, key, False, a + i, a + i + 1))
        i += 1
    return out



# ---------------------------------------------------------------- compare

@dataclass
class Disagreement:
    kind: str            # differ / style (bold only) / case
    a_span: tuple        # source characters in page A
    b_span: tuple
    a_text: str          # canonical tokens of each side
    b_text: str
    a_math: bool = True
    b_math: bool = True


def _src_span(toks: list, i: int, j: int, n_src: int) -> tuple:
    if i < j:
        return (min(t.a for t in toks[i:j]), max(t.b for t in toks[i:j]))
    at = toks[i - 1].b if i > 0 else (toks[0].a if toks else 0)
    return (min(at, n_src), min(at, n_src))


def _blank_tags(md: str) -> str:
    """`<eq>` wrappers a parser leaves inside table cells, blanked in place so offsets stay true."""
    return re.sub(r"</?eq>", lambda m: " " * len(m.group(0)), md)


@dataclass
class Alignment:
    md_a: str
    md_b: str
    ta: list
    tb: list
    opcodes: list
    disagreements: list

    def b_to_a(self, pos: int) -> int:
        """The character of page A that lines up with character `pos` of page B (the nearest aligned token)."""
        if not self.tb or not self.ta:
            return 0
        j = min(range(len(self.tb)), key=lambda k: abs(self.tb[k].a - pos))
        for op, i1, i2, j1, j2 in self.opcodes:
            if j1 <= j < j2 or (j1 == j2 == j):
                if op == "equal":
                    return self.ta[i1 + (j - j1)].a
                return self.ta[min(i1, len(self.ta) - 1)].a
        return self.ta[-1].a


def align(md_a: str, md_b: str) -> Alignment:
    """Line the two pages up token by token and list where they differ. A is the witness, B the transcript."""
    md_a, md_b = _blank_tags(md_a), _blank_tags(md_b)
    ta, _ = page_tokens(md_a)
    tb, _ = page_tokens(md_b)
    fa, fb = [t.key.lower() for t in ta], [t.key.lower() for t in tb]       # case is checked after the alignment
    ops = difflib.SequenceMatcher(None, fa, fb, autojunk=False).get_opcodes()
    out: list = []
    for op, i1, i2, j1, j2 in ops:
        if op != "equal":
            out.append(Disagreement("differ", _src_span(ta, i1, i2, len(md_a)), _src_span(tb, j1, j2, len(md_b)),
                                    " ".join(t.strict for t in ta[i1:i2]), " ".join(t.strict for t in tb[j1:j2]),
                                    any(t.math for t in ta[i1:i2]) or i1 == i2,
                                    any(t.math for t in tb[j1:j2]) or j1 == j2))
            continue
        run = None                                                   # [kind, start, end) over A's tokens
        for d in range(i2 - i1):
            x, y = ta[i1 + d], tb[j1 + d]
            kind = ""
            if x.math and y.math and x.key != y.key:
                kind = "case"
            elif x.math and y.math and x.strict != y.strict:
                kind = "style"
            if kind and run and run[0] == kind and run[2] == i1 + d:
                run[2] += 1
                continue
            if run:
                out.append(_run(run, ta, tb, i1, j1, md_a, md_b))
            run = [kind, i1 + d, i1 + d + 1] if kind else None
        if run:
            out.append(_run(run, ta, tb, i1, j1, md_a, md_b))
    return Alignment(md_a, md_b, ta, tb, ops, out)


def compare(md_a: str, md_b: str) -> list:
    return align(md_a, md_b).disagreements


def _run(run, ta, tb, i1, j1, md_a, md_b):
    kind, s, e = run
    js, je = j1 + (s - i1), j1 + (e - i1)
    return Disagreement(kind, _src_span(ta, s, e, len(md_a)), _src_span(tb, js, je, len(md_b)),
                        " ".join(t.strict for t in ta[s:e]), " ".join(t.strict for t in tb[js:je]))

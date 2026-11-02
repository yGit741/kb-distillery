"""The truth: every glyph of a PDF page with its font, size and box, plus the ruled lines, from PDFium (pypdfium2).

`read_page` / `read_pdf` give `PageLayer`s; words are runs of glyphs between spaces, hyphen-broken words are joined
across lines, and NUL / control codes never survive. Fonts map to the LaTeX class they stand for (MSBM -> mathbb,
EUFM -> mathfrak, CMEX -> big operators), see `font_class` and `glyph_latex`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MARGIN = 0.07                     # top / bottom band (fraction of page height): running heads and page numbers
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f￾￿]")
ACCENTS = {                       # accent glyph -> kind (what a parser should render as \tilde, \hat, ...)
    "~": "tilde", "˜": "tilde", "∼": "tilde", "̃": "tilde",
    "^": "hat", "ˆ": "hat", "̂": "hat",
    "¯": "bar", "ˉ": "bar", "̄": "bar", "‾": "bar",
    "·": "dot", "˙": "dot", "̇": "dot",
    "¨": "ddot", "̈": "ddot",
    "ˇ": "check", "̌": "check", "˘": "breve", "̆": "breve",
    "´": "acute", "́": "acute", "`": "grave", "̀": "grave",
    "⃗": "vec", "→": "vec", "⃖": "vecl", "←": "vecl",         # an arrow raised above a base is an accent (\vec)
}
# font-name stem (CM / AMS / Euler families) -> LaTeX class
_FONT_CLASSES = (
    ("msbm", "mathbb"), ("msam", "symbol"), ("eufm", "mathfrak"), ("eusm", "mathscr"), ("eurm", "roman"),
    ("cmex", "bigop"), ("lmmathextension", "bigop"), ("cmsy", "symbol"), ("cmmi", "mathit"), ("cmbx", "mathbf"), ("cmbsy", "mathbf"),
    ("cmr", "roman"), ("cmss", "sans"), ("cmtt", "mono"), ("cmti", "textit"), ("cmsl", "textit"), ("cmcsc", "roman"),
    ("lmmath", "mathit"), ("mathit", "mathit"), ("math", "mathit"),
)
MATH_CLASSES = {"mathbb", "mathfrak", "mathscr", "bigop", "symbol", "mathit", "mathbf"}
# CMEX10 codes -> big operator (text size and display size share an operator)
CMEX_BIGOP = {0x50: "\\sum", 0x58: "\\sum", 0x51: "\\prod", 0x59: "\\prod", 0x52: "\\int", 0x5A: "\\int",
              0x53: "\\bigcup", 0x5B: "\\bigcup", 0x54: "\\bigcap", 0x5C: "\\bigcap", 0x55: "\\bigsqcup",
              0x5D: "\\bigsqcup", 0x57: "\\bigvee", 0x5F: "\\bigvee", 0x56: "\\bigwedge", 0x5E: "\\bigwedge",
              0x4C: "\\bigoplus", 0x4D: "\\bigoplus", 0x4E: "\\bigotimes", 0x4F: "\\bigotimes"}
BIGOP_CHAR = {"\\sum": "∑", "\\prod": "∏", "\\int": "∫", "\\bigcup": "⋃", "\\bigcap": "⋂",
              "\\bigsqcup": "⨆", "\\bigvee": "⋁", "\\bigwedge": "⋀", "\\bigoplus": "⨁",
              "\\bigotimes": "⨂"}
UNI_BIGOP = {v: k for k, v in BIGOP_CHAR.items()}
BAR_CHARS = {"|": "|", "\u2223": "|", "\u2225": "\u2016", "\u2016": "\u2016"}      # single / double vertical bar glyphs
BARS = set(BAR_CHARS.values())


def font_class(fontname: str) -> str:
    """LaTeX class of a PDF font name: `ABCDEF+MSBM10` -> mathbb, `CMEX10` -> bigop, anything else -> text."""
    name = re.sub(r"^[A-Z]{6}\+", "", fontname or "").lower()
    name = re.sub(r"[^a-z]", "", name)
    for stem, cls in _FONT_CLASSES:
        if name.startswith(stem) or (stem in ("mathit", "math") and stem in name):
            return cls
    return "text"


def clean(text: str) -> str:
    """Drop NUL and other control codes (they come out of broken CID maps)."""
    return CONTROL.sub("", text or "")


def glyph_latex(char: str, cls: str) -> str:
    """The LaTeX a glyph stands for: R in MSBM is \\mathbb{R}, code 0x58 in CMEX is \\sum, else the character."""
    if cls == "mathbb" and char.isalpha():
        return "\\mathbb{%s}" % char
    if cls == "mathfrak" and char.isalpha():
        return "\\mathfrak{%s}" % char
    if cls == "bigop" and len(char) == 1 and ord(char) in CMEX_BIGOP:
        return CMEX_BIGOP[ord(char)]
    return char


@dataclass
class Glyph:
    char: str                      # the character as the PDF encodes it (control codes already stripped)
    font: str
    size: float
    bbox: tuple                    # x0, y0, x1, y1 in points, y down
    cls: str = "text"

    @property
    def latex(self) -> str:
        return glyph_latex(self.char, self.cls)

    @property
    def key(self) -> str:
        """Normal form shared with `reconcile`: lower-case NFKC, \\mathbb / \\mathfrak kept as a class suffix."""
        if not self.char:
            return ""
        if self.cls == "bigop":                      # extension-font codes: operators, or delimiter pieces (no key)
            return BIGOP_CHAR[CMEX_BIGOP[ord(self.char[0])]] if ord(self.char[0]) in CMEX_BIGOP else ""
        if self.char in BAR_CHARS:
            return BAR_CHARS[self.char]
        c = unicodedata.normalize("NFKC", self.char.replace("\u2206", "\u0394")).casefold()      # INCREMENT is Delta
        if self.cls in ("mathbb", "mathfrak") and c.isalpha():
            return c + ("|bb" if self.cls == "mathbb" else "|fr")
        return c


@dataclass
class Word:
    text: str
    bbox: tuple
    glyphs: list = field(default_factory=list)
    line: int = 0
    block: int = 0

    @property
    def uniform(self) -> bool:
        """One font class, one size (within half a point): a prose word, not a base with a script on it."""
        if not self.glyphs:
            return False
        sizes = [g.size for g in self.glyphs]
        return max(sizes) - min(sizes) < 0.5 and len({g.cls for g in self.glyphs}) == 1 \
            and self.glyphs[0].cls not in MATH_CLASSES


@dataclass
class Rule:
    bbox: tuple
    kind: str = "rule"             # fraction | overline | underline | radical | rule (no text beside it)


@dataclass
class PageLayer:
    page: int                      # 1-based
    width: float
    height: float
    glyphs: list = field(default_factory=list)
    words: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    vrules: list = field(default_factory=list)       # thin vertical strokes tall enough to be a drawn delimiter bar
    figures: list = field(default_factory=list)      # image boxes (labels inside them belong to the figure)

    def is_margin(self, bbox) -> bool:
        y0, y1 = bbox[1], bbox[3]
        return y1 < self.height * MARGIN or y0 > self.height * (1 - MARGIN)

    def in_figure(self, bbox) -> bool:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        return any(f[0] <= cx <= f[2] and f[1] <= cy <= f[3] for f in self.figures)

    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _words_of_line(glyphs: list, line_no: int, block_no: int = 0) -> list:
    words, cur = [], []
    for g in glyphs:
        if g.char.isspace():
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(g)
    if cur:
        words.append(cur)
    out = []
    for ws in words:
        xs0, ys0 = min(g.bbox[0] for g in ws), min(g.bbox[1] for g in ws)
        xs1, ys1 = max(g.bbox[2] for g in ws), max(g.bbox[3] for g in ws)
        out.append(Word("".join(g.char for g in ws), (xs0, ys0, xs1, ys1), ws, line_no, block_no))
    return out


def _join_hyphens(words: list) -> list:
    """`decompo-` at a line end + `sition` on the next line -> one word `decomposition` (hyphen kept out)."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is not None and w.text.endswith("-") and len(w.text) > 2 and w.text[-2].isalpha() \
                and nxt.line == w.line + 1 and nxt.block == w.block and nxt.text[:1].islower():
            out.append(Word(w.text[:-1] + nxt.text, (min(w.bbox[0], nxt.bbox[0]), w.bbox[1], max(w.bbox[2], nxt.bbox[2]),
                                                    nxt.bbox[3]), w.glyphs[:-1] + nxt.glyphs, w.line, w.block))
            i += 2
            continue
        out.append(w)
        i += 1
    return out


def _classify_rules(rules: list, glyphs: list) -> None:
    for r in rules:
        x0, y0, x1, y1 = r.bbox
        above = below = False
        for g in glyphs:
            if g.char.isspace() or g.bbox[2] <= x0 or g.bbox[0] >= x1:
                continue
            reach, cy = g.size * 1.2, (g.bbox[1] + g.bbox[3]) / 2          # by glyph centre: line boxes overlap rules
            above = above or y0 - reach <= cy <= y0
            below = below or y1 <= cy <= y1 + reach
        radical = any(g.bbox[2] <= x0 + 1.0 and x0 - g.size * 1.5 <= g.bbox[2] and g.bbox[3] >= y0 - 1.0
                      and g.bbox[1] <= y1 + g.size
                      and (g.char == "\u221a" or (g.cls == "bigop" and 0x70 <= ord(g.char[:1] or " ") <= 0x76))
                      for g in glyphs)
        r.kind = "radical" if radical else "fraction" if above and below else "overline" if below \
            else "underline" if above else "rule"


def _page_glyphs(page) -> list:
    """Per line, the glyphs of a pypdfium2 page: [[Glyph, ...], ...] in reading order, y down, spaces kept."""
    from kb_distillery.storage.pdf import page_lines
    out = []
    for line in page_lines(page):
        gl = []
        for ch in line:
            c = clean(ch.ch)
            if c:
                gl.append(Glyph(c, ch.font, ch.size, ch.box, font_class(ch.font)))
        if gl:
            out.append(gl)
    return out


def _paragraph_breaks(lines: list) -> list:
    """Block number of each line: a new block when the gap to the previous line is more than 0.6 of its type size."""
    blocks, block, prev = [], 0, None
    for gl in lines:
        box = [g for g in gl if not g.char.isspace()] or gl
        top, bottom = min(g.bbox[1] for g in box), max(g.bbox[3] for g in box)
        size = max(g.size for g in box)
        if prev is not None and top - prev[1] > 0.6 * prev[2]:
            block += 1
        blocks.append(block)
        prev = (top, bottom, size)
    return blocks


def _half_stroke(obj) -> float:
    """Half the stroke width of a stroked path object, 0 for a path that is only filled."""
    import ctypes

    import pypdfium2.raw as raw
    fill, stroke = ctypes.c_int(), ctypes.c_int()
    raw.FPDFPath_GetDrawMode(obj.raw, ctypes.byref(fill), ctypes.byref(stroke))
    if not stroke.value:
        return 0.0
    width = ctypes.c_float()
    raw.FPDFPageObj_GetStrokeWidth(obj.raw, ctypes.byref(width))
    return width.value / 2


def read_page(page, number: int | None = None) -> PageLayer:
    """Layer of one pypdfium2 page: glyphs, words, thin horizontal rules (path objects) and image boxes."""
    import pypdfium2.raw as raw
    layer = PageLayer(number or 1, page.get_width(), page.get_height())
    height = layer.height
    lines = _page_glyphs(page)
    for line_no, (gl, block_no) in enumerate(zip(lines, _paragraph_breaks(lines))):
        layer.glyphs.extend(g for g in gl if not g.char.isspace())
        layer.words.extend(_words_of_line(gl, line_no, block_no))
    layer.words = _join_hyphens(layer.words)
    paths = []
    for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_PATH, raw.FPDF_PAGEOBJ_IMAGE]):
        x0, bottom, x1, top = obj.get_bounds()
        if obj.type == raw.FPDF_PAGEOBJ_IMAGE:
            layer.figures.append((x0, height - top, x1, height - bottom))
            continue
        half = _half_stroke(obj)             # PDFium's bounds include the stroke; a rule is the path itself
        x0, x1, top, bottom = (x0 + half, x1 - half, top - half, bottom + half) if x1 - x0 > 2 * half \
            else (x0 + half, x0 + half, top - half, bottom + half)
        paths.append((x0, height - max(top, bottom), x1, height - min(top, bottom)))
    for x0, y0, x1, y1 in paths:
        if y1 - y0 <= 1.6 and x1 - x0 >= 2.0:
            layer.rules.append(Rule((x0, y0, x1, y1)))
    _classify_rules(layer.rules, layer.glyphs)
    layer.vrules = [b for b in paths if b[2] - b[0] <= 1.6 and b[3] - b[1] >= 8.0]
    return layer


def iter_pdf(path_or_bytes, pages=None):
    """Layers of a PDF (a path or the bytes) one page at a time, the 1-based `pages` or all of them."""
    from kb_distillery.storage.pdf import LOCK, PdfDoc
    doc = PdfDoc(path_or_bytes)
    try:
        want = set(pages) if pages else None
        for i in range(doc.page_count):
            if want is None or i + 1 in want:
                with LOCK:
                    page = doc.page(i)
                    try:
                        lay = read_page(page, i + 1)
                    finally:
                        page.close()
                yield lay
    finally:
        doc.close()


def read_pdf(path_or_bytes, pages=None) -> list:
    """Layers of a PDF (a path or the bytes), all pages or the 1-based `pages`."""
    return list(iter_pdf(path_or_bytes, pages))

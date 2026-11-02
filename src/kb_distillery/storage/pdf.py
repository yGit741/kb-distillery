"""Reading PDFs: page text, page count, outline, title, one page as a PNG. The one place the PDF library is imported.

The library is pypdfium2 (BSD / Apache, the PDFium engine). It replaced PyMuPDF, which is AGPL. PDFium is not thread
safe, and the server renders thumbnails from a thread pool, so every call into it runs under `LOCK`.

`page_text` keeps the shape the pipeline always saw: lines joined by "\\n", a page ending in "\\n" when it has text.
Everything that reads a PDF imports this module lazily, so a missing library means "no PDF support" in one place.
"""
from __future__ import annotations

import ctypes
import io
import threading
from typing import NamedTuple

LOCK = threading.RLock()
GAP_EM = 2.0          # a gap wider than this many em on one line starts a new line (table cells sit this far apart)
MISSING_MSG = "pypdfium2 not installed — run: pixi install"


def available() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


class Char(NamedTuple):
    ch: str            # one character ("" for a generated line break is never returned)
    box: tuple         # x0, y0, x1, y1 in points, y down (the font's full line height, not the ink)
    size: float
    font: str


def page_lines(page) -> list:
    """The characters of a pypdfium2 page grouped into lines: [[Char, ...], ...], caller holds `LOCK`.

    PDFium starts a new line whenever the baseline moves, so a subscript, a superscript or a raised accent becomes a line
    of its own. A break is dropped when the next character sits inside the vertical extent of the line before it: that is
    one line of text with a script on it, which is how the rest of the pipeline (and the page itself) reads it.
    A hyphen at the end of a line, which PDFium reports as a marker with no text, is given back as "-" plus the break."""
    import pypdfium2.raw as raw
    height = page.get_height()
    tp = page.get_textpage()
    try:
        handle, n = tp.raw, tp.count_chars()
        name_buf = ctypes.create_string_buffer(256)
        flags = ctypes.c_int()
        lines, cur, i, pending_break = [], [], 0, False
        top = bottom = last_x0 = last_x1 = size_max = 0.0
        while i < n:
            u = raw.FPDFText_GetUnicode(handle, i)
            hyphen = bool(raw.FPDFText_IsHyphen(handle, i))
            if u in (10, 13) and not hyphen:
                pending_break = bool(cur)
                i += 1
                continue
            step = 1
            if hyphen:
                ch = "-"
            elif 0xD800 <= u < 0xDC00 and i + 1 < n:            # high surrogate: join with the low half
                ch = chr(0x10000 + ((u - 0xD800) << 10) + (raw.FPDFText_GetUnicode(handle, i + 1) - 0xDC00))
                step = 2
            else:
                ch = chr(u) if u else ""
            if ch == "" or (ord(ch[0]) < 32 and ch not in "\t") or ch in "\ufffe\uffff":
                i += step                                       # a control code or no unicode: nothing to read
                continue
            left, bot, right, tp_ = tp.get_charbox(i, loose=True)
            box = (left, height - tp_, right, height - bot)
            if cur and not pending_break and not ch.isspace() and box[0] - last_x1 > GAP_EM * size_max:
                while cur and cur[-1].ch.isspace():
                    cur.pop()
                lines.append(cur)                               # a wide gap on one baseline: a table cell, a new run
                cur = []
            if pending_break and cur:
                mid = (box[1] + box[3]) / 2
                if not (top <= mid <= bottom and box[0] >= last_x0 - 0.6 * size_max):
                    lines.append(cur)
                    cur = []
            pending_break = False
            size = float(raw.FPDFText_GetFontSize(handle, i))
            nlen = raw.FPDFText_GetFontInfo(handle, i, name_buf, len(name_buf), ctypes.byref(flags))
            font = name_buf.raw[:max(0, nlen - 1)].decode("utf-8", "replace") if nlen > 0 else ""
            if not cur:
                top, bottom, size_max = box[1], box[3], size
            elif not ch.isspace():
                top, bottom, size_max = min(top, box[1]), max(bottom, box[3]), max(size_max, size)
            last_x0 = box[0]
            if not ch.isspace():
                last_x1 = box[2]
            cur.append(Char(ch, box, size, font))
            if hyphen:
                lines.append(cur)
                cur = []
            i += step
        if cur:
            lines.append(cur)
        return lines
    finally:
        tp.close()


class PdfDoc:
    """An open PDF: a path, or the bytes of one. Pages are 0-based here (the TOC and `layer` use 1-based numbers)."""

    def __init__(self, source):
        import pypdfium2 as pdfium
        with LOCK:
            self._doc = pdfium.PdfDocument(bytes(source) if isinstance(source, (bytes, bytearray)) else str(source))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        with LOCK:
            if self._doc is not None:
                self._doc.close()
                self._doc = None

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def page(self, i: int):
        """The raw pypdfium2 page (caller holds `LOCK` while using it)."""
        return self._doc[i]

    def page_size(self, i: int) -> tuple:
        with LOCK:
            return self._doc[i].get_size()

    def page_text(self, i: int) -> str:
        """Text of page `i`: one line per "\\n", ending in "\\n" when the page has any text."""
        with LOCK:
            page = self._doc[i]
            try:
                text = "".join("".join(c.ch for c in line) + "\n" for line in page_lines(page))
            finally:
                page.close()
        return text

    def toc(self) -> list:
        """The outline as (level, title, page) with levels and pages 1-based; an entry with no page gets page 0."""
        out = []
        with LOCK:
            for item in self._doc.get_toc():
                dest = item.get_dest()
                idx = dest.get_index() if dest is not None else None
                out.append((item.level + 1, item.get_title() or "", (idx + 1) if idx is not None else 0))
        return out

    @property
    def title(self) -> str:
        with LOCK:
            return (self._doc.get_metadata_dict() or {}).get("Title") or ""

    def render(self, i: int, width: int):
        """Page `i` rendered `width` px wide as an RGB PIL image."""
        with LOCK:
            page = self._doc[i]
            try:
                image = page.render(scale=width / max(page.get_width(), 1)).to_pil()
            finally:
                page.close()
        return image.convert("RGB")

    def render_png(self, i: int, width: int) -> bytes:
        """Page `i` rendered `width` px wide as PNG bytes."""
        buf = io.BytesIO()
        self.render(i, width).save(buf, "PNG")
        return buf.getvalue()

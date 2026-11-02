"""Build small PDFs for tests (reportlab, BSD). Coordinates are in points from the top-left corner, text is placed on its
baseline, as a page layout is usually described; the bytes are deterministic (no dates, no random /ID).

    doc = pdfkit.Doc()
    doc.new_page().insert_text((72, 72), "hello", fontsize=10)
    doc.set_toc([[1, "Chapter 1", 1]])
    doc.save(path)           # or doc.tobytes()
"""
from __future__ import annotations

import io

from reportlab import rl_config
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

rl_config.invariant = 1                 # no creation date, a fixed /ID: the same input gives the same bytes

A4 = (595.0, 842.0)
FONTS = {"helv": "Helvetica", "heit": "Helvetica-Oblique", "hebo": "Helvetica-Bold"}


def font_name(name):
    return FONTS.get(name, name)


def text_length(text, fontname="helv", fontsize=11):
    return stringWidth(text, font_name(fontname), fontsize)


class Page:
    def __init__(self, size=A4):
        self.width, self.height = size
        self._ops = []

    def insert_text(self, point, text, fontsize=11, fontname="helv"):
        """`text` starts on the baseline at `point`; a newline starts the next line 1.2 em below."""
        self._ops.append(("text", point, text, fontsize, font_name(fontname)))

    def insert_rotated_text(self, point, text, fontsize=11, fontname="helv"):
        """`text` running upwards (rotated 90 degrees) from `point`, like the arXiv stamp in the left margin."""
        self._ops.append(("rtext", point, text, fontsize, font_name(fontname)))

    def insert_textbox(self, rect, text, fontsize=11, fontname="helv"):
        """`text` wrapped to the width of `rect` (x0, y0, x1, y1), top line at its top edge; a blank line stays blank."""
        x0, y0, x1, _ = rect
        font, y = font_name(fontname), y0 + fontsize
        for para in text.split("\n"):
            for line in simpleSplit(para, font, fontsize, x1 - x0) or [""]:
                self._ops.append(("text", (x0, y), line, fontsize, font))
                y += fontsize * 1.2

    def draw_line(self, p1, p2, width=1.0):
        self._ops.append(("line", p1, p2, width))

    def insert_image(self, rect, color=(200, 60, 60)):
        """A solid-colour raster image filling `rect`."""
        self._ops.append(("image", rect, color))

    def _render(self, c):
        from reportlab.lib.utils import ImageReader
        h = self.height
        for op in self._ops:
            if op[0] == "text":
                _, (x, y), text, size, font = op
                for k, line in enumerate(text.split("\n")):
                    c.setFont(font, size)
                    c.drawString(x, h - y - k * size * 1.2, line)
            elif op[0] == "rtext":
                _, (x, y), text, size, font = op
                c.saveState()
                c.translate(x, h - y)
                c.rotate(90)
                c.setFont(font, size)
                c.drawString(0, 0, text)
                c.restoreState()
            elif op[0] == "line":
                _, (x0, y0), (x1, y1), width = op
                c.setLineWidth(width)
                c.line(x0, h - y0, x1, h - y1)
            else:
                from PIL import Image
                _, (x0, y0, x1, y1), color = op
                buf = io.BytesIO()
                Image.new("RGB", (40, 27), tuple(color)).save(buf, "PNG")
                buf.seek(0)
                c.drawImage(ImageReader(buf), x0, h - y1, width=x1 - x0, height=y1 - y0)


class Doc:
    def __init__(self):
        self.pages: list[Page] = []
        self.toc: list = []
        self.title = ""

    def new_page(self, size=A4) -> Page:
        self.pages.append(Page(size))
        return self.pages[-1]

    def set_toc(self, toc):
        """[[level, title, page], ...] with 1-based levels and pages."""
        self.toc = toc

    def set_metadata(self, meta):
        """Only `title` is kept: the producer and dates would make the bytes differ between runs."""
        self.title = (meta or {}).get("title", "")

    def close(self):
        pass

    def tobytes(self) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
        if self.title:
            c.setTitle(self.title)
        for n, page in enumerate(self.pages, 1):
            c.setPageSize((page.width, page.height))
            page._render(c)
            for k, (level, title, at) in enumerate(self.toc):
                if at == n:
                    key = f"toc{k}"
                    c.bookmarkPage(key)
                    c.addOutlineEntry(title, key, level=level - 1, closed=False)
            c.showPage()
        c.save()
        return buf.getvalue()

    def save(self, path, **_ignored):
        with open(path, "wb") as f:
            f.write(self.tobytes())

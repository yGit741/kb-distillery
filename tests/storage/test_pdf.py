"""storage.pdf (pypdfium2): the text, outline, title and page image the pipeline reads from a PDF."""
import threading

from kb_distillery.storage.pdf import PdfDoc
from tests import pdfkit


def make(build):
    doc = pdfkit.Doc()
    build(doc)
    return PdfDoc(doc.tobytes())


def test_page_text_is_one_line_per_newline_and_ends_with_one():
    def build(doc):
        doc.new_page().insert_text((72, 100), "first line\nsecond line", fontsize=10)
        doc.new_page()
    d = make(build)
    assert d.page_count == 2 and d.page_text(0) == "first line\nsecond line\n" and d.page_text(1) == ""


def test_hyphen_at_a_line_end_is_kept():
    def build(doc):
        pg = doc.new_page()
        pg.insert_text((72, 100), "the strict non-", fontsize=10)
        pg.insert_text((72, 114), "saturation region", fontsize=10)
    assert make(build).page_text(0) == "the strict non-\nsaturation region\n"


def test_a_script_stays_on_its_line_and_a_wide_gap_starts_a_new_one():
    def build(doc):
        pg = doc.new_page()
        pg.insert_text((72, 100), "z = x", fontsize=10)
        pg.insert_text((100, 102.5), "i", fontsize=7, fontname="heit")       # a subscript
        pg.insert_text((72, 130), "size", fontsize=10)
        pg.insert_text((200, 130), "score", fontsize=10)                      # the next table cell
    assert make(build).page_text(0) == "z = xi\nsize\nscore\n"


def test_outline_levels_pages_and_title():
    def build(doc):
        doc.new_page(); doc.new_page()
        doc.set_toc([[1, "Chapter 1", 1], [2, "Section", 2], [1, "Chapter 2", 2]])
        doc.set_metadata({"title": "  A   Title "})
    d = make(build)
    assert d.toc() == [(1, "Chapter 1", 1), (2, "Section", 2), (1, "Chapter 2", 2)] and d.title.strip() == "A   Title"


def test_render_png_width_and_thread_safety():
    d = make(lambda doc: doc.new_page().insert_text((72, 100), "hi"))
    out, errs = [], []

    def work():
        try:
            out.append(d.render_png(0, 300))
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(out) == 6 and all(b[:8] == b"\x89PNG\r\n\x1a\n" for b in out)

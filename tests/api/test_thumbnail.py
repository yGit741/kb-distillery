"""thumbnail_png renders the first page of a real PDF (the corpus router's tests mock it)."""
import pytest

from kb_distillery.api.assets import thumbnail_png


def test_pdf_thumbnail(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "2000-x.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(str(path))
    assert thumbnail_png(str(path)).startswith(b"\x89PNG")

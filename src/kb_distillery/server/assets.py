"""Server assets the typed routers share: the height reporter injected into chat visualizations and PDF thumbnails."""
import os

THUMB_WIDTH = 360
VIZ_REPORTER = (b"<script>(function(){var p=function(){parent.postMessage({vizHeight:"
                b"document.documentElement.scrollHeight},'*');};new ResizeObserver(p)"
                b".observe(document.documentElement);addEventListener('load',p);p();})()</script>")
_thumbs = {}          # (path, mtime, width) -> PNG bytes; a re-annotated PDF gets a new mtime


def thumbnail_png(full, width=THUMB_WIDTH):
    """First page of a PDF rendered `width` px wide (200-1400), or None if it can't be rendered."""
    width = max(200, min(1400, int(width)))
    key = (full, os.path.getmtime(full), width)
    if key not in _thumbs:
        try:
            import fitz  # pymupdf
            doc = fitz.open(full)
            page = doc[0]
            zoom = width / max(page.rect.width, 1)
            _thumbs[key] = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
            doc.close()
        except Exception:
            _thumbs[key] = None
    return _thumbs[key]

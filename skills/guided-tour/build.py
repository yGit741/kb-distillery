"""Inline the tour engine into a mockup page so it publishes as one self-contained file.

    python skills/guided-tour/build.py <mockup.html> -o <out.html>

The mockup marks where the engine goes with `<!-- tour.js -->`.
"""
import argparse
from pathlib import Path

HERE = Path(__file__).parent
MARKER = "<!-- tour.js -->"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mockup")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    page = Path(a.mockup).read_text()
    if MARKER not in page:
        raise SystemExit(f"mockup has no {MARKER} marker")
    engine = (HERE / "assets" / "tour.js").read_text()
    Path(a.out).write_text(page.replace(MARKER, f"<script>{engine}</script>"))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

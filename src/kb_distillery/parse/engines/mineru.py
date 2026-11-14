"""MinerU 4.1.3, run locally as a subprocess: `mineru-kit parse <pdf> -o <dir> --tier advanced -f middle_json`.

MinerU lives in a plain venv outside the repo (`$KB_MINERU_HOME`, default ~/.cache/kb-distillery/mineru, venv under
`venv/`, a private HOME under `home/` so models, caches and its config never land in the real home). It is a local
model, not a `kb_distillery.llm` call: nothing is sent anywhere and nothing is billed. Telemetry is switched off
in the environment of every run (`MINERU_TELEMETRY_DISABLED=1`), and `--remote` is never passed.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess

from . import EngineError

DEFAULT_HOME = "~/.cache/kb-distillery/mineru"
TIER = "advanced"
TIMEOUT = 6 * 3600


def home_dir() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("KB_MINERU_HOME", DEFAULT_HOME)))


def kit_path() -> str:
    return os.path.join(home_dir(), "venv", "bin", "mineru-kit")


def environment(base: dict | None = None) -> dict:
    """The child's environment: a private HOME / HF_HOME, telemetry off. Nothing else is inherited but PATH."""
    h = os.path.join(home_dir(), "home")
    src = os.environ if base is None else base
    env = {"PATH": src.get("PATH", "/usr/bin:/bin"), "HOME": h, "HF_HOME": h, "MINERU_TELEMETRY_DISABLED": "1",
           "LANG": src.get("LANG", "en_US.UTF-8")}
    for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
        if k in src:
            env[k] = src[k]
    return env


def page_arg(pages: list) -> str:
    """[3,4,5,9] -> '3-5,9' (1-based, as mineru-kit's --pages)."""
    pages, parts, i = sorted(set(pages)), [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(str(pages[i]) if i == j else "%d-%d" % (pages[i], pages[j]))
        i = j + 1
    return ",".join(parts)


def command(pdf: str, out: str, pages: list) -> list:
    """Never `--remote` / `--remote-url` / `--api-key`: the model runs on this machine."""
    return [kit_path(), "parse", pdf, "-o", out, "--tier", TIER, "-f", "middle_json", "--disable-image-analysis",
            "-p", page_arg(pages)]


class MinerU:
    name = "mineru"

    def parse(self, pdf: str, pages: list, workdir: str) -> dict:
        if not os.path.exists(kit_path()):
            raise EngineError("mineru-kit not found at %s (set KB_MINERU_HOME; see parse/engines/mineru.py)" % kit_path())
        os.makedirs(os.path.join(home_dir(), "home"), exist_ok=True)
        r = subprocess.run(command(pdf, workdir, pages), env=environment(), capture_output=True, text=True,
                           timeout=TIMEOUT, cwd=workdir)
        if r.returncode != 0:
            raise EngineError("mineru-kit exited %d: %s" % (r.returncode, (r.stderr or r.stdout)[-1500:]))
        files = sorted(glob.glob(os.path.join(workdir, "**", "*.json"), recursive=True))
        if not files:
            raise EngineError("mineru-kit wrote no JSON under %s: %s" % (workdir, (r.stderr or r.stdout)[-800:]))
        out: dict = {}
        for f in files:
            doc = json.load(open(f, encoding="utf-8"))
            if not isinstance(doc, dict):
                continue
            for pg in doc.get("pages", []):
                out[int(pg["page_idx"]) + 1] = pg          # page_idx stays the PDF's own 0-based index for a subset
        stray = sorted(set(out) - set(pages))
        if stray:
            raise EngineError("mineru-kit returned pages %s that were not asked for (%s)" % (stray, page_arg(pages)))
        return out

    def markdown(self, record: dict) -> str:
        return to_markdown(record)

    def figures(self, record: dict, width: float, height: float) -> list:
        return figure_boxes(record, width, height)

    def boxes(self, record: dict) -> list:
        return chunk_boxes(record)

    def body(self, record: dict) -> tuple:
        return body(record)


SKIP: set = set()          # running heads and page numbers are kept: dropping them would only make the verifier miss them


def _no_dollar(latex: str) -> str:
    """MinerU sometimes leaves a stray `$` inside an equation's own text (`$--- e.g. $x$ —$`); one more would end the
    math early and turn the rest into prose, so none is kept."""
    return latex.replace("$", "").strip()


_CELL = re.compile(r"(<t[dh][^>]*>)(.*?)(</t[dh]>)", re.S)


def _table(html: str) -> str:
    """Cells of an HTML table that hold raw LaTeX (`\\mathcal{F}_1`, `a_{ij}`) get `$...$` so they read as math."""
    def cell(m):
        body = m.group(2).strip()
        if "$" not in body and re.search(r"\\[A-Za-z]+|[_^]\{", body):
            body = "$%s$" % body
        return m.group(1) + body + m.group(3)
    return _CELL.sub(cell, html)


def _spans(content) -> str:
    """Inline spans (text and equation_inline) joined as Markdown; a plain string passes through."""
    if isinstance(content, str):
        return content
    out = []
    for sp in content or []:
        if not isinstance(sp, dict):
            continue
        t, c = sp.get("type"), sp.get("content", "")
        if t == "equation_inline":
            out.append("$%s$" % _no_dollar(c))
        elif isinstance(c, list):
            out.append(_spans(c))
        else:
            out.append(c)
    return "".join(out)


FURNITURE = {"page_number", "header", "footer"}        # running heads and page numbers: not part of the text


def _block(b: dict, box=None, skip=frozenset()) -> list:
    """(Markdown chunk, box) pairs of one block (a chunk is a paragraph, a display equation, a table...). The box is the
    block's own `bbox` (fractions of the page: x0, y0, x1, y1), else the enclosing block's."""
    t, c = b.get("type"), b.get("content")
    box = tuple(b["bbox"]) if b.get("bbox") and len(b["bbox"]) == 4 else box
    if t in SKIP or t in skip:
        return []
    if t == "equation":
        return [("$$\n%s\n$$" % _no_dollar(c if isinstance(c, str) else _spans(c)), box)]
    if t == "paragraph_title" or t == "title":
        return [("%s %s" % ("#" * max(1, min(6, int(b.get("level", 1)) + 1)), _spans(c).strip()), box)]
    if t in ("image", "table", "list", "code", "algorithm") and isinstance(c, list) and c and "type" in c[0] \
            and c[0]["type"] not in ("text", "equation_inline"):
        return [x for sub in c for x in _block(sub, box, skip)]
    if t == "list" and isinstance(c, list):
        return [x for sub in c for x in _block(sub, box, skip)]
    if t == "image_body":
        return [("![](image)", box)]
    if t == "table_body":
        return [(_table(c if isinstance(c, str) else _spans(c)), box)]
    txt = _spans(c).strip()
    return [(txt, box)] if txt else []


def chunks(record: dict, skip=frozenset()) -> list:
    """[(Markdown chunk, box or None)] of one middle-JSON page, in MinerU's reading order, without block types in `skip`."""
    return [x for b in record.get("blocks", []) for x in _block(b, None, skip)]


def body(record: dict) -> tuple:
    """(Markdown, [(start, end, box)]) of the page without its running head, footer and page number."""
    out, parts, pos = [], [], 0
    for md, box in chunks(record, FURNITURE):
        out.append((pos, pos + len(md), box))
        parts.append(md)
        pos += len(md) + 2
    return "\n\n".join(parts) + "\n", out


def to_markdown(record: dict) -> str:
    """Markdown of one middle-JSON page, in MinerU's reading order. Image bodies stay a placeholder (the figure's pixels
    are not text); the engine is run with --disable-image-analysis so nothing is read out of a plot."""
    return "\n\n".join(md for md, _ in chunks(record)) + "\n"


def chunk_boxes(record: dict) -> list:
    """[(start, end, box)] over the characters of `to_markdown(record)`: which block each stretch came from."""
    out, pos = [], 0
    for md, box in chunks(record):
        out.append((pos, pos + len(md), box))
        pos += len(md) + 2
    return out


def figure_boxes(record: dict, width: float, height: float) -> list:
    """Image regions MinerU found, in PDF points: text the PDF draws inside one (axis ticks, legends of a vector plot)
    belongs to the figure, not to the page's prose, so the verifier leaves it out."""
    out = []

    def walk(b):
        if b.get("type") == "image_body" and b.get("bbox"):
            x0, y0, x1, y1 = b["bbox"]
            out.append((x0 * width, y0 * height, x1 * width, y1 * height))
        if isinstance(b.get("content"), list):
            for x in b["content"]:
                if isinstance(x, dict):
                    walk(x)
    for b in record.get("blocks", []):
        walk(b)
    return out

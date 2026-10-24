"""Extract PDF text for agent; validate claims.json."""
import json
import os
import re
import sys

from kb.core.schema import PARSED_FILENAME

from .paths import session_dir, load_session, person_from_raw
from .schemas import validate_claims


def _sidecar_path(raw_path):
    """A parsed.md next to raw_path (file sibling) or inside it (directory)."""
    if os.path.isdir(raw_path):
        candidate = os.path.join(raw_path, PARSED_FILENAME)
    else:
        candidate = os.path.join(os.path.dirname(raw_path), PARSED_FILENAME)
    return candidate if os.path.isfile(candidate) else None


TEXT_EXTS = {".md", ".txt", ".html", ".htm"}
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
_TAGS = re.compile(r"<[^>]+>")


def text_clip(raw_path):
    """A web clip or other text file is its own text: frontmatter dropped, HTML tags stripped."""
    with open(raw_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    if raw_path.lower().endswith((".html", ".htm")):
        text = _TAGS.sub(" ", text)
    return _FRONTMATTER.sub("", text, count=1).strip() + "\n"


def extract_text(raw_path, max_pages=25, pages=None):
    """Text of a PDF. `pages` is a 1-based inclusive (start, end) range; without it,
    read the first `max_pages` pages — fine for a paper, useless for a book."""
    sidecar = _sidecar_path(raw_path)
    if sidecar:
        with open(sidecar, encoding="utf-8") as f:
            return f.read()
    if os.path.splitext(raw_path)[1].lower() in TEXT_EXTS:
        return text_clip(raw_path)

    try:
        import fitz  # pymupdf
    except ImportError:
        print("pymupdf not installed — run: pixi install", file=sys.stderr)
        return None

    doc = fitz.open(raw_path)
    parts = []
    if pages:
        start = max(1, min(pages[0], doc.page_count))
        end = max(start, min(pages[1], doc.page_count))
        parts.append(f"[pages {start}-{end} of {doc.page_count}]\n")
        for i in range(start - 1, end):
            parts.append(doc.load_page(i).get_text())
    else:
        for i, page in enumerate(doc):
            if i >= max_pages:
                parts.append(f"\n[... truncated after {max_pages} pages ...]\n")
                break
            parts.append(page.get_text())
    doc.close()
    return "\n".join(parts)


def run_extract(sha):
    session = load_session(sha)
    raw_rel = session["raw"]
    from kb.paths import vault_root
    root = vault_root()
    raw_path = os.path.join(root, raw_rel)

    scope = session.get("scope") or {}
    pages = tuple(scope["pages"]) if scope.get("pages") else None
    text = extract_text(raw_path, pages=pages)
    sdir = session_dir(sha)
    text_path = os.path.join(sdir, "extracted.text")
    if text:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        scope_note = f" · scope: {scope.get('label')}" if scope.get("label") else ""
        print(f"wrote {text_path} ({len(text)} chars){scope_note}")
    else:
        print("no text extracted — agent must read PDF directly")

    claims_path = os.path.join(sdir, "claims.json")
    if os.path.isfile(claims_path):
        with open(claims_path, encoding="utf-8") as f:
            claims = json.load(f)
        validate_claims(claims)
        print(f"claims.json valid ({claims.get('title', '?')})")
    else:
        template = {
            "raw": raw_rel,
            "title": "",
            "problem": "",
            "method": "",
            "results": [],
            "equations": [{"latex": "", "variables": {}, "label": ""}],
            "concepts": [],
            "open_questions": [],
            "citekey": "",
            "url": "",
            "year": int(os.path.basename(raw_rel)[:4]) if os.path.basename(raw_rel)[:4].isdigit() else None,
            "authors": [],
        }
        if scope.get("label"):
            template["section"] = scope["label"]
            template["section_pages"] = scope.get("pages")
        person = person_from_raw(raw_rel)
        if person:
            template["person"] = person
        with open(claims_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
            f.write("\n")
        print(f"claims template at {claims_path} — fill via agent, then re-run extract to validate")

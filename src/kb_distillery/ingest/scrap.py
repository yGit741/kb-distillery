"""Download URLs or copy files to raw/inbox/. Zero LLM."""
import hashlib
import os
import re
import shutil
import sys
import urllib.request
from urllib.parse import urlparse

from .paths import ROOT
from . import resolve as resolve_mod
from kb_distillery.config import net

INBOX = os.path.join(ROOT, "raw", "inbox")


def _ensure_inbox():
    os.makedirs(INBOX, exist_ok=True)


def _sanitize_name(name):
    name = re.sub(r"[^\w.\-]+", "-", name).strip("-").lower()
    return name or "download"


def web_clip_name(url, max_len=120):
    """Inbox name for a scrapped HTML page: kebab of host (no www) + path, so two pages never share
    a name. `page.html` only when both host and path are empty."""
    from urllib.parse import unquote
    p = urlparse(url)
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = re.sub(r"\.(html?|php|aspx?)$", "", unquote(p.path or ""), flags=re.I)
    stem = re.sub(r"[^a-z0-9]+", "-", f"{host} {path}".lower()).strip("-")[:max_len].rstrip("-")
    return f"{stem}.html" if stem else "page.html"


PDF_MAGIC = b"%PDF-"


def arxiv_filename(aid):
    """Reversible inbox name for an arXiv id. New-style keeps the historic arxiv-2105-10386.pdf;
    old-style maps only the slash, so math.PR/0503503 and hep-th/9901001 stay distinguishable.
    catalog._arxiv_id_from_scrape is the inverse."""
    return f"arxiv-{aid.replace('/', '_')}.pdf" if "/" in aid else f"arxiv-{aid.replace('.', '-')}.pdf"


def _fetch(url):
    """(bytes, Content-Type) of a URL, nothing written."""
    req = urllib.request.Request(url, headers={"User-Agent": "thesis-wiki-ingest/1.0"})
    with net.urlopen(req, timeout=60) as resp:
        data = resp.read()
        ctype = ""
        try:
            ctype = resp.headers.get("Content-Type", "") or ""
        except AttributeError:
            pass
    return data, ctype


def is_pdf(data, content_type=""):
    """A PDF by its bytes (`%PDF-`) or its Content-Type, never by the URL's suffix."""
    return bytes(data[:1024]).lstrip().startswith(PDF_MAGIC) or "application/pdf" in (content_type or "").lower()


def _download(url, dest):
    data, _ctype = _fetch(url)
    with open(dest, "wb") as f:
        f.write(data)
    return data


def record_source(inbox_name, data, url):
    """Remember where a non-arXiv download came from (meta/.catalog/sources.jsonl, keyed by inbox
    filename + sha1) so catalog can write the stub's `url:`. raw/ stays free of agent files."""
    import json
    d = os.path.join(ROOT, "meta", ".catalog")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "sources.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"file": inbox_name, "sha1": hashlib.sha1(data).hexdigest(), "url": url}) + "\n")


def source_url(inbox_path):
    """The recorded source URL for an inbox file (matched on name and content sha1), or ''."""
    import json
    try:
        with open(inbox_path, "rb") as f:
            sha = hashlib.sha1(f.read()).hexdigest()
        with open(os.path.join(ROOT, "meta", ".catalog", "sources.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return ""
    name = os.path.basename(inbox_path)
    for r in reversed(rows):
        if r.get("file") == name and r.get("sha1") == sha:
            return r.get("url", "")
    return ""


def _check_pre_resolve(source, force):
    if force:
        print("scrap: --force, skipping pre-resolve check", file=sys.stderr)
        return
    result = resolve_mod.resolve(source)
    if result.status == "found":
        print(resolve_mod.format_human(result))
        print("scrap blocked — use existing entry or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked(result.matches)
    if result.status == "ambiguous":
        print(resolve_mod.format_human(result))
        print("scrap blocked — refine query with resolve, or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked(result.matches)


def _check_post_bytes(data, inbox_rel, force):
    if force:
        return
    h = resolve_mod.sha1_bytes(data)
    dupes = resolve_mod.find_by_sha1(h, exclude_path=inbox_rel)
    if dupes:
        full = os.path.join(ROOT, inbox_rel)
        if os.path.isfile(full):
            os.remove(full)
        print(f"DUPLICATE bytes (sha1 {h}) — already at {dupes[0]}")
        if len(dupes) > 1:
            print(f"  also: {', '.join(dupes[1:])}")
        print("scrap blocked — use existing file or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked([{"raw": dupes[0], "sha1": h, "reason": "byte-identity"}])


def scrap(source, kind=None, force=False):
    """Save source to raw/inbox/. Returns inbox-relative path."""
    _ensure_inbox()
    source = source.strip()
    _check_pre_resolve(source, force)

    if os.path.isfile(source):
        ext = os.path.splitext(source)[1].lower()
        with open(source, "rb") as f:
            data = f.read()
        if kind is None:
            kind = "articles" if ext == ".pdf" or is_pdf(data) else "notes"
        name = _sanitize_name(os.path.basename(source))
        if kind == "articles" and not name.endswith(".pdf") and data.startswith(PDF_MAGIC):
            name += ".pdf"
        dest = os.path.join(INBOX, name)
        rel = f"raw/inbox/{name}"
        _check_post_bytes(data, rel, force)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"scrap ({kind}) → {rel}")
        return rel

    if not source.startswith(("http://", "https://")):
        raise ValueError(f"not a file or URL: {source}")

    parsed = urlparse(source)
    aid = resolve_mod.normalize_arxiv_id(source)
    if aid or kind == "articles" or parsed.path.lower().endswith(".pdf"):
        if aid:
            pdf_url = f"https://arxiv.org/pdf/{aid}"
            name = arxiv_filename(aid)
        else:
            pdf_url = source
            name = _sanitize_name(os.path.basename(parsed.path) or "paper.pdf")
            if not name.endswith(".pdf"):
                name += ".pdf"
        dest = os.path.join(INBOX, name)
        data = _download(pdf_url, dest)
        if not data.startswith(PDF_MAGIC):
            os.remove(dest)
            kind_seen = "an HTML page" if data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")) else "not a PDF"
            raise ValueError(
                f"{pdf_url} returned {kind_seen} ({len(data)} bytes), not a PDF — nothing saved. "
                "Publishers often answer scripts with a login or consent page; find a direct PDF link.")
        rel = f"raw/inbox/{name}"
        _check_post_bytes(data, rel, force)
        if not aid:
            record_source(name, data, source)
        print(f"scrap (articles) → {rel}")
        return rel

    data, ctype = _fetch(source)
    if is_pdf(data, ctype) and data.startswith(PDF_MAGIC):      # a PDF served from a suffix-less URL
        name = _sanitize_name(os.path.basename(parsed.path) or "paper.pdf")
        if not name.endswith(".pdf"):
            name += ".pdf"
        rel = f"raw/inbox/{name}"
        _check_post_bytes(data, rel, force)
        with open(os.path.join(INBOX, name), "wb") as f:
            f.write(data)
        record_source(name, data, source)
        print(f"scrap (articles) → {rel}")
        return rel
    name = web_clip_name(source)
    dest = os.path.join(INBOX, name)
    with open(dest, "wb") as f:
        f.write(data)
    rel = f"raw/inbox/{name}"
    _check_post_bytes(data, rel, force)
    print(f"scrap ({kind or 'web'}) → {rel}")
    return rel

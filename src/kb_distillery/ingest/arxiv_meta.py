"""Authoritative paper metadata from the arXiv API (title, year, authors). 0 LLM.

Used by `catalog` to name arXiv scrapes properly (the filename alone gives `2000-untitled.pdf`),
and by `backfill-authors` to repair author lists that were bootstrapped as the researcher alone.
"""
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
BATCH = 50            # ids per request
PAUSE_S = 3.0         # arXiv asks for >=3s between calls — enforced globally by _throttle()
TIMEOUT_S = 30
RETRIES = 3           # on 429 / 5xx: wait (Retry-After or 5s·n) and try again, then give up loudly
RETRY_CODES = {429, 500, 502, 503, 504}
ENTRY_ID = re.compile(r"arxiv\.org/abs/(.+?)(v\d+)?$")
# the margin stamp arXiv prints on page 1: `arXiv:2310.02541v2 [cs.LG] 4 Oct 2023`
STAMP = re.compile(r"arXiv:\s*([a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?\s*\[[\w.\-]+\]\s*\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}")

SLEEP = time.sleep    # patched by tests
_last_call = 0.0


class ArxivUnavailable(RuntimeError):
    """The arXiv API did not answer (rate limit, outage, network). Callers must not guess a
    title or clear a url on this — leave the file where it is and retry later."""


def _throttle():
    global _last_call
    wait = _last_call + PAUSE_S - time.monotonic()
    if wait > 0:
        SLEEP(wait)
    _last_call = time.monotonic()


def _retry_after(err):
    try:
        return float(err.headers.get("Retry-After", "")) if err.headers else None
    except (TypeError, ValueError):
        return None


def _get(url, opener=None):
    """One throttled API call; retries on 429/5xx; raises ArxivUnavailable when it cannot."""
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": "thesis-wiki-ingest/1.0"})
    last = None
    for attempt in range(1, RETRIES + 1):
        _throttle()
        try:
            with opener(req, timeout=TIMEOUT_S) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in RETRY_CODES:
                raise ArxivUnavailable(f"HTTP {e.code}") from e
            delay = _retry_after(e) or 5.0 * attempt
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            delay = 5.0 * attempt
        if attempt < RETRIES:
            print(f"arxiv: {last} — retry {attempt}/{RETRIES - 1} in {delay:.0f}s", file=sys.stderr)
            SLEEP(delay)
    code = getattr(last, "code", None)
    raise ArxivUnavailable(f"HTTP {code}" if code else str(last)) from last


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _parse(xml_bytes):
    out = {}
    root = ET.fromstring(xml_bytes)
    for entry in root.findall("a:entry", ATOM):
        m = ENTRY_ID.search(_clean(entry.findtext("a:id", default="", namespaces=ATOM)))
        if not m:
            continue
        title = _clean(entry.findtext("a:title", default="", namespaces=ATOM))
        if not title or title.lower() == "error":
            continue
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        authors = [_clean(a.findtext("a:name", default="", namespaces=ATOM))
                   for a in entry.findall("a:author", ATOM)]
        out[m.group(1)] = {
            "id": m.group(1),
            "title": title,
            "year": int(published[:4]) if published[:4].isdigit() else None,
            "authors": [a for a in authors if a],
            "url": f"https://arxiv.org/abs/{m.group(1)}",
        }
    return out


def fetch(ids, pause=PAUSE_S, opener=None, strict=False):
    """{arxiv_id: {title, year, authors, url}} for every id arXiv knows. Missing ids are absent.

    A batch the API will not serve (after retries) is reported and skipped — or, with `strict`,
    raises ArxivUnavailable so the caller can refuse instead of filing something `untitled`.
    `pause` is kept for callers; spacing between calls is enforced by _throttle() regardless."""
    ids = [i for i in dict.fromkeys(ids) if i]
    out = {}
    for n in range(0, len(ids), BATCH):
        chunk = ids[n:n + BATCH]
        url = f"{API}?{urllib.parse.urlencode({'id_list': ','.join(chunk), 'max_results': len(chunk)})}"
        try:
            out.update(_parse(_get(url, opener)))
        except ArxivUnavailable as e:
            if strict:
                raise
            print(f"arxiv: batch {n // BATCH + 1} failed: {e}", file=sys.stderr)
        except ET.ParseError as e:
            if strict:
                raise ArxivUnavailable(f"bad XML: {e}") from e
            print(f"arxiv: batch {n // BATCH + 1} unparsable: {e}", file=sys.stderr)
    return out


def stamp(path):
    """The arXiv id printed in the margin of page 1 (`arXiv:2310.02541v2 [cs.LG] 4 Oct 2023`),
    or None: not a PDF, no text layer, a journal version without the stamp, pymupdf missing.
    Only the dated margin form counts, so a citation in a footnote cannot pass as the stamp."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
        text = doc[0].get_text() if doc.page_count else ""
        doc.close()
    except Exception:
        return None
    m = STAMP.search(text)
    return m.group(1) if m else None


def surname(name):
    parts = re.sub(r"[^\w\s'-]", " ", name or "").split()
    return parts[-1].lower() if parts else ""


def same_paper(meta, expected_authors=(), expected_title=""):
    """Guard against a wrong `url:` — the fetched record must mention someone we expect,
    or share most of the title. Prevents overwriting a page with a stranger's author list."""
    got = {surname(a) for a in meta.get("authors", [])}
    if any(surname(a) in got for a in expected_authors if a):
        return True
    words = lambda t: {w for w in re.findall(r"[a-z]{4,}", (t or "").lower())}
    a, b = words(meta.get("title")), words(expected_title)
    return bool(a and b) and len(a & b) >= 0.6 * min(len(a), len(b))


def _words(t):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (t or "").lower())} - {"the", "and", "for", "with", "via"}


def title_match(a, b):
    """Overlap of significant title words, 0..1, relative to the shorter title."""
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0


def search_title(title, expected_authors, opener=None, min_title=0.8):
    """Find the arXiv record for `title`. Accepted only if the title matches closely AND one of
    `expected_authors` is on it — two independent signals, so a wrong id is never adopted.
    None = no confident match; ArxivUnavailable = the API did not answer."""
    q = " AND ".join(f"ti:{w}" for w in sorted(_words(title), key=len, reverse=True)[:8])
    url = f"{API}?{urllib.parse.urlencode({'search_query': q, 'max_results': 10})}"
    try:
        hits = _parse(_get(url, opener))
    except ET.ParseError as e:
        raise ArxivUnavailable(f"bad XML: {e}") from e
    # ArxivUnavailable propagates: "no match" and "could not ask" must stay different answers
    want = {surname(a) for a in expected_authors if a}
    best = None
    for meta in hits.values():
        score = title_match(meta["title"], title)
        if score < min_title or not (want & {surname(a) for a in meta["authors"]}):
            continue
        if not best or score > best[0]:
            best = (score, meta)
    return best[1] if best else None

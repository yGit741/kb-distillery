"""Lookup existing raw/wiki entries before scrap. Zero LLM."""
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Literal

from kb_distillery.lint.lint import parse_frontmatter, read_manifest, walk
from kb_distillery.core.schema import DUPE_PREFIX, INK_PREFIX, WIKI_DIR

from .paths import ROOT

# New-style IDs (2007+): 1906.05890. Old-style (pre-2007): math/9811157, math.PR/0503503,
# hep-th/9901001 — an archive name, optional subject class, a slash, then YYMMNNN.
_ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z][a-z-]*(?:\.[A-Z]{2})?/\d{7})"
ARXIV_ABS = re.compile(r"arxiv\.org/abs/" + _ARXIV_ID + r"(v\d+)?", re.I)
ARXIV_PDF = re.compile(r"arxiv\.org/pdf/" + _ARXIV_ID + r"(v\d+)?", re.I)
ARXIV_BARE = re.compile(r"^" + _ARXIV_ID + r"(?:v\d+)?$", re.I)
ARXIV_FILENAME = re.compile(r"arxiv-(\d{4})-(\d+)", re.I)


class DuplicateBlocked(Exception):
    """Raised when scrap would duplicate vault content."""

    def __init__(self, matches):
        self.matches = matches


@dataclass
class ResolveResult:
    status: Literal["found", "not_found", "ambiguous"]
    matches: list = field(default_factory=list)
    query: str = ""


def normalize_arxiv_id(text):
    """Return base arXiv ID without version suffix, or None."""
    text = re.sub(r"^arxiv:\s*", "", (text or "").strip(), flags=re.I)
    for pat in (ARXIV_ABS, ARXIV_PDF):
        m = pat.search(text)
        if m:
            return m.group(1)
    m = ARXIV_BARE.match(text)
    if m:
        return m.group(1)
    m = ARXIV_FILENAME.search(text)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()[:12]


def _title_from_text(text):
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def _is_skipped_disposition(disp):
    if not disp:
        return False
    return disp == "skip" or disp.startswith(DUPE_PREFIX) or disp.startswith(INK_PREFIX)


@dataclass
class VaultIndexes:
    by_sha1: dict = field(default_factory=dict)
    by_arxiv: dict = field(default_factory=dict)
    by_raw: dict = field(default_factory=dict)
    by_slug: dict = field(default_factory=dict)
    by_alias: dict = field(default_factory=dict)      # old slug → entry (pages keep it in aliases:)
    title_entries: list = field(default_factory=list)


def _links_out_arxiv_ids(text):
    m = re.search(r"^## Links out\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return []
    return [x.group(1) for pat in (ARXIV_ABS, ARXIV_PDF) for x in pat.finditer(m.group(1))]


def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def arxiv_title(aid):
    """The arXiv title for an id, or None when offline / unknown. Never raises."""
    if os.environ.get("KB_OFFLINE") or os.environ.get("KB_CI"):
        return None
    try:
        from . import arxiv_meta
        meta = arxiv_meta.fetch([aid], pause=0).get(aid)
        return meta["title"] if meta else None
    except Exception:
        return None


def _title_fallback(idx, aid):
    """No hit by arXiv id: ask arXiv for the title (only if reachable) and match it against pages."""
    title = _norm_title(arxiv_title(aid))
    if not title:
        return []
    return [_match_entry(e, f"arxiv:{aid} (title match)") for e in idx.title_entries
            if _norm_title(e.get("title")) == title]


def build_indexes():
    """Build lookup indexes from corpus.tsv and wiki frontmatter."""
    idx = VaultIndexes()
    manifest = read_manifest()

    for path, row in manifest.items():
        h = row.get("sha1", "")
        disp = row.get("disposition", "")
        if h and not _is_skipped_disposition(disp):
            idx.by_sha1.setdefault(h, []).append(path)

    for rel in walk(WIKI_DIR, ".md"):
        if "excalidraw" in rel:
            continue
        slug = os.path.basename(rel)[:-3]
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            text = f.read()
        fm = parse_frontmatter(text)
        if not fm:
            continue
        raws = [str(r) for r in (fm.get("raw") if isinstance(fm.get("raw"), list) else [fm.get("raw")])
                if r and str(r) != "none"]
        url = str(fm.get("url") or "")
        title = _title_from_text(text)
        entry = {"slug": slug, "raw": ", ".join(raws), "url": url,
                 "title": title, "wiki": rel, "reason": ""}
        idx.by_slug[slug] = entry
        for raw in raws:
            idx.by_raw[raw] = slug
        aliases = fm.get("aliases") or []
        for a in [aliases] if isinstance(aliases, str) else aliases:
            idx.by_alias[a.strip("\"' ")] = entry
        aid = normalize_arxiv_id(url)
        if aid:
            idx.by_arxiv[aid] = entry
        # a publisher `url:` hides the arXiv id: honour an explicit `arxiv:` key, then any arXiv
        # link under `## Links out` (first claim wins; the url: above always outranks these)
        explicit = normalize_arxiv_id(str(fm.get("arxiv") or ""))
        if explicit:
            idx.by_arxiv.setdefault(explicit, entry)
        for found in _links_out_arxiv_ids(text):
            idx.by_arxiv.setdefault(found, entry)
        idx.title_entries.append(entry)

    return idx


def _match_entry(entry, reason, sha1=None):
    m = dict(entry)
    m["reason"] = reason
    if sha1:
        m["sha1"] = sha1
    return m


def resolve(query):
    """Resolve a query to existing vault content."""
    query = (query or "").strip()
    if not query:
        return ResolveResult(status="not_found", query=query)

    idx = build_indexes()
    matches = []

    aid = normalize_arxiv_id(query)
    if aid and aid in idx.by_arxiv:
        matches.append(_match_entry(idx.by_arxiv[aid], f"arxiv:{aid}"))

    if aid and not matches:
        matches.extend(_title_fallback(idx, aid))

    yt = re.search(r"(?:youtube\.com/.*[?&]v=|youtu\.be/|youtube\.com/(?:shorts|live|embed)/)([A-Za-z0-9_-]{11})", query)
    if yt:                                    # a scrap-youtube bundle, digested or not
        from .youtube.bundle import ITEM, existing
        for folder in existing(yt.group(1), ROOT):
            raw = f"{folder}/{ITEM}"
            slug = idx.by_raw.get(raw)
            matches.append(_match_entry(idx.by_slug[slug], f"youtube:{yt.group(1)}") if slug in idx.by_slug
                           else {"slug": None, "raw": raw, "reason": f"youtube:{yt.group(1)}"})

    qnorm = query.replace(os.sep, "/").lstrip("./")
    if qnorm.startswith("raw/") and qnorm in idx.by_raw:
        slug = idx.by_raw[qnorm]
        matches.append(_match_entry(idx.by_slug[slug], "raw path"))

    slug_q = qnorm
    if slug_q.endswith(".md"):
        slug_q = slug_q[:-3]
    if slug_q.startswith("wiki/"):
        slug_q = os.path.basename(slug_q)[:-3]
    if slug_q in idx.by_slug:
        matches.append(_match_entry(idx.by_slug[slug_q], "slug"))
    elif slug_q in idx.by_alias:
        matches.append(_match_entry(idx.by_alias[slug_q], f"old slug {slug_q} (aliases:)"))

    if not matches:
        qlower = query.lower()
        for entry in idx.title_entries:
            slug = entry["slug"]
            title = (entry.get("title") or "").lower()
            if qlower in slug.lower() or (title and qlower in title):
                matches.append(_match_entry(entry, "title/substring"))

    seen = set()
    unique = []
    for m in matches:
        key = m.get("slug"), m.get("raw")
        if key not in seen:
            seen.add(key)
            unique.append(m)

    if not unique:
        return ResolveResult(status="not_found", query=query)
    if len(unique) > 3:
        return ResolveResult(status="ambiguous", matches=unique, query=query)
    return ResolveResult(status="found", matches=unique, query=query)


def find_by_sha1(sha1_hash, exclude_path=None):
    """Return canonical paths with this content hash."""
    idx = build_indexes()
    paths = idx.by_sha1.get(sha1_hash, [])
    return [p for p in paths if p != exclude_path]


def exit_code(result):
    if result.status == "found":
        return 0
    if result.status == "ambiguous":
        return 2
    return 1


def format_human(result):
    lines = []
    if result.status == "not_found":
        lines.append(f"NOT_FOUND  {result.query}")
        return "\n".join(lines)
    if result.status == "ambiguous":
        lines.append(f"AMBIGUOUS  {result.query} ({len(result.matches)} matches)")
    else:
        lines.append(f"FOUND  {result.query}")
    for m in result.matches:
        page = f"wiki/{m['slug']}" if m.get("slug") else "(no page yet)"
        lines.append(f"  {page}  {m.get('raw') or '(no raw)'}")
        if m.get("url"):
            lines.append(f"       url: {m['url']}")
        if m.get("reason"):
            lines.append(f"       via: {m['reason']}")
    return "\n".join(lines)

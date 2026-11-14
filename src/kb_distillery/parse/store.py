"""Parsed pages on disk: `<root>/<raw-sha1>/manifest.json` plus `pNNNN.json`, one per page.

JSON, not Markdown (lint treats every `meta/**/*.md` as a wikilink target). Status per page is `verified` (no flag, no
mark), `repaired` (a model fix that passed the verifier), `marked` (a transcript whose unsure places carry `!` / `!!`
mark links, see `transcribe`) or `needs-human`; nothing else reaches a digest as checked text.
`root` is always a parameter: the live location is `<kb>/meta/parsed` (`parsed_root`), tests pass a tmp dir.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter

STATUSES = ("verified", "repaired", "marked", "needs-human")


def parsed_root(kb_root: str) -> str:
    return os.path.join(kb_root, "meta", "parsed")


def sha1_bytes(data: bytes) -> str:
    """Key of a raw file; the caller reads the bytes through kb.storage.raw."""
    return hashlib.sha1(data).hexdigest()


def status_for(flags: list) -> str:
    return "needs-human" if flags else "verified"


def _dir(root: str, sha: str) -> str:
    if not sha or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("raw sha1 must be lower-case hex, got %r" % (sha,))
    return os.path.join(root, sha)


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def page_path(root: str, sha: str, page: int) -> str:
    return os.path.join(_dir(root, sha), "p%04d.json" % page)


def write_page(root: str, sha: str, page: int, markdown: str, flags: list, status: str | None = None,
               engine: str = "", repaired_from: str = "") -> dict:
    """Store one page. `status` defaults to verified / needs-human from the flags; a verified page cannot carry flags."""
    status = status or status_for(flags)
    if status not in STATUSES:
        raise ValueError("status %r not in %s" % (status, STATUSES))
    if status in ("verified", "repaired") and flags:
        raise ValueError("a %s page has no flags (page %d has %d)" % (status, page, len(flags)))
    if status == "repaired" and not repaired_from:
        raise ValueError("a repaired page records what it was repaired from")
    rec = {"page": page, "status": status, "markdown": markdown, "engine": engine,
           "flags": [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in flags]}
    if repaired_from:
        rec["repaired_from"] = repaired_from
    _write_json(page_path(root, sha, page), rec)
    return rec


def write_transcript_page(root: str, sha: str, page: int, markdown: str, marks: list, engine: str = "",
                          figures: list | None = None) -> dict:
    """Store one page of a marked transcript: `verified` without marks, `marked` with them (the records ride along).
    `figures`: the page's figure records (`parse.figures`), each with its PNG under `figures/`."""
    rec = {"page": page, "status": "marked" if marks else "verified", "markdown": markdown, "engine": engine,
           "flags": [], "marks": [dict(m) for m in marks], "figures": [dict(f) for f in figures or []]}
    _write_json(page_path(root, sha, page), rec)
    return rec


def transcript(root: str, sha: str, pages: list) -> str | None:
    """The stored pages joined in order, mark links included; None when any of them is missing or needs a human."""
    recs = [read_page(root, sha, n) for n in pages]
    if not recs or any(r is None or r["status"] == "needs-human" for r in recs):
        return None
    return "\n\n".join(r["markdown"].strip() for r in recs) + "\n"


def marks(root: str, sha: str, pages: list | None = None) -> list:
    """Every mark record of the stored pages, each with its `page`."""
    out = []
    for n in (pages if pages is not None else pages_on_disk(root, sha)):
        rec = read_page(root, sha, n)
        for m in (rec or {}).get("marks", []):
            out.append(dict(m, page=n))
    return out


def figures(root: str, sha: str, pages: list | None = None) -> list:
    """Every figure record of the stored pages, in page order, each with its `page`."""
    out = []
    for n in (pages if pages is not None else pages_on_disk(root, sha)):
        rec = read_page(root, sha, n)
        for f in (rec or {}).get("figures", []):
            out.append(dict(f, page=n))
    return out


def read_page(root: str, sha: str, page: int) -> dict | None:
    try:
        with open(page_path(root, sha, page), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def pages_on_disk(root: str, sha: str) -> list:
    try:
        names = os.listdir(_dir(root, sha))
    except FileNotFoundError:
        return []
    return sorted(int(n[1:-5]) for n in names if n[0] == "p" and n.endswith(".json") and n[1:-5].isdigit())


def write_manifest(root: str, sha: str, source: str, page_count: int, engine: str = "") -> dict:
    """Manifest = what was parsed plus the per-status rollup of the pages now on disk."""
    counts: Counter = Counter()
    on_disk = pages_on_disk(root, sha)
    for n in on_disk:
        rec = read_page(root, sha, n)
        if rec:
            counts[rec["status"]] += 1
    m = {"sha1": sha, "source": source, "pages": page_count, "engine": engine,
         "status": {s: counts.get(s, 0) for s in STATUSES},
         "missing": [n for n in range(1, page_count + 1) if n not in set(on_disk)]}
    _write_json(os.path.join(_dir(root, sha), "manifest.json"), m)
    return m


def read_manifest(root: str, sha: str) -> dict | None:
    try:
        with open(os.path.join(_dir(root, sha), "manifest.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def checked_text(root: str, sha: str, pages: list | None = None) -> str | None:
    """The stored transcript for `pages` when every one is verified or repaired, else None. Without `pages` it needs
    the whole document: the manifest's page count, every page stored, none needing a human."""
    if pages is None:
        m = read_manifest(root, sha)
        if not m:
            return None
        want = list(range(1, m["pages"] + 1))
    else:
        want = list(pages)
    recs = [read_page(root, sha, n) for n in want]
    if not recs or any(r is None or r["status"] == "needs-human" for r in recs):
        return None
    return "\n\n".join(r["markdown"] for r in recs)


RESOLUTION_ACTIONS = ("correct", "fixed")


def resolutions_path(root: str, sha: str) -> str:
    return os.path.join(_dir(root, sha), "resolutions.json")


def resolutions(root: str, sha: str) -> dict:
    """What the owner decided about marks: `{"p0188/3": {action, text, slug, time}}`; empty when nothing is decided."""
    try:
        with open(resolutions_path(root, sha), encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_resolution(root: str, sha: str, page: int, mark_id: int, action: str, text: str, slug: str,
                     time: str | None = None) -> dict:
    """Record one decision: `correct` (the formula stays as it is, `text` empty) or `fixed` (`text` is the replacement)."""
    if action not in RESOLUTION_ACTIONS:
        raise ValueError("action %r not in %s" % (action, RESOLUTION_ACTIONS))
    import datetime
    rec = {"action": action, "text": text if action == "fixed" else "", "slug": slug,
           "time": time or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    data = resolutions(root, sha)
    data["p%04d/%d" % (page, mark_id)] = rec
    _write_json(resolutions_path(root, sha), data)
    return rec

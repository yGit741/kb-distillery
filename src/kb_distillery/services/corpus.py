"""Per-format corpus tables, raw previews, the easy-digest action and the citation graph for the
graph's data layer (0 LLM, read-only apart from the easy-digest subprocess). Columns beyond
corpus.tsv are computed at view time and never written back."""
import json
import os
import subprocess
import sys
from urllib.parse import urlparse

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.graph import raw_layer
from kb_distillery.lint.lint import collections_of, read_manifest
from kb_distillery.search.semfind import load_pages

ROOT = raw_layer.ROOT
FORMATS = tuple(f for f in raw_layer.FORMATS if f != "inbox")
CACHE_DIR = os.path.join(ROOT, ".cache")
PAGES_CACHE = os.path.join(CACHE_DIR, "corpus-pages.json")
STAMPS_CACHE = os.path.join(CACHE_DIR, "arxiv-stamps.json")
CITATIONS_CACHE = os.path.join(CACHE_DIR, "citations.json")
PREVIEW_CHARS = 4000
ACTIONS = ("easy-digest",)
ACTION_TIMEOUT = 300
from kb_distillery.vault.schema import COLLECTION_TYPES

COMMON = [("path", "File"), ("disposition", "Disposition"), ("digestion", "Digest"), ("slug", "Page"),
          ("collection", "Collection"), ("year", "Year"), ("sha1", "sha1")]
EXTRA = {
    "printed-docs": [("title", "Title"), ("authors", "Authors"), ("url", "URL"), ("pages", "Pages"),
                     ("stamp", "arXiv stamp")],
    "handwritten": [("pages", "Pages"), ("hub", "Notebook / course")],
    "presentations": [("pages", "Slides"), ("hub", "Course")],
    "emails": [("thread_date", "Thread date"), ("attachments", "Attachments")],
    "web-clips": [("domain", "Source domain"), ("assets", "Assets")],
    "images": [("companion_of", "Belongs to")],
    "llm-chats": [("chat", "Chat page")],
}


def columns(fmt):
    return [{"key": k, "label": l} for k, l in COMMON + EXTRA.get(fmt, [])]


def check_raw_path(rel):
    """Validate a path for preview/actions. Returns (abs_path, None) or (None, reason).
    Only existing-or-not files strictly under raw/ and never under raw/inbox/."""
    if not isinstance(rel, str) or not rel.startswith("raw/") or "\x00" in rel:
        return None, "path must be under raw/"
    parts = rel.split("/")
    if ".." in parts or len(parts) < 3:
        return None, "path must be a file under raw/<format>/"
    if parts[1] == "inbox":
        return None, "raw/inbox/ is not part of the data layer"
    raw_root = os.path.realpath(os.path.join(ROOT, "raw"))
    full = os.path.realpath(os.path.join(ROOT, rel))
    if not full.startswith(raw_root + os.sep):
        return None, "path escapes raw/"
    real_rel = os.path.relpath(full, raw_root).split(os.sep)
    if real_rel[0] == "inbox":
        return None, "raw/inbox/ is not part of the data layer"
    return full, None


def validate_action(action, path):
    """(error|None). Only easy-digest is runnable; full/deep are shown as commands in the UI."""
    if action not in ACTIONS:
        return f"unknown action {action!r}; supported: {', '.join(ACTIONS)}"
    _, err = check_raw_path(path)
    return err


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _page_count(rel, sha1, cache, dirty):
    key = sha1 or rel
    if key in cache:
        return cache[key]
    full = os.path.join(ROOT, rel)
    n = None
    if rel.lower().endswith(".pdf") and os.path.isfile(full):
        try:
            from kb_distillery.storage.pdf import PdfDoc
            with PdfDoc(full) as doc:
                n = doc.page_count
        except Exception:  # noqa: BLE001
            n = None
    if n is not None:
        cache[key] = n
        dirty.append(1)
    return n


def _authors(fm):
    a = fm.get("authors")
    return ", ".join(str(x) for x in a) if isinstance(a, list) else (str(a) if a else "")


def build_corpus(fmt):
    if fmt not in FORMATS:
        return None
    pages = load_pages()
    cites = raw_layer.page_sources(pages)
    manifest = {p: r for p, r in read_manifest().items() if r.get("disposition") != "sidecar"}
    stamps = _load_json(STAMPS_CACHE, {})
    page_cache, dirty = _load_json(PAGES_CACHE, {}), []
    asset_count, folder_files = {}, {}
    for p, r in manifest.items():
        head, tgt = raw_layer.split_disposition(r.get("disposition"))
        if head == "asset" and tgt:
            asset_count[tgt] = asset_count.get(tgt, 0) + 1
        if raw_layer.raw_format(p, r) == "emails":
            folder_files.setdefault(os.path.dirname(p), []).append(p)

    rows = []
    for path, r in sorted(manifest.items()):
        if raw_layer.raw_format(path, r) != fmt:
            continue
        disp, comp = raw_layer.split_disposition(r.get("disposition"))
        if fmt == "emails" and disp == "asset":
            continue                      # attachments fold into their thread row
        slug = (r.get("slug") or "").strip()
        citing = sorted(cites.get(path, ()))
        slug = slug if slug in pages else (citing[0] if citing else "")
        fm = pages[slug][1] if slug else {}
        coll = collections_of(r)
        row = {"path": path, "disposition": disp, "collection": coll, "slug": slug or None,
               "digestion": fm.get("depth") or "", "year": raw_layer.year_of(path),
               "sha1": (r.get("sha1") or "")[:10], "companion_of": comp,
               "title": pages[slug][2].split("\n# ", 1)[-1].split("\n", 1)[0] if slug and "\n# " in pages[slug][2]
               else raw_layer.prettify(path)}
        hubs = [c for c in coll if c in pages and pages[c][1].get("type") in COLLECTION_TYPES]
        if fmt == "printed-docs":
            row["authors"] = _authors(fm)
            row["url"] = fm.get("url") or (f"arXiv:{fm['arxiv']}" if fm.get("arxiv") else "")
            row["pages"] = _page_count(path, r.get("sha1"), page_cache, dirty)
            st = stamps.get(path) or stamps.get(r.get("sha1") or "")
            row["stamp"] = (st if isinstance(st, str) else json.dumps(st)) if st else ""
        elif fmt in ("handwritten", "presentations"):
            row["pages"] = _page_count(path, r.get("sha1"), page_cache, dirty)
            row["hub"] = ", ".join(hubs)
        elif fmt == "emails":
            row["thread_date"] = os.path.basename(os.path.dirname(path))[:10]
            row["attachments"] = max(0, len(folder_files.get(os.path.dirname(path), [])) - 1)
        elif fmt == "web-clips":
            src = fm.get("source") or fm.get("url") or ""
            row["domain"] = urlparse(str(src)).netloc if src else ""
            row["assets"] = asset_count.get(path, 0)
        elif fmt == "llm-chats":
            row["chat"] = slug or ""
        rows.append(row)
    if dirty:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(PAGES_CACHE, "w", encoding="utf-8") as f:
                json.dump(page_cache, f)
        except OSError:
            pass
    return {"format": fmt, "columns": columns(fmt), "rows": rows, "count": len(rows)}


def build_preview(rel):
    """({meta..., text}, None) or (None, error). Never reads raw/inbox/ or outside raw/."""
    full, err = check_raw_path(rel)
    if err:
        return None, err
    row = read_manifest().get(rel)
    meta = {"path": rel, "exists": os.path.isfile(full), "ext": os.path.splitext(rel)[1].lstrip(".").lower(),
            "file_url": "/raw-file?path=" + rel, "format": rel.split("/")[1]}
    if row:
        meta["disposition"] = row.get("disposition")
        meta["slug"] = row.get("slug") or None
        meta["collection"] = collections_of(row)
    text = ""
    if meta["exists"] and meta["ext"] not in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
        try:
            from kb_distillery.ingest.extract import extract_text
            text = (extract_text(full, max_pages=2) or "")[:PREVIEW_CHARS]
        except Exception as e:  # noqa: BLE001
            meta["error"] = f"{type(e).__name__}: {e}"
    meta["text"] = text
    return meta, None


def run_action(action, rel):
    """Run easy-digest on one raw file; (result, error)."""
    err = validate_action(action, rel)
    if err:
        return None, err
    cmd = [sys.executable, "-m", "kb_distillery.ingest", "easy-digest", rel]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=ACTION_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"timed out after {ACTION_TIMEOUT}s", "command": " ".join(cmd[2:])}, None
    return {"exit": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-2000:],
            "command": "python3 -m kb_distillery.ingest easy-digest " + rel}, None


def build_citations():
    """Citation graph among cataloged papers from .cache/citations.json: A cites B."""
    data = _load_json(CITATIONS_CACHE, None)
    if not isinstance(data, dict) or not isinstance(data.get("papers"), dict):
        return {"nodes": [], "links": [], "missing": True}
    papers = data["papers"]
    mine = {pid: p for pid, p in papers.items() if p.get("slug")}
    nodes = [{"id": p["slug"], "title": p.get("title") or p["slug"], "year": p.get("year"),
              "citationCount": p.get("citationCount") or 0} for p in mine.values()]
    links, seen = [], set()
    for pid, p in mine.items():
        for ref in p.get("references") or []:
            q = mine.get(ref)
            if q and (p["slug"], q["slug"]) not in seen:
                seen.add((p["slug"], q["slug"]))
                links.append({"source": p["slug"], "target": q["slug"]})
    return {"nodes": nodes, "links": links}

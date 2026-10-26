"""Build the pipeline snapshot for the dashboard (0 LLM): every raw file, its format, status,
digest depth and collections, plus collection-hub coverage and the side queues."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb.core.coherence import load_warnings
from kb.lint.lint import collect_snapshot, collections_of, parse_frontmatter, raw_paths
from kb.core.schema import (DEPTH, COLLECTION_TYPES, PARTITION_COLLECTIONS, SOURCE_TYPES, RAW_DIR,  # noqa: E402
                    RAW_EMAILS, RAW_INBOX, RAW_VIDEOS, VIDEO_ITEM, RAW_PRINTED, CONTENTS_COLLECTIONS, WIKI_DIR)

ROOT = vault_root()  # KB_ROOT: share build
INGEST_ROOT = os.path.join(ROOT, "meta", ".ingest")
DISTILL_ROOT = os.path.join(ROOT, "meta", ".distill")
CATALOG_LOG_DIR = os.path.join(ROOT, "meta", ".catalog")
INGESTION_ORDER = ("inbox", "failed", "uncataloged", "cataloged")
COMPANION_STATUS = ("ink", "dupe", "asset")     # dispositions that fold a file into another file
DIGESTION_ORDER = ("not digested", "partial", "digested", "skipped")
STARTED_AT = time.time()
CODE_DIRS = ("backend/src/kb", "backend/src/kb/core", "backend/src/kb/dashboard", "backend/src/kb/dashboard/static",
             "backend/src/kb/ingest", "backend/src/kb/ops", "backend/src/kb/services")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _code_mtime():
    """Newest mtime of the code this server runs — newer than STARTED_AT means stale."""
    newest = 0.0
    for d in CODE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if fn.endswith((".py", ".js", ".css", ".html")):
                newest = max(newest, os.path.getmtime(os.path.join(base, fn)))
    return newest


def _infer_ingest_stage(sdir, session):
    if session.get("status") == "finalizing":
        return "finalizing"
    staging = os.path.join(sdir, "staging")
    if os.path.isdir(staging) and any(f.endswith(".md") for f in os.listdir(staging)):
        return "draft"
    if os.path.isfile(os.path.join(sdir, "plan.json")):
        return "map"
    if os.path.isfile(os.path.join(sdir, "claims.json")):
        return "extract"
    return "begin"


def _load_active_ingest():
    sessions = []
    if not os.path.isdir(INGEST_ROOT):
        return sessions
    for sha in sorted(os.listdir(INGEST_ROOT)):
        sp = os.path.join(INGEST_ROOT, sha, "session.json")
        if not os.path.isfile(sp):
            continue
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        if s.get("status") != "open":
            continue
        sdir = os.path.join(INGEST_ROOT, sha)
        sessions.append({
            "sha": sha,
            "raw": s.get("raw", ""),
            "depth": s.get("depth", "full"),
            "stage": _infer_ingest_stage(sdir, s),
            "opened_at": s.get("opened_at", ""),
        })
    return sessions


def _load_distill_review(pages):
    review = []
    for slug, (rel, fm, _text) in pages.items():
        if fm.get("type") != "distilled-think" or fm.get("status") != "review":
            continue
        source = str(fm.get("source", ""))
        proposals = 0
        think_rel = source.replace("\\", "/")
        if think_rel.startswith("think/"):
            sid = hashlib.sha1(think_rel.encode()).hexdigest()[:12]
            plan_path = os.path.join(DISTILL_ROOT, sid, "plan.json")
            if os.path.isfile(plan_path):
                with open(plan_path, encoding="utf-8") as f:
                    plan = json.load(f)
                proposals = len(plan.get("proposals", []))
        review.append({"slug": slug, "source": source, "path": rel, "proposals": proposals})
    return sorted(review, key=lambda x: x["slug"])


def _load_pages():
    pages = {}
    base = os.path.join(ROOT, WIKI_DIR)
    if not os.path.isdir(base):
        return pages
    for fn in os.listdir(base):
        if not fn.endswith(".md") or "excalidraw" in fn:
            continue
        rel = f"{WIKI_DIR}/{fn}"
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        fm = parse_frontmatter(text)
        if fm:
            pages[fn[:-3]] = (rel, fm, text)
    return pages


def _title(text, slug):
    for line in text.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return slug


# --------------------------------------------------------------------------
# collections: book/notebook partitions and course/series contents tables
# --------------------------------------------------------------------------
def _collections(pages):
    from kb.core.books import coverage as page_coverage, parse_partition
    from kb.core import hubs
    out = []
    for slug, (_rel, fm, text) in sorted(pages.items()):
        t = fm.get("type")
        if t not in COLLECTION_TYPES:
            continue
        if t in PARTITION_COLLECTIONS:
            rows = parse_partition(text)
            done, total = page_coverage(rows) if rows else (0, 0)
            unit = "pp"
            rows = [{"title": r["title"], "pages": [r["start"], r["end"]], "status": r["status"],
                     "slug": r["slug"], "raws": []} for r in rows]
        else:
            rows = hubs.parse_contents(text)
            done, total = hubs.coverage(rows) if rows else (0, 0)
            unit = "items"
            rows = [{"title": r["title"], "pages": None, "status": r["status"], "slug": r["slug"],
                     "raws": r["raws"]} for r in rows]
        out.append({
            "slug": slug, "type": t, "title": _title(text, slug),
            "raw": ", ".join(raw_paths(fm)), "status": str(fm.get("status") or ""),
            "covered": done, "total": total, "unit": unit,
            "pct": round(100 * done / total) if total else 0, "rows": rows,
        })
    return out


# --------------------------------------------------------------------------
# items: one per raw file
# --------------------------------------------------------------------------
def _split_disposition(disp):
    """`dupe:<path>` / `ink:<path>` / `asset:<path>` → (status, target)."""
    status, _, target = (disp or "queued").partition(":")
    return status, target


def _unit(rel, kind):
    """An email thread or a video bundle is one unit (its folder); every other file is one unit."""
    parts = rel.split("/")
    return "/".join(parts[:3]) if kind in (RAW_EMAILS, RAW_VIDEOS) and len(parts) > 3 else rel


def _depth(slug, pages):
    """Digest depth of the page that cites a file: listed / easy / full / deep."""
    page = pages.get(slug)
    if not page:
        return ""
    fm = page[1]
    if fm.get("type") in SOURCE_TYPES:
        ds = fm.get("depth")
        return ds if ds in DEPTH else ""
    return ""


def _row_index(rel, colls, row_hub):
    """(hub, 1-based row) of the first course/series table listing this file."""
    for c in colls:
        hit = row_hub.get((c, rel))
        if hit:
            return c, hit
    return None, None


def _next_step(rel, kind, status, ext, hub, row):
    """Only commands the CLI handles today."""
    if status == "queued":
        if rel.startswith(f"{RAW_DIR}/{RAW_INBOX}/"):
            return f"python3 -m kb.ingest catalog {rel} --collection <hub-or-person>"
        if hub:
            return f"python3 -m kb.ingest full-digest {hub} --row {row}"
        if kind == RAW_PRINTED and ext == ".pdf":
            return f"python3 -m kb.ingest easy-digest {rel}"
    if status == "partial":
        return f"python3 -m kb.ingest toc {rel}"
    return ""


def _load_catalog_log(kind):
    path = os.path.join(CATALOG_LOG_DIR, f"{kind}.jsonl")
    out = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


_KB_OP = re.compile(r"^kb\((\w+)\)")


def _wiki_commit_times(root=None, rev=None):
    """Latest commit touching each wiki page, from one history pass: path → (iso-utc, op).
    `op` is the kb(<op>) of that commit's subject (digest, refine, catalog…) or 'edit'.
    `root`/`rev` let the share build read a content commit's history from the real repo
    (an archive checkout has no history of its own)."""
    vcs = "g" + "it"                                         # read-only; the write guard greps for the word
    try:
        out = subprocess.run([vcs, "log", "--format=%x00%cI %s", "--name-only", *([rev] if rev else []),
                              "--", WIKI_DIR],
                             cwd=root or ROOT, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    seen, ts, op = {}, "", ""
    for line in out.splitlines():
        if line.startswith("\x00"):
            stamp, _, subject = line[1:].partition(" ")
            try:
                ts = datetime.fromisoformat(stamp).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                ts = ""
            m = _KB_OP.match(subject)
            op = m.group(1) if m else "edit"
        elif line and line not in seen and ts:
            seen[line] = (ts, op)        # log is newest-first, so the first hit wins
    return seen


def _last_op(rel, slug, cataloged_at, wiki_times, mtime):
    """The most recent operation on a file: cataloged, or its page committed (digest, refine…).
    Disk mtime is only a fallback for files nothing has touched yet — checkouts and cloud sync
    rewrite mtimes, so it must never outrank a recorded operation. Returns (iso-utc, op)."""
    cands = []
    if rel in cataloged_at:
        cands.append((cataloged_at[rel], "catalog"))
    if slug and f"{WIKI_DIR}/{slug}.md" in wiki_times:
        cands.append(wiki_times[f"{WIKI_DIR}/{slug}.md"])
    if cands:
        return max(cands)
    return (_iso(mtime), "modified") if mtime else ("", "")


def _companion_of(rel, kind, status, target):
    """A file that only makes sense next to another: ink overlay, duplicate copy, a figure
    downloaded with a web clip, an email thread's attachments or parsed.md sidecar.
    Returns the parent path, or ''."""
    if status in COMPANION_STATUS:
        return target
    parts = rel.split("/")
    if kind == RAW_EMAILS and len(parts) > 3 and parts[-1] != "thread.md":
        return "/".join(parts[:3]) + "/thread.md"
    if kind == RAW_VIDEOS and len(parts) > 3 and parts[-1] != VIDEO_ITEM:
        return "/".join(parts[:3]) + "/" + VIDEO_ITEM
    return ""


def _ingestion(rel, status, slug, hub_row, failed, cataloged):
    """Did the file get into the vault properly? inbox · failed · uncataloged · cataloged."""
    if rel.startswith(f"{RAW_DIR}/{RAW_INBOX}/"):
        return "failed" if rel in failed else "inbox"
    if (slug or hub_row or status in ("skip", "partial")
            or any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in cataloged)):
        return "cataloged"
    return "uncataloged"


def _digestion(ingestion, status, depth):
    """How far into the wiki? Only defined once cataloged. A listed-depth stub is not a note."""
    if ingestion != "cataloged":
        return ""
    if status == "skip":
        return "skipped"
    if status == "partial":
        return "partial"
    if status == "source" and depth != "listed":
        return "digested"
    return "not digested"


_URL_RE = re.compile(r"^(?:url|source_url|original|link):\s*[\"']?(https?://\S+?)[\"']?\s*$", re.M)


def _source_url(rel, ext):
    """The web address a Markdown raw file was clipped from (frontmatter `url:`), or ""."""
    if ext != ".md":
        return ""
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return ""
    if not head.startswith("---"):
        return ""
    fm = head.split("\n---", 2)[0] if "\n---" in head else head
    m = _URL_RE.search(fm)
    return m.group(1) if m else ""


def _items(rows, pages, collections, now, failed=(), cataloged=(), cataloged_at=None, wiki_times=None):
    cataloged_at, wiki_times = cataloged_at or {}, wiki_times or {}
    row_hub = {}
    for c in collections:
        if c["type"] in CONTENTS_COLLECTIONS:
            for i, r in enumerate(c["rows"], 1):
                for p in r["raws"]:
                    row_hub[(c["slug"], p)] = i
    items = []
    for rel, row in sorted(rows.items()):
        kind = row.get("kind", "") or "other"
        status, target = _split_disposition(row.get("disposition"))
        ext = os.path.splitext(rel)[1].lower()
        colls = collections_of(row)
        hub, hub_row = _row_index(rel, colls, row_hub)
        slug = row.get("slug", "")
        slug = slug if slug in pages else ""       # the manifest keeps slugs of pages since removed
        depth = _depth(slug, pages) if status in ("source", "partial") else ""
        companion = _companion_of(rel, kind, status, target)
        ingestion = _ingestion(rel, status, slug, hub_row, failed, cataloged)
        try:
            st = os.stat(os.path.join(ROOT, rel))
            size_kb, age, mtime = round(st.st_size / 1024, 1), round((now - st.st_mtime) / 86400, 1), st.st_mtime
        except OSError:
            size_kb, age, mtime = 0, None, 0
        last_at, last_op = _last_op(rel, slug, cataloged_at, wiki_times, mtime)
        items.append({
            "path": rel,
            "name": os.path.basename(rel),
            "kind": kind,
            "collections": colls,
            # a companion folds into its parent's item; an email thread is one item
            "unit": _unit(companion, kind) if status in COMPANION_STATUS else _unit(rel, kind),
            "companion_of": companion,
            "status": status,
            "ingestion": ingestion,
            "digestion": _digestion(ingestion, status, depth),
            "depth": depth if depth in ("easy", "full", "deep") else "",
            "target": target,
            "slug": slug,
            "ext": ext,
            "size_kb": size_kb,
            "age_days": age,
            "last_op": last_op,            # catalog | digest | refine | … | modified
            "last_op_at": last_at,         # ISO UTC, minute-exact — the Chron view sorts by it
            "hub_row": hub_row,
            "url": _source_url(rel, ext),   # the page a clip came from — the modal links to it
            "failure": failed.get(rel, "") if isinstance(failed, dict) else "",
            "next": _next_step(rel, kind, status, ext, hub, hub_row),
        })
    return items


def build_digestion_snapshot():
    snap = collect_snapshot(quiet=True)
    rows = snap.pop("_rows", {})
    pages = _load_pages()
    now = time.time()
    collections = _collections(pages)
    failures = {}
    for f in _load_catalog_log("failures"):                 # latest reason per path
        failures[f.get("path", "")] = f.get("reason", "")
    events = _load_catalog_log("events")
    cataloged = {e.get("dest", "") for e in events if e.get("dest")}
    cataloged_at = {}                                        # latest catalog event per dest
    for e in events:
        if e.get("dest") and e.get("ts", "") >= cataloged_at.get(e["dest"], ""):
            cataloged_at[e["dest"]] = e["ts"]
    failures = {p: r for p, r in failures.items() if os.path.exists(os.path.join(ROOT, p))}
    items = _items(rows, pages, collections, now, failures, cataloged, cataloged_at, _wiki_commit_times())
    recent = [dict(e) for e in events[-20:]][::-1]
    inbox = sorted((i for i in items if i["path"].startswith(f"{RAW_DIR}/{RAW_INBOX}/")),
                   key=lambda x: -(x["age_days"] or 0))
    titles = {s: _title(t, s) for s, (_r, _fm, t) in pages.items()
              if _fm.get("type") in COLLECTION_TYPES or _fm.get("type") == "person"}

    warnings = load_warnings()
    coherence = sorted((
        {"id": r["id"], "kind": r.get("kind", ""), "score": int(r.get("score", 0)),
         "slugs": r.get("slugs", ""), "summary": r.get("summary", "")}
        for r in warnings.values() if r.get("status") == "open"), key=lambda x: -x["score"])

    from kb.ingest.backlog import shallow_paper_slugs
    active_ingest = _load_active_ingest()
    distill_review = _load_distill_review(pages)
    shallow_papers = [{"slug": s} for s in shallow_paper_slugs()]

    queued = [i for i in items if i["status"] == "queued"]
    values = snap["values"]
    parents = [i for i in items if not i["companion_of"]]   # one per item; companions never count
    ingestion_counts = {k: sum(1 for i in parents if i["ingestion"] == k) for k in INGESTION_ORDER}
    digestion_counts = {k: sum(1 for i in parents if i["digestion"] == k) for k in DIGESTION_ORDER}
    read_depth = {d: sum(1 for i in parents if i["digestion"] == "digested" and i["depth"] == d)
                  for d in ("easy", "full", "deep")}
    depth_counts = {d: sum(1 for i in items if i["depth"] == d) for d in DEPTH}
    summary = {
        "files": len(items),
        "queued": len(queued),
        "queued_units": len({i["unit"] for i in queued}),
        "queued_mb": round(sum(i["size_kb"] for i in queued) / 1024, 1),
        "inbox_count": len(inbox),
        "items": len(parents),
        "ingestion": ingestion_counts,
        "digestion": digestion_counts,
        "read_depth": read_depth,
        "depth": depth_counts,
        "coherence_internal": values.get("coherence_internal", 0),
        "coherence_external": values.get("coherence_external", 0),
        "coherence_cosmetic": values.get("coherence_cosmetic", 0),
        "coherence_open": len(coherence),
        "active_ingest": len(active_ingest),
        "distill_review": len(distill_review),
        "shallow_papers": len(shallow_papers),
        "collections_open": sum(1 for c in collections if c["total"] and c["covered"] < c["total"]),
        "errors": values.get("errors", 0),
    }

    code_mtime = _code_mtime()
    return {
        "generated_at": snap.get("generated_at", _now()),
        "server": {
            "started_at": _iso(STARTED_AT),
            "code_mtime": _iso(code_mtime) if code_mtime else "",
            "stale": code_mtime > STARTED_AT + 1,
            "root": ROOT,
        },
        "summary": summary,
        "items": items,
        "inbox": inbox,
        "failures": [{"path": p, "reason": r} for p, r in sorted(failures.items())],
        "recent": recent,
        "collections": collections,
        "titles": titles,
        "active_ingest": active_ingest,
        "coherence": coherence,
        "distill_review": distill_review,
        "shallow_papers": shallow_papers,
    }

#!/usr/bin/env python3
"""Vault linter. `backend/src/kb/lint/lint.py` IS the schema — if it passes, the vault is legal.

    python3 -m kb.lint.lint                 check + reconcile + regenerate index.md
    python3 -m kb.lint.lint --health        terminal health summary
    python3 -m kb.lint.lint --dashboard     localhost health UI
    python3 -m kb.lint.lint --coherence-only  semantic coherence checks only (debug)
    python3 -m kb.lint.lint --write-index   no-op (index always regenerated)
    KB_CI=1 python3 -m kb.lint.lint         cloud checkout: raw binaries are gitignored, so the
                                         manifest is read-only and nothing is regenerated

Run by .git/hooks/pre-commit. No third-party dependencies.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

from kb.core.schema import (ASSET_NAME, ASSET_PREFIX, BARE_TYPES, BLANK_PDF_BYTES, CHATS_DIR,
                    PARTIAL_CHECKOUT_MIN, RAW_BINARY_EXTS,
                    DEPRECATED_AREA_SLUGS, DISPOSITIONS, RAW_IMAGES, RAW_WEB,
                    DEPTH, DISTILLED_THINK_PREFIX, DUPE_PREFIX, GENERATED,
                    COLLECTION_TYPES, INK_PREFIX, PARTITION_COLLECTIONS, PAPER_NAME, PAPER_YEAR_MAX, PAPER_YEAR_MIN,
                    INBOX_ERROR, INBOX_STALE_DAYS, INK_SUFFIX,
                    MANIFEST, MANIFEST_COLS, META_DIR, NEEDS_RAW, SOURCE_TYPES, PARSED_FILENAME,
                    PLACEHOLDER_TITLE, RAW_NAME, RAW_NESTED, RAW_DIR, RAW_EMAILS, RAW_INBOX,
                    RAW_PRINTED, RAW_SUBDIRS, RESERVED_PREFIXES, ROOT_DIRS, ROOT_FILES,
                    ROOT_LINT_IGNORE, ROOT_MD, CONTENTS_COLLECTIONS, SIDECAR_ELIGIBLE_KINDS, SLUG_PREFIX,
                    TOPIC_PREFIX, TOPIC_SLUGS, THINK_DIR, TYPE_STATUS, WIKI_DIR, YEARED, strip_prefix,
                    LAYER_OF, RETIRED_DEPTH, RETIRED_DISPOSITIONS, RETIRED_KEYS, RETIRED_TYPES)
from kb.core.books import (DIGESTED, OVERVIEW_HEADING, OVERVIEW_MIN_CHARS, PARTITION_HEADING, SKIP,
                   book_status, coverage, coverage_line, find_row, overview_ok,
                   parse_partition, validate)
from kb.core import hubs
from kb.core import persons
from kb.core import scopes as scope_lib
from kb.core import wikiio
try:
    from kb.ingest import arxiv_meta          # page-1 arXiv stamps (check_arxiv_stamps)
except ImportError:                         # pragma: no cover
    arxiv_meta = None

from kb.paths import vault_root
ROOT = vault_root()  # KB_ROOT: share build
LINK = re.compile(r"\[\[([^\]|#\\]+)")
# Fenced blocks and inline code: `[[1, 2], [3, 4]]` in a code sample is not a wikilink.
CODE = re.compile(r"^\s*(?:>\s*)*(```|~~~).*?^\s*(?:>\s*)*\1[^\n]*$|`[^`\n]+`", re.M | re.S)
errors, warnings, notices = [], [], []
CI_RAW = set()          # KB_CI: manifest paths stand in for the gitignored raw bytes


def ci_mode():
    """`KB_CI=1`: a cloud checkout has corpus.tsv but not the raw PDFs/PNGs it lists."""
    return bool(os.environ.get("KB_CI"))


def missing_binaries(rows):
    """Manifest rows of gitignored raw binaries whose bytes are not in this checkout."""
    return {p for p in rows if os.path.splitext(p)[1].lower() in RAW_BINARY_EXTS
            and p.startswith(f"{RAW_DIR}/") and not os.path.exists(os.path.join(ROOT, p))}


def partial_checkout(rows):
    """A clone, CI run or fresh worktree: the manifest lists raw binaries git never had. Below
    PARTIAL_CHECKOUT_MIN missing files it is a deliberate deletion and reconciles as usual."""
    return len(missing_binaries(rows)) >= PARTIAL_CHECKOUT_MIN


def raw_exists(rel):
    """On disk — or, under KB_CI, a row of the manifest (the bytes are gitignored)."""
    return os.path.exists(os.path.join(ROOT, rel)) or rel in CI_RAW


def _names_guard(text):
    """The hook command runs the write guard: `python3 -m kb.git.guard`, or the pre-#69 `guard.py`."""
    return "kb.git.guard" in text or "guard.py" in text


def hooks_health():
    """Return (status_text, all_ok) for agent write-guard hook configs."""
    cursor_ok = claude_ok = False
    cursor_path = os.path.join(ROOT, ".cursor", "hooks.json")
    claude_path = os.path.join(ROOT, ".claude", "settings.json")
    if os.path.isfile(cursor_path):
        try:
            with open(cursor_path, encoding="utf-8") as f:
                cursor_ok = _names_guard(json.dumps(json.load(f)))
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.isfile(claude_path):
        try:
            with open(claude_path, encoding="utf-8") as f:
                claude_ok = _names_guard(f.read())
        except OSError:
            pass
    status = f"cursor {'ok' if cursor_ok else 'MISS'}, claude {'ok' if claude_ok else 'MISS'}"
    return status, cursor_ok and claude_ok

def err(f, m):  errors.append(f"{f}: {m}")
def warn(f, m): warnings.append(f"{f}: {m}")

def parse_frontmatter(text):
    """Minimal YAML: flat `key: value` and `key: [a, b]`. Enough for this vault."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = {}
    for line in text[3:end].splitlines():
        line = line.split("#")[0].rstrip()
        if not line.strip() or ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip()] = v
    return fm

def raw_paths(fm):
    """`raw:` as a list of paths — a lecture may cite its slides and its notes. `none` → []."""
    v = fm.get("raw")
    vals = v if isinstance(v, list) else [v]
    return [str(x).strip() for x in vals if x and str(x).strip() and str(x).strip() != "none"]


def collections_of(row):
    """corpus.tsv `collection` cell → list of slugs."""
    return [c.strip() for c in (row.get("collection") or "").split(",") if c.strip()]


def walk(d, ext=None):
    out = []
    base = os.path.join(ROOT, d)
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if not x.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            if ext and not fn.endswith(ext):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/"))
    return sorted(out)

# dispositions that bind a file to another file: never backlog, never a hub member of their own
COMPANION = (DUPE_PREFIX, INK_PREFIX, ASSET_PREFIX)
_ASSET_NAME = re.compile(ASSET_NAME, re.I)


def asset_source(rel, on_disk):
    """`raw/images/<clip stem>-NN.png` -> `raw/web-clips/<clip stem>.md` when that clip exists:
    a figure scrap-wordpress downloaded with its post."""
    parts = rel.split('/')
    if len(parts) != 3 or parts[1] != RAW_IMAGES:
        return None
    m = _ASSET_NAME.match(parts[2])
    if not m:
        return None
    clip = f"raw/{RAW_WEB}/{m.group('clip')}.md"
    return clip if clip in on_disk else None


def ink_source(rel, on_disk):
    """`X.pdf (annotations).pdf` -> `X.pdf`. reMarkable leaves the original
    extension in the stem, so try both the plain and de-doubled forms."""
    if INK_SUFFIX not in os.path.basename(rel):
        return None
    cand = rel.replace(INK_SUFFIX, "")
    for c in (cand, re.sub(r"\.pdf\.pdf$", ".pdf", cand, flags=re.I)):
        if c in on_disk and c != rel:
            return c
    return None

def sha1(rel):
    h = hashlib.sha1()
    with open(os.path.join(ROOT, rel), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def read_manifest(root=None):
    path = os.path.join(root or ROOT, MANIFEST)
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("path\t"):
                continue
            parts = line.split("\t")
            parts += [""] * (len(MANIFEST_COLS) - len(parts))
            rows[parts[0]] = dict(zip(MANIFEST_COLS, parts[:len(MANIFEST_COLS)]))
    return rows

def write_manifest(rows, root=None):
    path = os.path.join(root or ROOT, MANIFEST)
    os.makedirs(os.path.dirname(path), exist_ok=True)      # a bare content checkout (share build) has no meta/
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Generated by backend/src/kb/lint/lint.py. Edit the `disposition`, `collection` and `scopes` columns only.\n")
        f.write("# disposition: queued | source | partial | skip | dupe:<path> | ink:<path> | asset:<path> · "
                "collection: comma-separated hub/person slugs · scopes: comma-separated scope-* slugs\n")
        f.write("\t".join(MANIFEST_COLS) + "\n")
        for p in sorted(rows):
            r = rows[p]
            f.write("\t".join(r.get(c, "") for c in MANIFEST_COLS) + "\n")

def reconcile(raw_files, cited, on_disk, raw_to_slug=None, coverage=None, row_status=None,
              missing=frozenset()):
    """Bring the manifest in line with disk. This is the consistency mechanism:
    a new file cannot be invisible, and a changed file cannot stay 'source'.
    `missing`: manifest paths whose bytes are not in this checkout (gitignored PDFs and figures
    in a clone or CI run) — they keep their row and sha1 untouched instead of being dropped.
    `row_status` (raw path → course/series contents-row status) makes a hub table the truth
    for its members: a `—` row is backlog even if the manifest once said skip."""
    rows = read_manifest()
    added = requeued = dropped = 0
    sha1_ms = 0.0
    raw_to_slug = raw_to_slug or {}

    for rel in raw_files:
        parts = rel.split("/")
        kind = parts[1] if len(parts) > 1 else "?"
        t0 = time.perf_counter()
        if rel in missing:
            if rel not in rows:
                continue                                  # nothing on disk, nothing to record
            h = rows[rel]["sha1"]                          # bytes not here: trust the manifest
        else:
            h = sha1(rel)
        sha1_ms += (time.perf_counter() - t0) * 1000
        if rel not in rows:
            rows[rel] = {"path": rel, "sha1": h, "kind": kind,
                         "disposition": "queued", "slug": "", "collection": "", "scopes": ""}
            added += 1
            continue
        r = rows[rel]
        r["kind"] = kind
        if not r["sha1"]:                 # row pre-seeded by catalog (collection set, no hash)
            r["sha1"] = h
        if r["sha1"] != h:
            # bytes changed — e.g. re-annotated on the tablet. Re-open it.
            if r["disposition"] == "source":
                r["disposition"] = "queued"
                requeued += 1
                notices.append(f"re-queued (content changed): {rel}")
            r["sha1"] = h

    on_disk = set(raw_files)
    for rel in list(rows):
        if rel not in on_disk:
            del rows[rel]
            dropped += 1
            notices.append(f"dropped from manifest (gone from disk): {rel}")

    # an ink overlay is bound to its source, never a backlog item of its own
    for rel in raw_files:
        src = ink_source(rel, on_disk)
        if src and rows[rel]["disposition"] == "queued":
            rows[rel]["disposition"] = INK_PREFIX + src

    # a figure downloaded with a web clip belongs to that clip
    for rel in raw_files:
        src = asset_source(rel, on_disk)
        if src and rows[rel]["disposition"] == "queued":
            rows[rel]["disposition"] = ASSET_PREFIX + src

    # a parsed.md sidecar is a transcription cache, never a backlog item
    for rel in raw_files:
        parts = rel.split("/")
        if (os.path.basename(rel) == PARSED_FILENAME and len(parts) == 4
                and parts[1] in SIDECAR_ELIGIBLE_KINDS
                and rows[rel]["disposition"] == "queued"):
            rows[rel]["disposition"] = "sidecar"

    # a course/series contents row is the truth for its members
    for rel, status in (row_status or {}).items():
        if rel not in rows or rows[rel]["disposition"].startswith(COMPANION):
            continue
        if status == SKIP:
            rows[rel]["disposition"] = "skip"
        elif status in DIGESTED:
            rows[rel]["disposition"] = "source"
        elif rows[rel]["disposition"] in ("skip", "source") and rel not in cited:
            rows[rel]["disposition"] = "queued"

    # a page citing a file is ground truth for `source`
    for rel in cited:
        if rel in rows and rows[rel]["disposition"] == "queued":
            rows[rel]["disposition"] = "source"

    # …but a book with only some chapters digested is `partial`, so the rest stays visible
    for rel, cov in (coverage or {}).items():
        if rel not in rows:
            continue
        total = cov.get("total") or 0
        if (not total or cov["covered"] < total) and rows[rel]["disposition"] in ("queued", "source"):
            rows[rel]["disposition"] = "partial"

    for raw_rel, slug in raw_to_slug.items():
        if raw_rel in rows:
            rows[raw_rel]["slug"] = slug

    for rel, r in rows.items():
        d = r["disposition"]
        if d in RETIRED_DISPOSITIONS:
            err(MANIFEST, f"{rel}: disposition {d!r} is retired (schema 1.0) — use {RETIRED_DISPOSITIONS[d]!r}")
        elif d not in DISPOSITIONS and not d.startswith(COMPANION):
            err(MANIFEST, f"{rel}: disposition {d!r} invalid (expected "
                          f"{sorted(DISPOSITIONS)}, dupe:<path>, ink:<path> or asset:<path>)")
        if d.startswith(COMPANION):
            target = d.split(":", 1)[1]
            if target not in rows:
                err(MANIFEST, f"{rel}: target {target!r} is not in the manifest")

    write_manifest(rows)
    if added or requeued or dropped:
        notices.append(f"manifest: +{added} new, {requeued} re-queued, -{dropped} removed")
    return rows, sha1_ms


def check_dupes(rows):
    """Warn when byte-identical files exist under different paths."""
    by_sha = {}
    for path, r in rows.items():
        disp = r.get("disposition", "")
        if disp == "skip" or disp.startswith(COMPANION):
            continue
        h = r.get("sha1", "")
        if not h:
            continue
        by_sha.setdefault(h, []).append(path)
    for paths in by_sha.values():
        if len(paths) < 2:
            continue
        canonical = sorted(paths)[0]
        for p in paths[1:]:
            warn(p, f"byte-identical to {canonical} — set disposition dupe:{canonical}")


def load_wiki_pages():
    """Load wiki pages without schema validation (for coherence-only debug)."""
    pages = {}
    for rel in walk(WIKI_DIR, ".md"):
        if "excalidraw" in rel:
            continue
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        slug = os.path.basename(rel)[:-3]
        fm = parse_frontmatter(text)
        if fm:
            pages[slug] = (rel, fm, text)
    return pages


def _coherence_only_main():
    global errors, warnings, notices
    errors, warnings, notices = [], [], []
    pages = load_wiki_pages()
    raw_files = walk(RAW_DIR)
    cited = {str(fm["raw"]) for _, fm, _ in pages.values()
             if fm.get("raw") and fm["raw"] != "none"}
    raw_to_slug = {}
    for slug, (_rel, fm, _text) in pages.items():
        raw = str(fm.get("raw") or "")
        if raw and raw != "none":
            raw_to_slug[raw] = slug
    rows, _sha1_ms = reconcile(raw_files, cited, set(raw_files), raw_to_slug)
    from kb.core.coherence import run_coherence_lint
    merged, internal, external = run_coherence_lint(
        pages, rows, err_fn=err, warn_fn=warn)
    cosmetic = sum(1 for r in merged.values()
                   if r.get("kind") == "cosmetic" and r.get("status") == "open")
    for w in warnings:
        print(f"warn  {w}")
    for e in errors:
        print(f"ERROR {e}")
    open_n = sum(1 for r in merged.values() if r.get("status") == "open")
    print(f"\ncoherence  {open_n} open ({internal} internal, {external} external, "
          f"{cosmetic} cosmetic)")
    return 1 if errors else 0


# --------------------------------------------------------------------------
def check_wiki():
    pages = {}
    for rel in walk(WIKI_DIR, ".md"):
        parts = rel.split("/")
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        slug = os.path.basename(rel)[:-3]

        if "excalidraw" in parts:          # plugin-authored, exempt
            pages[slug] = (rel, {}, text)
            continue
        if len(parts) > 2:
            err(rel, "wiki/ is flat — the type prefix (paper-, course-, q-, …) replaces folders")

        fm = parse_frontmatter(text)
        if fm is None:
            err(rel, "missing YAML frontmatter")
            continue
        pages[slug] = (rel, fm, text)
        for m in wikiio.check_my_notes(text):       # the user's reserved section: one, and last
            warn(rel, m)

        t = fm.get("type")
        if t in RETIRED_TYPES:
            err(rel, f"type: {t} is retired (schema 1.0) — use type: {RETIRED_TYPES[t]} "
                     f"(layer: {LAYER_OF[RETIRED_TYPES[t]]})")
            continue
        if t not in TYPE_STATUS:
            err(rel, f"type: {t!r} not in {sorted(TYPE_STATUS)}")
            continue
        for key, new in RETIRED_KEYS.items():
            if key in fm:
                err(rel, f"`{key}:` is retired (schema 1.0) — use `{new}:`")
        layer = fm.get("layer")
        if not layer:
            err(rel, f"missing `layer:` — type {t} lives in layer {LAYER_OF[t]}")
        elif layer != LAYER_OF[t]:
            err(rel, f"layer: {layer} disagrees with type {t} (layer {LAYER_OF[t]})")
        elif t not in SOURCE_TYPES and "depth" in fm:
            err(rel, f"`depth:` is for sources only (this page is a {layer} of type {t})")
        allowed = TYPE_STATUS[t]
        if allowed and fm.get("status") not in allowed:
            err(rel, f"status: {fm.get('status')!r} invalid for type {t} — "
                     f"expected one of {sorted(allowed)}")
        if t in NEEDS_RAW:
            raws = raw_paths(fm)
            if not fm.get("raw"):
                err(rel, f"type {t} requires a `raw:` field (a path under raw/, a list, or `none`)")
            elif not raws:
                if not fm.get("url"):
                    err(rel, "raw: none requires a `url:` — a digest needs some provenance")
            for raw in raws:
                if not raw_exists(raw):
                    err(rel, f"raw: {raw} does not exist on disk")
        if t in SOURCE_TYPES:
            ds = fm.get("depth")
            if not ds:
                err(rel, f"type {t} requires `depth:` ({' | '.join(DEPTH)})")
            elif ds in RETIRED_DEPTH:
                err(rel, f"depth: {ds} is retired (schema 1.0) — use depth: {RETIRED_DEPTH[ds]}")
            elif ds not in DEPTH:
                err(rel, f"depth: {ds!r} invalid — expected one of {list(DEPTH)}")
            elif ds == "listed" and fm.get("status") == "digested":
                err(rel, "depth listed means unread — status must be to-read or reading")
            elif ds != "listed" and fm.get("status") != "digested":
                err(rel, f"depth {ds} means read — status must be digested")
        _check_slug(rel, slug, t)
        if t == "topic" and slug[len(TOPIC_PREFIX):] not in TOPIC_SLUGS:
            err(rel, f"topic page must be one of {sorted(TOPIC_PREFIX + s for s in TOPIC_SLUGS)}")
        if t == "ai-chat":
            h1 = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), "")
            if re.match(PLACEHOLDER_TITLE, str(fm.get("title") or "")) or re.match(PLACEHOLDER_TITLE, h1):
                err(rel, "ai-chat needs an informative title, not a clipper placeholder")
            conv = str(fm.get("conversation") or "")
            if not conv or not os.path.isfile(os.path.join(ROOT, CHATS_DIR, conv + ".json")):
                err(rel, f"ai-chat conversation: {conv or '(missing)'} has no tree in {CHATS_DIR}/")
        if t == "distilled-think":
            src = str(fm.get("source") or "")
            if not src.startswith(f"{THINK_DIR}/"):
                err(rel, f"type distilled-think requires source: under {THINK_DIR}/")
            for heading in ("Summary", "Proposed propagation"):
                if f"## {heading}" not in text:
                    err(rel, f"distilled-think page missing ## {heading}")
        if t == "scope":
            if scope_lib.WHY_HEADING not in text or not scope_lib.why_text(text):
                err(rel, "scope page needs a non-empty ## Why (the reason this working set exists)")
            elif not any(l.startswith(("theme-", "q-")) for l in scope_lib.why_links(text)):
                warn(rel, "## Why should link a [[theme-…]] or [[q-…]] page")
            if scope_lib.MEMBERS_HEADING not in text:
                warn(rel, "scope page missing ## Members (lint adds it)")
        if t in SOURCE_TYPES or t in COLLECTION_TYPES:
            _check_paper_areas(rel, fm)
    for slug in sorted(pages):
        rel, fm, _text = pages[slug]
        aliases = fm.get("aliases") or []
        for a in [aliases] if isinstance(aliases, str) else aliases:
            a = a.strip("\"' ")
            if a in pages and a != slug:
                err(rel, f"alias {a!r} is also a page's slug — an old slug must not be reused")
    for theme in sorted(TOPIC_SLUGS):
        if TOPIC_PREFIX + theme not in pages:
            warn(WIKI_DIR, f"missing topic page [[{TOPIC_PREFIX}{theme}]] — every area: needs one")
    return pages


def _check_slug(rel, slug, t):
    """The filename prefix is the type: `paper-` ⇔ type paper; idea/person stay bare."""
    want = SLUG_PREFIX.get(t)
    if want and not slug.startswith(want):
        err(rel, f"type {t} requires a {want} filename prefix")
        return
    owner = next((p for p in RESERVED_PREFIXES if slug.startswith(p)), None)
    if owner and owner != want:
        kind = next(k for k, v in SLUG_PREFIX.items() if v == owner)
        err(rel, f"{owner} prefix requires type: {kind} (this page is {t})")
    if t in BARE_TYPES and owner:
        err(rel, f"type {t} slugs are bare — drop the {owner} prefix")


def _check_paper_areas(rel, fm):
    areas = fm.get("area")
    if not areas:
        return
    if isinstance(areas, str):
        areas = [areas]
    for a in areas:
        if a in DEPRECATED_AREA_SLUGS:
            warn(rel, f"area: {a!r} is deprecated — use a topic slug from {sorted(TOPIC_SLUGS)}")
        elif a not in TOPIC_SLUGS:
            warn(rel, f"area: {a!r} not in topic whitelist {sorted(TOPIC_SLUGS)}")

TABLE_PIPE = re.compile(r"\[\[[^\]\\|]*(?<!\\)\|[^\]]*\]\]")


def check_table_pipes(pages):
    """Inside a markdown table a bare | ends the cell, so [[slug|label]] splits the row and the
    title lands in the next column. Obsidian's table form is [[slug\\|label]]."""
    for _slug, (rel, _fm, text) in pages.items():
        for n, line in enumerate(text.split("\n"), 1):
            if line.lstrip().startswith("|") and TABLE_PIPE.search(line):
                warn(rel, f"line {n}: wikilink inside a table needs an escaped pipe — [[slug\\|label]]")


def check_links(pages):
    known = set(pages) | {os.path.basename(p)[:-3] for p in walk(META_DIR, ".md")}
    known |= {p[:-3] for p in ROOT_MD}
    broken = 0
    for slug, (rel, fm, text) in pages.items():
        for target in LINK.findall(CODE.sub("", text)):
            target = target.strip()
            if "/" in target:
                err(rel, f"path-prefixed wikilink [[{target}]] — wiki/ is flat, use the bare slug")
            elif target not in known:
                warn(rel, f"wikilink [[{target}]] resolves to nothing")
                broken += 1
    return broken

def check_pdf_magic(raw_files):
    """A .pdf that is really an HTML landing page passes the name and size checks and then
    sits in the corpus as `source` forever. Reading 5 bytes per file catches it."""
    for rel in raw_files:
        if not rel.lower().endswith(".pdf"):
            continue
        try:
            with open(os.path.join(ROOT, rel), "rb") as f:
                head = f.read(5)
        except OSError:
            continue
        if head != b"%PDF-":
            err(rel, f"not a PDF (starts with {head!r}) — probably a saved web page; re-fetch a real PDF")


STAMP_CACHE = os.path.join(ROOT, ".cache", "arxiv-stamps.json")
ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?$")


def check_arxiv_stamps(pages):
    """A paper page whose raw PDF is stamped with a different arXiv id than its `url:` cites is a
    wrong download (35 came from Semantic Scholar ids that pointed at strangers' papers), and any
    digest made from it is of the wrong paper. Page 1 of each PDF is read once; the result is
    cached by size+mtime in .cache/, so a lint run costs nothing after the first."""
    if arxiv_meta is None:
        return 0
    try:
        with open(STAMP_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    found, dirty = 0, False
    for slug, (rel, fm, _text) in pages.items():
        if fm.get("type") != "paper":
            continue
        raw, url = fm.get("raw"), str(fm.get("url") or "")
        m = ARXIV_URL.search(url)
        if not m or not isinstance(raw, str) or not raw.lower().endswith(".pdf"):
            continue
        want = m.group(1)
        full = os.path.join(ROOT, raw)
        try:
            st = os.stat(full)
        except OSError:
            continue
        key = f"{st.st_size}:{int(st.st_mtime)}"
        hit = cache.get(raw)
        if hit and hit[0] == key:
            got = hit[1]
        else:
            got = arxiv_meta.stamp(full)
            cache[raw] = [key, got]
            dirty = True
        if got and got != want:
            found += 1
            warn(rel, f"raw PDF is stamped arXiv:{got} but url: cites arXiv:{want} — a wrong "
                      "download, and the digest is of that other paper; "
                      "`python3 -m kb.ingest refetch-raw --apply` replaces it")
    if dirty:
        try:
            os.makedirs(os.path.dirname(STAMP_CACHE), exist_ok=True)
            with open(STAMP_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return found


def check_raw():
    raw_files = walk(RAW_DIR)
    for rel in raw_files:
        parts = rel.split("/")
        sub = parts[1] if len(parts) > 2 else None
        if sub is None or sub not in RAW_SUBDIRS:
            err(rel, f"nothing may sit loose in raw/ — allowed: {sorted(RAW_SUBDIRS)}")
            continue
        if sub == RAW_INBOX:
            continue                                   # free shape, it drains
        depth = len(parts) - 3   # dirs between raw/<kind>/ and the filename
        if sub in RAW_NESTED and depth != 1:
            err(rel, f"raw/{sub}/ takes exactly one nested level")
        if sub not in RAW_NESTED and depth != 0:
            err(rel, f"raw/{sub}/ is flat — membership goes in corpus.tsv `collection`, not folders")
        base = os.path.basename(rel)
        if (sub not in RAW_NESTED and INK_SUFFIX not in base
                and not re.match(RAW_NAME, base)):
            err(rel, "raw filename must be lowercase ascii kebab, e.g. "
                     "`<collection>-<topic>.pdf` (papers: `<year>-<title>.pdf`)")
        if rel.endswith(".md"):
            fm = parse_frontmatter(open(os.path.join(ROOT, rel), encoding="utf-8").read())
            if fm and fm.get("type") in TYPE_STATUS:
                err(rel, "agent-authored frontmatter inside raw/ — this belongs in wiki/")
            if os.path.basename(rel) == PARSED_FILENAME:
                derived_from = fm.get("derived-from") if fm else None
                if not derived_from:
                    err(rel, "parsed.md sidecar missing `derived-from:` frontmatter")
                elif not raw_exists(derived_from.rstrip("/")):
                    err(rel, f"parsed.md sidecar's derived-from: {derived_from} does not exist on disk")
    return raw_files


def _git_ignored(names):
    """Subset of `names` (vault-root entries) that git ignores; empty when not a git checkout."""
    if not names:
        return set()
    try:
        r = subprocess.run(["git", "check-ignore", "--", *names], cwd=ROOT, capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {l.strip().rstrip("/") for l in r.stdout.splitlines()} if r.returncode == 0 else set()


def check_wiki_strays():
    """Warn on anything in wiki/ that is not a flat `.md` page (subfolders, other files, excalidraw)."""
    base = os.path.join(ROOT, WIKI_DIR)
    if not os.path.isdir(base):
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for d in dirnames:
            rel = os.path.relpath(os.path.join(dirpath, d), ROOT).replace(os.sep, "/")
            warn(rel, "subfolder in wiki/ — wiki is flat; move or delete (plugin leftovers do not belong here)")
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if fn.endswith(".excalidraw.md"):
                warn(rel, "excalidraw drawing in wiki/ — not a wiki page; move it out or delete")
            elif not fn.endswith(".md"):
                warn(rel, "non-markdown file in wiki/ — wiki holds only .md pages")


def check_root():
    """Warn on unexpected files/folders at vault root (dot-tooling, ROOT_LINT_IGNORE and git-ignored exempt)."""
    ignored = _git_ignored([n for n in os.listdir(ROOT) if not n.startswith(".")
                            and n not in ROOT_LINT_IGNORE and n not in ROOT_DIRS and n not in ROOT_FILES])
    for name in sorted(os.listdir(ROOT)):
        if name.startswith("."):
            continue
        if name in ROOT_LINT_IGNORE or name in ignored:
            continue
        full = os.path.join(ROOT, name)
        if os.path.isdir(full):
            if name in ROOT_DIRS:
                continue
            warn("vault-root", f"{name}/ — unexpected folder at vault root; "
                 "move to raw/inbox/ or _quarantine/")
            continue
        if name in ROOT_FILES:
            continue
        warn("vault-root", f"{name} — unexpected file at vault root; "
             "delete or move to raw/inbox/")


def check_paper_name(rel):
    """A paper or book PDF uses `<year>-<kebab-title>.pdf`. Sortable and self-describing."""
    name = os.path.basename(rel)
    if not re.match(PAPER_NAME, name):
        err(rel, "paper filename must be `<year>-<kebab-title>.pdf` "
                 "(lowercase, hyphens, no spaces) — e.g. 2023-toolformer.pdf")
        return
    year = int(name[:4])
    if not (PAPER_YEAR_MIN <= year <= PAPER_YEAR_MAX):
        err(rel, f"implausible publication year {year}")

def check_paper_year_matches(pages):
    """A paper/book PDF in printed-docs/ is named `<year>-<title>.pdf`, and that year must agree
    with the digest's `year:` field."""
    checked = set()
    for slug, (rel, fm, _) in pages.items():
        if fm.get("type") not in YEARED:
            continue
        year = fm.get("year")
        for raw in raw_paths(fm):
            if raw.startswith(f"{RAW_DIR}/{RAW_PRINTED}/") and raw.endswith(".pdf") \
                    and fm.get("type") != "part" and raw not in checked:
                checked.add(raw)
                check_paper_name(raw)
            fname = os.path.basename(raw)
            if year and re.match(PAPER_NAME, fname) and fname[:4] != str(year):
                err(rel, f"filename year {fname[:4]} disagrees with frontmatter year: {year}")

def check_ink(raw_files):
    """An ink overlay must keep its source document; a blank overlay is noise."""
    byname = {r: os.path.getsize(os.path.join(ROOT, r)) for r in raw_files}
    for rel in raw_files:
        base = os.path.basename(rel)
        if INK_SUFFIX not in base:
            continue
        if byname[rel] <= BLANK_PDF_BYTES:
            warn(rel, "ink overlay is a blank page — no annotation, safe to drop")
        if not ink_source(rel, byname):
            notices.append(f"ink overlay with no source document in the vault: {rel}")


def _effective_digestion(fm, text):
    """Resolve digestion tier for strict checks."""
    ds = fm.get("depth")
    if ds in DEPTH:
        return ds
    if fm.get("status") != "digested":
        return "listed"
    if "## Key equations" in text:
        block = text.split("## Key equations", 1)[1].split("\n##", 1)[0].strip()
        if block and block != "—" and len(block) > 8:
            return "full"
    return "listed"


def check_ingest_strict(pages, only_slugs=None):
    """Stricter checks for finalize — Key equations only for full/deep digestion."""
    only_slugs = set(only_slugs or [])
    theme_papers = set()
    for slug, (rel, fm, text) in pages.items():
        if not slug.startswith(TOPIC_PREFIX):
            continue
        if "## Papers" in text:
            for target in LINK.findall(text.split("## Papers", 1)[1]):
                theme_papers.add(target.strip())

    for slug, (rel, fm, text) in pages.items():
        if only_slugs and slug not in only_slugs:
            continue
        if fm.get("type") not in SOURCE_TYPES:
            continue
        tier = _effective_digestion(fm, text)
        if tier not in ("full", "deep"):
            continue
        if fm.get("status") != "digested":
            err(rel, f"depth {tier} requires status: digested")
            continue
        if "## Key equations" not in text:
            err(rel, "full/deep digest missing ## Key equations section")
            continue
        block = text.split("## Key equations", 1)[1].split("\n##", 1)[0].strip()
        if not block or block == "—" or len(block) < 8:
            err(rel, "full/deep digest has empty Key equations (use LaTeX, not —)")
        if slug not in theme_papers and str(fm.get("book") or "") not in theme_papers:
            warn(rel, f"[[{slug}]] not listed in any {TOPIC_PREFIX}*.md ## Papers section")


def _ingest_strict_slugs():
    for arg in sys.argv:
        if arg.startswith("--ingest-strict="):
            return [s.strip() for s in arg.split("=", 1)[1].split(",") if s.strip()]
    return None


def _page_range(fm):
    """Parse `section_pages:` (list or 'A-B' string) into an inclusive (start, end)."""
    v = fm.get("section_pages")
    if not v:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return int(v[0]), int(v[1])
        except (TypeError, ValueError):
            return None
    m = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", str(v))
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_books(pages):
    """Page-range hubs (book, notebook): an Overview, a valid page partition, and part pages
    that agree with their row both ways. Returns {hub slug: (rel, fm, rows)}."""
    hubs = {}
    for slug, (rel, fm, text) in pages.items():
        t = fm.get("type")
        if t not in PARTITION_COLLECTIONS:
            continue
        try:
            total = int(str(fm.get("book_pages") or "").strip())
        except ValueError:
            err(rel, f"type {t} requires an integer `book_pages:`")
            total = 0
        if not overview_ok(text):
            warn(rel, f"{t} needs an {OVERVIEW_HEADING} paragraph (≥{OVERVIEW_MIN_CHARS} chars): "
                      "what it is, how it is organised, why it matters here")
        rows = []
        if PARTITION_HEADING not in text:
            err(rel, f"type {t} requires a {PARTITION_HEADING} table — "
                     "`python3 -m kb.ingest toc <raw>` proposes one")
        else:
            rows = parse_partition(text)
            errs, warns = validate(rows, total)
            for m in errs:
                err(rel, m)
            for m in warns:
                warn(rel, m)
            line = coverage_line(rows).split(" · ")[0]
            if rows and line not in text:
                warn(rel, f"stale coverage line — expected `{line}`")
            derived = book_status(rows)
            if rows and fm.get("status") != derived:
                warn(rel, f"status: {fm.get('status')} but the partition says {derived}")
        for r in rows:
            target = pages.get(r["slug"])
            if target and target[1].get("type") != "part":
                err(rel, f"partition row p.{r['start']}–{r['end']} links [[{r['slug']}]], "
                         f"a {target[1].get('type')} page — rows link type: part pages")
        hubs[slug] = (rel, fm, rows)

    for slug, (rel, fm, _text) in pages.items():
        if fm.get("type") != "part":
            continue
        book = str(fm.get("book") or "")
        if book not in hubs:
            err(rel, f"type part requires `book:` naming a book or notebook page (got {book!r})")
            continue
        _brel, bfm, rows = hubs[book]
        if str(bfm.get("raw") or "") != str(fm.get("raw") or ""):
            err(rel, f"raw: differs from its book [[{book}]]")
        stem = f"{SLUG_PREFIX['part']}{strip_prefix(book)}-"
        if not slug.startswith(stem):
            warn(rel, f"part slug should start with `{stem}` (its hub's slug without the prefix)")
        rng = _page_range(fm)
        if not rng:
            err(rel, "type part requires `section_pages: A-B`")
            continue
        row = find_row(rows, *rng)
        if not row:
            err(rel, f"section_pages {rng[0]}-{rng[1]} matches no row of [[{book}]] "
                     f"{PARTITION_HEADING}")
            continue
        if row["slug"] != slug:
            err(rel, f"[[{book}]] row p.{rng[0]}–{rng[1]} links [[{row['slug'] or '—'}]], "
                     "not this page")
        if row["status"] != fm.get("depth"):
            err(rel, f"depth {fm.get('depth')!r} but [[{book}]] row says "
                     f"{row['status']!r}")
    return hubs


def check_contents(pages):
    """Row hubs (course, series): an Overview, a readable Contents table, linked pages that
    exist and cite the row's files. Returns {hub slug: (rel, fm, rows)}; membership against
    corpus.tsv is checked later by check_collections, once the manifest is reconciled."""
    tables = {}
    for slug, (rel, fm, text) in pages.items():
        t = fm.get("type")
        if t not in CONTENTS_COLLECTIONS:
            continue
        if not overview_ok(text):
            warn(rel, f"{t} needs an {OVERVIEW_HEADING} paragraph (≥{OVERVIEW_MIN_CHARS} chars)")
        if hubs.CONTENTS_HEADING not in text:
            err(rel, f"type {t} requires a {hubs.CONTENTS_HEADING} table of its raw files")
            tables[slug] = (rel, fm, [])
            continue
        rows = hubs.parse_contents(text)
        line = hubs.coverage_line(rows)
        if rows and line not in text:
            warn(rel, f"stale coverage line — expected `{line}`")
        derived = hubs.hub_status(rows)
        if rows and fm.get("status") != derived:
            warn(rel, f"status: {fm.get('status')} but the contents table says {derived}")
        for r in rows:
            if not r["slug"]:
                continue
            target = pages.get(r["slug"])
            if not target:
                continue                                  # broken link: check_links reports it
            ttype = target[1].get("type")
            if r["status"] == hubs.PARTIAL and ttype not in PARTITION_COLLECTIONS:
                err(rel, f"row {r['title']!r} is partial but [[{r['slug']}]] is a {ttype}, "
                         "not a book/notebook hub")
            elif ttype in SOURCE_TYPES:
                cited = set(raw_paths(target[1]))
                for p in r["raws"]:
                    if p not in cited:
                        err(rel, f"row {r['title']!r} links [[{r['slug']}]] but that page's raw: "
                                 f"does not include `{p}`")
        tables[slug] = (rel, fm, rows)
    return tables


def check_persons(pages):
    """Person pages: handles generate sections, no status (backend/src/kb/core/persons.py). Returns the
    health counters: unverified pages, `unknown` handles, lineage slugs without a page."""
    fms = {slug: fm for slug, (_rel, fm, _text) in pages.items()}
    people = {slug: (fm, persons.parse_frontmatter(text)[1])
              for slug, (_rel, fm, text) in pages.items() if fm.get("type") == "person"}
    errs, warns, health = persons.check_all(people, fms)
    for slug, m in errs:
        err(pages[slug][0], m)
    for slug, m in warns:
        warn(pages[slug][0], m)
    return health


def check_scopes(pages, rows, before, ci):
    """corpus.tsv `scopes` ↔ scope- pages, and the generated `## Members` section of each page.
    `before`: the manifest as it was on entry (rows reconcile dropped had their file deleted).
    Returns the health counters: scope pages and queued rows across all scopes."""
    names = scope_lib.all_scopes(rows)
    for slug in names:
        page = pages.get(slug)
        if page is None or page[1].get("type") != "scope":
            err(MANIFEST, f"scopes cell names {slug!r}, which is not a scope page")
    for path, r in sorted(before.items()):
        if path not in rows:
            for slug in scope_lib.scopes_of_row(r):
                warn(MANIFEST, f"{slug} lost {path} (gone from disk)")
    scope_pages = sorted(s for s, (_r, fm, _t) in pages.items() if fm.get("type") == "scope")
    uncovered = 0
    index = scope_lib.build_index(pages) if scope_pages else None
    for slug in scope_pages:
        rel, fm, text = pages[slug]
        paths = scope_lib.rows_of(slug, rows)
        if not paths:
            warn(rel, "scope has no files — add rows in the dashboard or the corpus `scopes` column")
        proj = scope_lib.projection(paths, pages, rows, index)
        uncovered += len(proj["uncovered"])
        if ci:
            continue                    # partial checkout: raw rows are frozen, leave the page alone
        new = scope_lib.replace_members(text, scope_lib.render_members(slug, proj, pages))
        if new != text:
            new = wikiio.write_page(os.path.join(ROOT, rel), new)
            pages[slug] = (rel, fm, new)
            notices.append(f"regenerated ## Members of {slug}")
    return {"scopes": len(scope_pages), "uncovered": uncovered}


def check_collections(pages, tables, rows):
    """corpus.tsv `collection` ↔ hub tables. A collection names a hub or a person page
    (a researcher's bibliography); a course/series table lists exactly its members."""
    members = {}
    for path, r in rows.items():
        disp = r.get("disposition", "")
        for c in collections_of(r):
            page = pages.get(c)
            ctype = page[1].get("type") if page else None
            if ctype is None:
                err(MANIFEST, f"{path}: collection {c!r} is not a wiki page")
            elif ctype not in COLLECTION_TYPES and ctype != "person":
                err(MANIFEST, f"{path}: collection {c!r} is a {ctype} page — "
                              f"expected one of {sorted(COLLECTION_TYPES | {'person'})}")
            elif ctype in CONTENTS_COLLECTIONS and not disp.startswith(COMPANION):
                members.setdefault(c, set()).add(path)
    for slug, (rel, _fm, trows) in tables.items():
        errs, warns = hubs.validate(trows, members.get(slug, set()), slug)
        for m in errs:
            err(rel, m)
        for m in warns:
            warn(rel, m)


def book_coverage(pages, hubs=None):
    """raw path -> {'covered', 'total', 'sections': [(slug, start, end)]} for books.
    A book hub's partition is the truth (skip rows count toward neither number). Raw files
    with no hub fall back to `section_pages:` / `book_pages:` on their pages. No PDF is
    opened: this runs on every lint."""
    out = {}
    for _slug, (_rel, fm, rows) in (hubs or {}).items():
        raw = str(fm.get("raw") or "")
        if not raw or raw == "none" or not rows:
            continue
        covered, total = coverage(rows)
        done = [r for r in rows if r["start"] is not None and r["status"] in DIGESTED]
        out[raw] = {"covered": covered, "total": total,
                    "sections": sorted(((r["slug"], r["start"], r["end"]) for r in done),
                                       key=lambda x: x[1])}
    sections, totals = {}, {}
    for slug, (_rel, fm, _text) in pages.items():
        raw = str(fm.get("raw") or "")
        if not raw or raw == "none" or raw in out:
            continue
        try:
            n = int(str(fm.get("book_pages") or "").strip())
            totals[raw] = max(totals.get(raw, 0), n)
        except ValueError:
            pass
        rng = _page_range(fm)
        if rng:
            sections.setdefault(raw, []).append((slug, rng[0], rng[1]))
    for raw, secs in sections.items():
        covered = len({p for _s, a, b in secs for p in range(a, b + 1)})
        out[raw] = {"covered": covered, "total": totals.get(raw, 0),
                    "sections": sorted(secs, key=lambda x: x[1])}
    return out


def check_book_coverage(pages, rows, coverage=None):
    """A long book with one chapter digested must never read as fully digested."""
    coverage = coverage if coverage is not None else book_coverage(pages)
    partial = []
    for raw, cov in sorted(coverage.items()):
        total = cov["total"]
        if total and cov["covered"] >= total:
            continue
        pct = f"{100 * cov['covered'] // total}%" if total else "?"
        chapters = ", ".join(f"p.{a}-{b}" for _s, a, b in cov["sections"])
        warn(raw, f"book partially digested — {cov['covered']}"
                  + (f"/{total}" if total else "") + f" pages ({pct}): {chapters or 'none'}. "
                  "Run `python3 -m kb.ingest toc <raw>` for what is left.")
        partial.append({"raw": raw, **cov})
    return partial


def collect_snapshot(quiet=False):
    """Run all vault checks and return a health snapshot dict."""
    global errors, warnings, notices
    errors, warnings, notices = [], [], []
    t0 = time.perf_counter()
    manifest_rows = read_manifest()
    ci = ci_mode() or partial_checkout(manifest_rows)
    CI_RAW.clear()
    if ci:
        CI_RAW.update(manifest_rows)

    raw_files = check_raw()
    if not ci:
        check_pdf_magic(raw_files)
    check_root()
    check_wiki_strays()

    t_wiki = time.perf_counter()
    pages = check_wiki()
    wiki_ms = (time.perf_counter() - t_wiki) * 1000
    if not ci:
        check_arxiv_stamps(pages)

    t_links = time.perf_counter()
    broken = check_links(pages)
    check_table_pipes(pages)
    links_ms = (time.perf_counter() - t_links) * 1000

    if not ci:
        check_ink(raw_files)
    check_paper_year_matches(pages)
    book_hubs = check_books(pages)
    tables = check_contents(pages)

    if "--ingest-strict" in sys.argv or any(a.startswith("--ingest-strict=") for a in sys.argv):
        check_ingest_strict(pages, _ingest_strict_slugs())

    cited = {p for _, fm, _ in pages.values() for p in raw_paths(fm)}
    raw_to_slug = {}
    for slug, (_rel, fm, _text) in pages.items():
        for raw in raw_paths(fm):
            raw_to_slug[raw] = slug
    for slug, (_rel, fm, _rows) in book_hubs.items():   # a book's corpus row names its hub
        for raw in raw_paths(fm):
            raw_to_slug[raw] = slug
    row_status = {}
    for _slug, (_rel, _fm, trows) in tables.items():
        row_status.update(hubs.row_status_by_path(trows))
    cover = book_coverage(pages, book_hubs)
    if ci:
        # partial checkout: the gitignored raw bytes are absent, so their manifest rows stand in —
        # kept as they are — while everything on disk (clips, new files) reconciles as usual
        on_disk = set(raw_files)
        missing = {p for p in CI_RAW if p not in on_disk and p.startswith(f"{RAW_DIR}/")}
        rows, sha1_ms = reconcile(sorted(on_disk | missing), cited, on_disk | missing, raw_to_slug,
                                  cover, row_status, missing=missing)
    else:
        rows, sha1_ms = reconcile(raw_files, cited, set(raw_files), raw_to_slug, cover, row_status)
    check_dupes(rows)
    check_collections(pages, tables, rows)
    partial_books = check_book_coverage(pages, rows, cover)
    person_health = check_persons(pages)
    scope_health = check_scopes(pages, rows, manifest_rows, ci)

    from kb.core.coherence import run_coherence_lint
    _coherence, _, _ = run_coherence_lint(
        pages, rows, err_fn=err, warn_fn=warn, fresh=_ingest_strict_slugs())

    inbox = [r for r in raw_files if r.startswith(f"{RAW_DIR}/{RAW_INBOX}/")]
    if len(inbox) >= INBOX_ERROR:
        err("raw/inbox", f"{len(inbox)} files — triage them, the inbox must drain")
    now = time.time()
    for rel in inbox:
        age = (now - os.path.getmtime(os.path.join(ROOT, rel))) / 86400
        if age > INBOX_STALE_DAYS:
            warn(rel, f"sat in the inbox for {age:.0f} days — catalog it or delete it")

    if ci and not quiet:
        print(f"partial checkout: {len(missing)} raw binaries not here (gitignored) — their manifest rows "
              "are kept as is; pdf/ink checks skipped")
    write_index(pages, quiet=quiet)

    queued_count = sum(1 for r in rows.values() if r.get("disposition") == "queued")
    h_status, h_ok = hooks_health()
    lint_ms = (time.perf_counter() - t0) * 1000

    from kb.core.health import build_snapshot
    snapshot = build_snapshot(
        pages=pages,
        raw_files=raw_files,
        rows=rows,
        broken=broken,
        errors=errors,
        warnings=warnings,
        inbox_count=len(inbox),
        queued_count=queued_count,
        hooks_status=h_status,
        hooks_ok=h_ok,
        coherence_merged=_coherence,
        timings={"root": ROOT, "lint_ms": lint_ms, "sha1_ms": sha1_ms,
                 "wiki_ms": wiki_ms, "links_ms": links_ms},
    )
    snapshot["_rows"] = rows
    snapshot["partial_books"] = partial_books
    snapshot.setdefault("values", {})["partial_books"] = len(partial_books)
    snapshot["values"]["scopes"] = scope_health["scopes"]
    snapshot["values"]["scope_uncovered"] = scope_health["uncovered"]
    snapshot["values"]["persons_unverified"] = person_health["unverified"]
    snapshot["values"]["person_unknowns"] = person_health["unknowns"]
    snapshot["values"]["lineage_stubs"] = len(person_health["stubs"])
    snapshot["lineage_stubs"] = person_health["stubs"]
    # listed-only stubs count as `source` in corpus.tsv, so `queued` hides to-read papers
    snapshot["values"]["to_read_stubs"] = sum(
        1 for _rel, fm, _t in pages.values()
        if fm.get("depth") == "listed"
        and fm.get("type") in ("paper", "part", "lecture", "article", "video", "conversation",
                               "ai-chat", "blog-post"))
    return snapshot


def main():
    if "--dashboard" in sys.argv:
        from kb.dashboard.serve import main as dash_main
        argv = [a for a in sys.argv[1:] if a != "--dashboard"]
        return dash_main(argv or None)

    if "--coherence-only" in sys.argv:
        return _coherence_only_main()

    quiet = "--health" in sys.argv
    snapshot = collect_snapshot(quiet=quiet)
    rows = snapshot.pop("_rows", {})
    wiki_count = snapshot["wiki_pages"]
    raw_count = snapshot["raw_files"]

    counts = {d: 0 for d in DISPOSITIONS}
    for r in rows.values():
        d = r["disposition"]
        if d.startswith(COMPANION):
            continue
        counts[d] = counts.get(d, 0) + 1

    if "--pending" in sys.argv:
        for p in sorted(rows):
            if rows[p]["disposition"] == "queued":
                print(f"  queued  {p}")

    if "--health" in sys.argv:
        from kb.core.health import print_health_terminal
        print_health_terminal(snapshot)
        return 1 if snapshot["values"]["errors"] else 0

    for n in notices:
        print(f"note  {n}")
    for w in warnings:
        print(f"warn  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{wiki_count} pages · {raw_count} raw files · "
          f"{counts.get('queued', 0)} queued · {len(errors)} errors · {len(warnings)} warnings")
    return 1 if errors else 0


SECTIONS = [("topic", "Topics"), ("idea", "Ideas"), ("question", "Open questions"),
            ("course", "Courses"), ("series", "Series"), ("book", "Books"),
            ("notebook", "Notebooks"), ("paper", "Papers"), ("part", "Book parts"),
            ("lecture", "Lectures"), ("article", "Articles"), ("blog-post", "Blog posts"),
            ("video", "Videos"), ("ai-chat", "AI chats"), ("conversation", "Conversations"),
            ("person", "People"),
            ("scope", "Scopes"),
            ("distilled-think", "Distilled thinking (review)")]

def first_line(text):
    body = text.split("\n---", 1)[-1]
    seen_h1 = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            seen_h1 = True
            continue
        if seen_h1 and s and not s.startswith(("#", ">", "-", "|", "*")):
            return s.rstrip(".")
    return ""

def write_index(pages, quiet=False):
    out = ["---", "type: meta", "---", "", "# Wiki index", "",
           "> Generated by `backend/src/kb/lint/lint.py`. Do not hand-edit.", "",
           "Read this first on any query.", "", "## Meta", "",
           "| Page | Summary |", "|------|---------|",
           "| [[thesis]] | Thesis topic, instructor, institution |",
           "| [[log]] | Activity timeline |",
           "| [[AGENTS]] | Schema and workflows |", ""]
    for t, title in SECTIONS:
        rows = []
        for slug in sorted(pages):
            rel, fm, text = pages[slug]
            if fm.get("type") != t:
                continue
            s = first_line(text).replace("|", "\\|")
            if len(s) > 110:
                s = s[:107] + "..."
            rows.append(f"| [[{slug}]] | {fm.get('status','')} | {s} |")
        if rows:
            out += [f"## {title}", "", "| Page | Status | Summary |",
                    "|------|--------|---------|"] + rows + [""]
    open(os.path.join(ROOT, "index.md"), "w", encoding="utf-8").write("\n".join(out))
    if not quiet:
        print("wrote index.md")


if __name__ == "__main__":
    sys.exit(main())

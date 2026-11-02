"""Generic book handling: detect long PDFs, read their table of contents, pick a section.

A book is any PDF long enough that a 25-page skim from the front is meaningless. Digesting one
is always scoped: the CLI prints the TOC and refuses to guess which part you meant.

Section ranges are 1-based inclusive page numbers as printed by `toc`, matching what PyMuPDF's
outline reports (physical PDF pages, which for a typeset book run ahead of the printed folios).
"""
import glob
import hashlib
import os
import re
import sys

from .paths import ROOT
from kb_distillery.paths import meta_file
from kb_distillery.vault import frontmatter, wikiio
from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.vault.schema import PARTITION_COLLECTIONS, RAW_HANDWRITTEN, SLUG_PREFIX, is_page_file, make_slug, strip_prefix
from kb_distillery.vault.books import (DIGESTED, PART_MAX_PAGES, SKIP, book_status, carve, coverage_line, find_row,
                   parse_partition, propose, replace_partition)

BOOK_MIN_PAGES = 60         # below this a PDF is a paper: digest it whole
BOOK_MIN_SECTIONS = 3        # a TOC needs at least this many entries to be worth offering
TOC_SCAN_PAGES = 25          # how far into a PDF to look for a printed contents page
CHAPTER_RE = re.compile(r"^\s*(?:chapter|ch\.?|part|lecture|appendix)\s+([0-9IVXA-Z]+)\b", re.I)
# "1.2. Title .......... 23"  /  "Chapter 3  Title   69"
TOC_LINE_RE = re.compile(
    r"^\s*(?P<num>(?:chapter|part|appendix)?\s*[0-9]+(?:\.[0-9]+)*\.?)\s+"
    r"(?P<title>.+?)\s*[.\s]{2,}\s*(?P<page>[0-9]+)\s*$", re.I)


def verify_for_scope(raw_rel):
    """Normalise a repo-relative raw path for TOC/scope use (read-only, no corpus checks)."""
    s = str(raw_rel).replace(os.sep, "/")
    if os.path.isabs(s):
        root = os.path.realpath(ROOT).replace(os.sep, "/").rstrip("/") + "/"
        for cand in (s, os.path.realpath(s).replace(os.sep, "/")):
            if cand.startswith(root):
                return cand[len(root):]
        return s                       # outside the KB: keep it absolute (os.path.join then keeps it too)
    while s.startswith("./"):
        s = s[2:]
    return s


def _fitz():
    try:
        import fitz  # pymupdf
        return fitz
    except ImportError:
        print("pymupdf not installed — run: pixi install", file=sys.stderr)
        return None


def page_count(raw_path):
    fitz = _fitz()
    if not fitz or not os.path.isfile(raw_path) or not raw_path.lower().endswith(".pdf"):
        return 0
    doc = fitz.open(raw_path)
    n = doc.page_count
    doc.close()
    return n


def _slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:60]


def _number(title):
    """Leading section number, e.g. '1' for 'Chapter 1. …' or '2.3' for '2.3. Total influence'."""
    m = CHAPTER_RE.match(title)
    if m:
        return m.group(1)
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)*)\.?\s", title)
    return m.group(1) if m else ""


def _finish(entries, total):
    """Fill in each entry's end page from the next entry at the same or a higher level."""
    for i, e in enumerate(entries):
        end = total
        for nxt in entries[i + 1:]:
            if nxt["level"] <= e["level"]:
                end = max(e["start"], nxt["start"] - 1)
                break
        e["end"] = end
        e["pages"] = e["end"] - e["start"] + 1
        e["number"] = _number(e["title"])
        e["slug"] = _slug(e["title"])
    return entries


def _from_outline(doc):
    raw = doc.get_toc() or []
    entries = [{"level": lvl, "title": " ".join(str(t).split()), "start": max(1, int(p))}
               for lvl, t, p in raw if p and int(p) > 0]
    return _finish(entries, doc.page_count)


def _from_text(doc):
    """Fallback for PDFs with no embedded outline: parse a printed contents page."""
    entries = []
    for i in range(min(TOC_SCAN_PAGES, doc.page_count)):
        for line in (doc.load_page(i).get_text() or "").splitlines():
            m = TOC_LINE_RE.match(line)
            if not m:
                continue
            num = m.group("num").strip().rstrip(".")
            title = m.group("title").strip(" .")
            page = int(m.group("page"))
            if not title or page > doc.page_count or len(title) < 3:
                continue
            entries.append({"level": 1 + num.count("."), "title": f"{num}. {title}", "start": page})
    # A printed TOC cites folio numbers; assume they line up with physical pages.
    seen, uniq = set(), []
    for e in sorted(entries, key=lambda x: x["start"]):
        if e["title"] in seen:
            continue
        seen.add(e["title"])
        uniq.append(e)
    return _finish(uniq, doc.page_count)


def read_toc(raw_path):
    """Return (entries, page_count, source) where source is 'outline', 'text' or 'none'."""
    fitz = _fitz()
    if not fitz or not os.path.isfile(raw_path) or not raw_path.lower().endswith(".pdf"):
        return [], 0, "none"
    doc = fitz.open(raw_path)
    total = doc.page_count
    entries = _from_outline(doc)
    source = "outline"
    if len(entries) < BOOK_MIN_SECTIONS:
        entries = _from_text(doc)
        source = "text" if entries else "none"
    doc.close()
    return entries, total, source


_PAPER_NOTICED = set()


def looks_like_paper(raw_path):
    """A long PDF that is really a paper with appendices: no chapter-like top-level outline
    entries and an abstract on the first page."""
    fitz = _fitz()
    if not fitz or not os.path.isfile(raw_path):
        return False
    try:
        doc = fitz.open(raw_path)
        try:
            for lvl, title, _p in (doc.get_toc() or []):
                if lvl == 1 and CHAPTER_RE.match(str(title)):
                    return False
            first = (doc.load_page(0).get_text() or "") if doc.page_count else ""
        finally:
            doc.close()
    except Exception:
        return False
    return bool(re.search(r"\babstract\b", first[:3000], re.I))


def is_book(raw_path):
    if page_count(raw_path) < BOOK_MIN_PAGES:
        return False
    if looks_like_paper(raw_path):
        if raw_path not in _PAPER_NOTICED:
            _PAPER_NOTICED.add(raw_path)
            print(f"note: {os.path.basename(raw_path)} has {page_count(raw_path)} pages (book "
                  f"threshold {BOOK_MIN_PAGES}) but no chapters and an abstract on page 1 — "
                  f"treating it as a paper with appendices.", file=sys.stderr)
        return False
    return True


def top_level(entries):
    """Chapter-level entries only — what the CLI offers by default."""
    if not entries:
        return []
    lvl = min(e["level"] for e in entries)
    return [e for e in entries if e["level"] == lvl]


def find_section(entries, spec):
    """Resolve a --section spec: chapter number ('1', '2.3'), 1-based index ('#4'), or text."""
    spec = (spec or "").strip()
    if not spec or not entries:
        return None
    if spec.startswith("#"):
        try:
            return entries[int(spec[1:]) - 1]
        except (ValueError, IndexError):
            return None
    low = spec.lower()
    # a chapter number: the shallowest outline entry carrying it ("1" is Chapter 1 even when a deeper
    # entry also numbers itself 1), earliest first
    numbered = [e for e in entries if e["number"] and e["number"].lower() == low]
    if numbered:
        return min(numbered, key=lambda e: (e["level"], e["start"]))
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", low):
        # a bare number with no such chapter: never let "4" match "Chapter 14" or "2004" by substring
        return None
    hits = [e for e in entries if low in e["title"].lower() or low in e["slug"]]
    return min(hits, key=lambda e: (e["level"], e["start"])) if hits else None


def parse_pages(spec, total=None):
    """'19-42' or '19' → (19, 42). Returns None when unparseable."""
    if not spec:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(?:[-:]\s*(\d+)\s*)?", str(spec))
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    if end < start:
        start, end = end, start
    if total:
        start, end = max(1, min(start, total)), max(1, min(end, total))
    return start, end


def digested_ranges(raw_rel):
    """[(slug, start, end)] already digested from this raw file, read from wiki frontmatter."""
    import glob
    from kb_distillery.paths import vault_root
    root = vault_root()
    out = []
    for path in _wiki_pages(os.path.join(root, "wiki")):
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(1200)
        except OSError:
            continue
        if not head.startswith("---") or f"raw: {raw_rel}" not in head:
            continue
        m = re.search(r"^section_pages:\s*(\d+)\s*[-:]\s*(\d+)\s*$", head, re.M)
        if m:
            out.append((os.path.basename(path)[:-3], int(m.group(1)), int(m.group(2))))
    return sorted(out, key=lambda x: x[1])


def _overlap(a, b, ranges):
    """Slug of the first digested range covering most of [a, b], or None."""
    for slug, s0, e0 in ranges:
        if min(b, e0) - max(a, s0) + 1 >= 0.6 * (b - a + 1):
            return slug
    return None


def _example(shown):
    """Pick a chapter-ish entry for the usage hint, not the preface."""
    for e in shown:
        if e["number"]:
            return f"{e['start']}-{e['end']}"
    return f"{shown[0]['start']}-{shown[0]['end']}"


def format_toc(entries, total, source, raw_rel, depth=1):
    """Human-readable contents listing for the terminal."""
    tops = top_level(entries)
    shown = tops if depth <= 1 else [e for e in entries if e["level"] <= min(e2["level"] for e2 in entries) + depth - 1]
    done = digested_ranges(raw_rel)
    covered = len({p for _s, a, b in done for p in range(a, b + 1)})
    head = f"{raw_rel} — {total} pages, {len(tops)} sections (TOC from {source})"
    if done:
        head += f"\n{covered}/{total} pages digested ({100 * covered // total if total else 0}%) — the rest is backlog."
    lines = [head, ""]
    width = max((len(e["title"]) for e in shown), default=10)
    width = min(width, 62)
    for i, e in enumerate(shown, 1):
        indent = "  " * (e["level"] - min(x["level"] for x in shown))
        title = e["title"] if len(e["title"]) <= 62 else e["title"][:59] + "…"
        slug = _overlap(e["start"], e["end"], done)
        mark = "[x]" if slug else "[ ]"
        row = f"  {mark} {i:>3}. {indent}{title.ljust(width)}  p.{e['start']}–{e['end']}  ({e['pages']}p)"
        lines.append(row + (f"  → {slug}" if slug else ""))
    lines += [
        "",
        "Digest one section, not the book:",
        f"  python3 -m kb_distillery.ingest full-digest {raw_rel} --section 1",
        f"  python3 -m kb_distillery.ingest full-digest {raw_rel} --pages {_example(shown)}" if shown else "",
        "  (--section takes a chapter number, #index or title text; --whole-book overrides this gate)",
    ]
    return "\n".join(l for l in lines if l is not None)


# --------------------------------------------------------------------------
# book hub page + partition
# --------------------------------------------------------------------------
def hub_type(raw_rel):
    """A long handwritten PDF is a notebook; anything else long is a book."""
    return "notebook" if raw_rel.startswith(f"raw/{RAW_HANDWRITTEN}/") else "book"


def template_for(page_type):
    return meta_file("templates", f"{page_type}.md")


def _wiki_pages(wiki_dir):
    """Absolute paths of the wiki's pages (index.md and log.md are the bundle's reserved files, not pages)."""
    return [p for p in glob.glob(os.path.join(wiki_dir, "*.md")) if is_page_file(os.path.basename(p))]


def find_hub(raw_rel):
    """(wiki_rel, text) of the book/notebook page for this raw file, or None."""
    for path in sorted(_wiki_pages(os.path.join(ROOT, "wiki"))):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if f"raw: {raw_rel}" not in text[:2000]:
            continue
        fm = parse_frontmatter(text) or {}
        if fm.get("type") in PARTITION_COLLECTIONS and str(fm.get("raw") or "") == raw_rel:
            return os.path.relpath(path, ROOT).replace(os.sep, "/"), text
    return None


def hub_slug(raw_rel):
    """Slug of the hub page — the existing one, else `book-`/`notebook-` + the PDF stem."""
    hub = find_hub(raw_rel)
    if hub:
        return os.path.basename(hub[0])[:-3]
    return make_slug(hub_type(raw_rel), re.sub(r"\.pdf$", "", os.path.basename(raw_rel), flags=re.I))


def partition_for(raw_rel, raw_path):
    """(rows, total, hub_rel). From the hub page when it exists, else proposed from the outline
    (hub_rel None). Rows are sorted by start page."""
    hub = find_hub(raw_rel)
    if hub:
        fm = parse_frontmatter(hub[1]) or {}
        try:
            total = int(str(fm.get("book_pages") or "0"))
        except ValueError:
            total = 0
        rows = [r for r in parse_partition(hub[1]) if r["start"] is not None]
        return sorted(rows, key=lambda r: r["start"]), total or page_count(raw_path), hub[0]
    entries, total, _source = read_toc(raw_path)
    return propose(entries, total), total, None


def format_partition(rows, total, raw_rel, hub_rel):
    """Terminal view of a book's partition, `[x]` digested, `[ ]` backlog, `[-]` skip."""
    where = (f"book page [[{os.path.basename(hub_rel)[:-3]}]]" if hub_rel else
             "no book page yet — PROPOSED partition, written on the first scoped digest")
    lines = [f"{raw_rel} — {total} pages · {where}", coverage_line(rows).replace("**", ""), ""]
    width = min(max((len(r["title"]) for r in rows), default=10), 64)
    nxt = None
    for i, r in enumerate(rows, 1):
        mark = "[x]" if r["status"] in DIGESTED else "[-]" if r["status"] == SKIP else "[ ]"
        title = r["title"] if len(r["title"]) <= 64 else r["title"][:61] + "…"
        n = r["end"] - r["start"] + 1
        tail = f"  {r['status']} → {r['slug']}" if r["slug"] else ("  skip" if r["status"] == SKIP else "")
        lines.append(f"  {mark} {i:>3}. {title.ljust(width)}  p.{r['start']}–{r['end']}  ({n}p){tail}")
        if nxt is None and r["status"] not in DIGESTED and r["status"] != SKIP:
            nxt = i
    lines += ["", "Digest one part, not the book:"]
    if nxt:
        lines.append(f"  python3 -m kb_distillery.ingest full-digest {raw_rel} --part {nxt}")
    lines += ["  (--part N takes a row number above; --pages A-B carves a new part out of undigested",
              "   rows; --section picks an outline entry — `toc --depth 2` shows the outline)"]
    return "\n".join(lines)


def _label_for(entries, start, end):
    """A row title for an ad-hoc page range: the outline entries it spans."""
    inside = [e for e in entries if start <= e["start"] <= end]
    if not inside:
        return f"Pages {start}–{end}"
    lvl = min(e["level"] for e in inside)
    names = [e["title"] for e in inside if e["level"] == lvl]
    return names[0] if len(names) == 1 else f"{names[0]} → {names[-1]}"


def gate(raw_rel, raw_path, pages, section, whole_book, part=None):
    """Books must be scoped. Returns (page_range, label, blocked_message).
    For a book the range must be carvable from its partition: it may cut undigested rows,
    never a digested one."""
    if whole_book or not is_book(raw_path):
        rng = parse_pages(pages, page_count(raw_path)) if pages else None
        return rng, (f"pages {rng[0]}–{rng[1]}" if rng else None), None

    rows, total, hub_rel = partition_for(raw_rel, raw_path)
    view = format_partition(rows, total, raw_rel, hub_rel)
    entries = None
    rng = label = None
    if part:
        try:
            row = rows[int(str(part).lstrip("#")) - 1]
        except (ValueError, IndexError):
            return None, None, f"no part {part!r} — rows run 1–{len(rows)}.\n\n{view}"
        if row["status"] == SKIP:
            return None, None, (f"part {part} ({row['title']}) is marked skip. Change its Status "
                                f"to — on the book page, or use --pages.\n\n{view}")
        rng, label = (row["start"], row["end"]), row["title"]
    elif pages:
        rng = parse_pages(pages, total)
        if not rng:
            return None, None, f"cannot read --pages {pages!r}; use A-B.\n\n{view}"
    elif section:
        entries, total, _source = read_toc(raw_path)
        hit = find_section(entries, section)
        if not hit:
            return None, None, f"no section matching {section!r}.\n\n{view}"
        rng, label = (hit["start"], hit["end"]), hit["title"]
    elif not rows:
        return None, None, (
            f"{raw_rel} is {total} pages and has no readable table of contents.\n"
            f"Pick a page range explicitly, e.g. --pages 19-42, or pass --whole-book "
            f"(the flag for a paper with long appendices) to digest it whole.")
    else:
        return None, None, (f"{raw_rel} is a book ({total} pages) — digest one part of it.\n"
                            f"(a paper with long appendices? pass --whole-book to digest it whole)\n\n"
                            + view)

    same = find_row(rows, *rng)
    if same and same["status"] in DIGESTED:
        return None, None, (f"pages {rng[0]}–{rng[1]} are already digested as [[{same['slug']}]].\n"
                            f"Edit that page, or pick another part:\n\n{view}")
    if not label:
        if same:
            label = same["title"]
        else:
            if entries is None:
                entries, _t, _s = read_toc(raw_path)
            label = _label_for(entries, *rng)
    try:
        carve(rows, rng[0], rng[1], "full", "", label)
    except ValueError as e:
        return None, None, f"{e}.\n\n{view}"
    return rng, label, None


def part_slug(book, label):
    """`part-<book stem>-ch1-boolean-functions-…` / `…-part-i-foundations` from a row title.
    A title too long to keep whole gets a short hash of the full title, so two long titles that
    share a prefix never land on the same page."""
    full = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-"))
    s = re.sub(r"^chapter-(\d+)-", r"ch\1-", full)
    s = re.sub(r"^part-([0-9ivx]+)-", r"part-\1-", s)
    if len(s) > 48:
        tag = hashlib.sha1(" ".join(str(label).split()).lower().encode("utf-8")).hexdigest()[:6]
        s = f"{s[:41].rstrip('-')}-{tag}"
    return f"{SLUG_PREFIX['part']}{strip_prefix(book)}-{s}"


def pdf_title(raw_path):
    fitz = _fitz()
    if not fitz or not os.path.isfile(raw_path):
        return ""
    doc = fitz.open(raw_path)
    title = (doc.metadata or {}).get("title") or ""
    doc.close()
    return " ".join(title.split())


def _set_status(text, status):
    return wikiio.set_key(text, "maturity", status)      # front matter only, never a body line


def new_hub_text(raw_rel, rows, total, meta=None):
    """A fresh book/notebook page from its template. Overview is left for a human/agent."""
    meta = meta or {}
    base = re.sub(r"\.pdf$", "", os.path.basename(raw_rel), flags=re.I)
    title = (meta.get("book_title") or pdf_title(os.path.join(ROOT, raw_rel))
             or base[5:].replace("-", " ").title())
    year = meta.get("year") or (base[:4] if re.match(r"^\d{4}-", base) else "")
    fill = {
        "title": title.replace("#", ""),
        "authors": "[" + ", ".join(meta.get("authors") or []) + "]",
        "year": str(year),
        "area": "[" + ", ".join(meta.get("area") or []) + "]",
        "raw": raw_rel,
        "url": meta.get("url") or "",
        "book_pages": str(total),
        "maturity": book_status(rows),
        "partition": "",
    }
    with open(template_for(hub_type(raw_rel)), encoding="utf-8") as f:
        text = f.read()
    for k, v in fill.items():
        text = text.replace("{{" + k + "}}", v)
    text = frontmatter.fill_title(text)
    return replace_partition(text, rows, PART_MAX_PAGES)


def record_part(raw_rel, start, end, slug, status, label, meta=None):
    """Mark pages start–end as digested part [[slug]] on the book page, creating the page from
    the proposed partition if it does not exist. Returns (wiki_rel, created)."""
    raw_path = os.path.join(ROOT, raw_rel)
    rows, total, hub_rel = partition_for(raw_rel, raw_path)
    created = hub_rel is None
    if created:
        hub_rel = f"wiki/{hub_slug(raw_rel)}.md"
        text = None
    else:
        with open(os.path.join(ROOT, hub_rel), encoding="utf-8") as f:
            text = f.read()
    same = find_row(rows, start, end)
    title = same["title"] if same and same["title"] else label
    rows = carve(rows, start, end, status, slug, title)
    if created:
        text = new_hub_text(raw_rel, rows, total, meta)
    else:
        text = _set_status(wikiio.edit_body(text, lambda t: replace_partition(t, rows, PART_MAX_PAGES)),
                           book_status(rows))
    wikiio.write_page(os.path.join(ROOT, hub_rel), text)
    return hub_rel, created

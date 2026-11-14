"""Generic book handling: detect long PDFs, build their chapters, pick chapters to digest.

A book is any PDF long enough that a 25-page skim from the front is meaningless. Ingest builds
its book page with a `## Chapters` table first (`build_book`); digest then works one chapter at
a time and refuses to run before that page exists.

Section ranges are 1-based inclusive page numbers as printed by `toc`, matching what the PDF
outline reports (physical PDF pages, which for a typeset book run ahead of the printed folios).
"""
import glob
import hashlib
import os
import re
import sys

from kb_distillery.ingest.paths import ROOT
from kb_distillery.config.paths import meta_file
from kb_distillery.storage import pdf as pdflib
from kb_distillery.vault import frontmatter, wikiio
from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.vault.schema import RAW_HANDWRITTEN, SLUG_PREFIX, is_page_file, make_slug, strip_prefix
from kb_distillery.vault import books as core
from kb_distillery.vault.books import (DIGESTED, SKIP, book_status, content_ids, coverage_line,
                                       parse_chapters, propose, replace_chapters, row_at, select, set_chapter)

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


def _pdf():
    """The PDF reader, or None (with a hint on stderr) when the library is not installed."""
    if pdflib.available():
        return pdflib
    print(pdflib.missing_msg(), file=sys.stderr)
    return None


def page_count(raw_path):
    if not os.path.isfile(raw_path) or not raw_path.lower().endswith(".pdf"):
        return 0                       # not a PDF: no library needed (and no install hint)
    reader = _pdf()
    if not reader:
        return 0
    doc = reader.PdfDoc(raw_path)
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
    raw = doc.toc()
    entries = [{"level": lvl, "title": " ".join(str(t).split()), "start": max(1, int(p))}
               for lvl, t, p in raw if p and int(p) > 0]
    return _finish(entries, doc.page_count)


def _from_text(doc):
    """Fallback for PDFs with no embedded outline: parse a printed contents page."""
    entries = []
    for i in range(min(TOC_SCAN_PAGES, doc.page_count)):
        for line in doc.page_text(i).splitlines():
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
    reader = _pdf()
    if not reader or not os.path.isfile(raw_path) or not raw_path.lower().endswith(".pdf"):
        return [], 0, "none"
    doc = reader.PdfDoc(raw_path)
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
    reader = _pdf()
    if not reader or not os.path.isfile(raw_path):
        return False
    try:
        doc = reader.PdfDoc(raw_path)
        try:
            for lvl, title, _p in doc.toc():
                if lvl == 1 and CHAPTER_RE.match(str(title)):
                    return False
            first = doc.page_text(0) if doc.page_count else ""
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


def digested_ranges(raw_rel):
    """[(slug, start, end)] already digested from this raw file, read from wiki frontmatter."""
    import glob
    from kb_distillery.config.paths import vault_root
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
        "Digest by chapter (the book page's ## Chapters table):",
        f"  python3 -m kb_distillery.ingest full-digest {raw_rel} --chapter 1",
        "  (--section takes a chapter number, #index or title text and resolves to its chapter)",
    ]
    return "\n".join(l for l in lines if l is not None)


# --------------------------------------------------------------------------
# chapters at ingest: outline, then page headings, else a clear stop
# --------------------------------------------------------------------------
HEADING_LINES = 3            # a chapter heading sits in the first lines of its page
CHAPTERS_FILE_HINT = (
    "Supply the chapter breaks by hand: write a text file with one chapter per line,\n"
    "  id<TAB>title<TAB>first-last      e.g.  ch1<TAB>Chapter 1. Basics<TAB>19-42\n"
    "(ids: front, ch1, ch2, …, appA, back; pages are physical PDF pages and must cover the whole book),\n"
    "then run again with --chapters-file <file>.")


class BookError(ValueError):
    """Ingest could not build a book's chapters. The message carries the hint."""


def _from_headings(doc):
    """Chapter entries from page headings: a page whose first lines say 'Chapter N' / 'Appendix X'."""
    entries, seen = [], set()
    for i in range(doc.page_count):
        lines = [l.strip() for l in doc.page_text(i).splitlines() if l.strip()][:HEADING_LINES]
        for n, line in enumerate(lines):
            if not re.match(r"^(chapter|appendix)\s+\w", line, re.I):
                continue
            title = line
            if len(line.split()) <= 2 and n + 1 < len(lines):
                title = f"{line}. {lines[n + 1]}"         # 'Chapter 3' / 'Influences' on two lines
            cid = core.chapter_id(title)
            if cid and cid not in seen:
                seen.add(cid)
                entries.append({"level": 1, "title": title, "start": i + 1})
            break
    return _finish(entries, doc.page_count) if len(entries) >= 2 else []


def chapter_rows(raw_path):
    """(rows, total, source): chapters from the PDF outline, else from page headings; rows is []
    when neither yields numbered chapters (`source` 'none')."""
    reader = _pdf()
    if not reader or not os.path.isfile(raw_path):
        return [], 0, "none"
    doc = reader.PdfDoc(raw_path)
    try:
        total = doc.page_count
        rows = propose(_from_outline(doc), total)
        if rows:
            return rows, total, "outline"
        rows = propose(_from_headings(doc), total)
        return rows, total, ("headings" if rows else "none")
    finally:
        doc.close()


def plan_chapters(raw_path, chapters_file=None):
    """(rows, total, outline_chapters, source) for a book PDF. Raises BookError with the
    chapters-file hint when no chapters can be found; never guesses."""
    total = page_count(raw_path)
    if chapters_file:
        try:
            with open(chapters_file, encoding="utf-8") as f:
                rows = core.parse_chapters_file(f.read(), total)
        except OSError as e:
            raise BookError(f"cannot read --chapters-file: {e}") from e
        except ValueError as e:
            raise BookError(f"{e}\n{CHAPTERS_FILE_HINT}") from e
        return rows, total, len(content_ids(rows)), "file"
    rows, total, source = chapter_rows(raw_path)
    if not rows:
        raise BookError(f"{os.path.basename(raw_path)} is a book ({total} pages) but neither its PDF "
                        f"outline nor its page headings give numbered chapters.\n{CHAPTERS_FILE_HINT}")
    return rows, total, len(content_ids(rows)), source


# --------------------------------------------------------------------------
# the book page
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
    return core.find_hub(ROOT, raw_rel)


def hub_slug(raw_rel):
    """Slug of the hub page — the existing one, else `book-`/`notebook-` + the PDF stem."""
    hub = find_hub(raw_rel)
    if hub:
        return os.path.basename(hub[0])[:-3]
    return make_slug(hub_type(raw_rel), re.sub(r"\.pdf$", "", os.path.basename(raw_rel), flags=re.I))


def chapters_for(raw_rel):
    """(rows, total, hub_rel) from the book page, or ([], pages, None) when there is none yet."""
    hub = find_hub(raw_rel)
    if not hub:
        return [], 0, None
    fm = parse_frontmatter(hub[1]) or {}
    try:
        total = int(str(fm.get("book_pages") or "0"))
    except ValueError:
        total = 0
    rows = [r for r in parse_chapters(hub[1]) if r["start"] is not None]
    return sorted(rows, key=lambda r: r["start"]), total, hub[0]


def ingest_hint(raw_rel):
    return (f"{raw_rel} is a book with no book page yet — ingest builds its chapters first:\n"
            f"  python3 -m kb_distillery.ingest book {raw_rel}   [--chapters-file <file>]")


def format_chapters(rows, total, raw_rel, hub_rel):
    """Terminal view of a book's chapters, `[x]` digested, `[ ]` backlog, `[-]` skip."""
    lines = [f"{raw_rel} — {total} pages · book page [[{os.path.basename(hub_rel)[:-3]}]]",
             coverage_line(rows).replace("**", ""), ""]
    width = min(max((len(r["title"]) for r in rows), default=10), 60)
    idw = max((len(r["id"]) for r in rows), default=4)
    nxt = None
    for r in rows:
        mark = "[x]" if r["status"] in DIGESTED else "[-]" if r["status"] == SKIP else "[ ]"
        title = r["title"] if len(r["title"]) <= 60 else r["title"][:57] + "…"
        n = r["end"] - r["start"] + 1
        tail = f"  {r['status']} → {r['slug']}" if r["slug"] else ("  skip" if r["status"] == SKIP else "")
        lines.append(f"  {mark} {r['id'].ljust(idw)}  {title.ljust(width)}  p.{r['start']}–{r['end']}  ({n}p){tail}")
        if nxt is None and r["status"] not in DIGESTED and r["status"] != SKIP:
            nxt = r["id"]
    lines += ["", "Digest by chapter:"]
    if nxt:
        lines.append(f"  python3 -m kb_distillery.ingest full-digest {raw_rel} --chapter {nxt}")
    lines += ["  (--chapter 3 / ch3 / appA, --chapters 1-3, --all; --section resolves an outline entry",
              "   to its chapter — `toc --depth 2` shows the outline)"]
    return "\n".join(lines)


def gate(raw_rel, raw_path, chapter=None, chapters=None, all_chapters=False, section=None):
    """Digest of a book works by chapter. Returns (rows, blocked_message): the undigested chapter
    rows to digest (one part page each), or None and why. Not a book: ([], None)."""
    asked = chapter or chapters or all_chapters or section
    if not is_book(raw_path):
        if asked:
            return None, f"{raw_rel} is not a book — digest it whole, without chapter flags."
        return [], None
    rows, total, hub_rel = chapters_for(raw_rel)
    if not hub_rel:
        return None, ingest_hint(raw_rel)
    view = format_chapters(rows, total, raw_rel, hub_rel)
    if not asked:
        return None, f"{raw_rel} is a book ({total} pages) — digest it by chapter.\n\n{view}"
    if section:
        entries, _t, _s = read_toc(raw_path)
        hit = find_section(entries, section)
        row = row_at(rows, hit["start"]) if hit else None
        if not row:
            return None, f"no chapter for section {section!r}.\n\n{view}"
        sel = row["id"]
    else:
        sel = "all" if all_chapters else (chapters or chapter)
    try:
        picked = select(rows, sel)
    except ValueError as e:
        return None, f"{e}\n\n{view}"
    single = bool(chapter or section)
    skipped = [r for r in picked if r["status"] == SKIP]
    if single and skipped:
        return None, (f"chapter {skipped[0]['id']} ({skipped[0]['title']}) is marked skip. Change its "
                      f"Status to — on the book page first.\n\n{view}")
    done = [r for r in picked if r["status"] in DIGESTED]
    if single and done:
        return None, (f"chapter {done[0]['id']} is already digested as [[{done[0]['slug']}]]. "
                      f"Edit that page, or pick another chapter:\n\n{view}")
    todo = [r for r in picked if r["status"] not in DIGESTED and r["status"] != SKIP]
    if not todo:
        return None, f"nothing left to digest in {sel!r}.\n\n{view}"
    return todo, None


def part_slug(book, label, chapter=None):
    """`part-<book stem>-ch1-boolean-functions-…` from the chapter id and its row title.
    A title too long to keep whole gets a short hash of the full title, so two long titles that
    share a prefix never land on the same page."""
    full = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-"))
    if chapter:
        topic = re.sub(r"^(?:chapter|ch|lecture)-?[0-9ivxlc]+-", "", full)
        topic = re.sub(r"^appendix-[a-z]-", "", topic)
        topic = re.sub(r"^[0-9]+-", "", topic)
        s = f"{chapter.lower()}-{topic}".strip("-") if topic else chapter.lower()
    else:
        s = re.sub(r"^chapter-(\d+)-", r"ch\1-", full)
        s = re.sub(r"^part-([0-9ivx]+)-", r"part-\1-", s)
    if len(s) > 48:
        tag = hashlib.sha1(" ".join(str(label).split()).lower().encode("utf-8")).hexdigest()[:6]
        s = f"{s[:41].rstrip('-')}-{tag}"
    return f"{SLUG_PREFIX['part']}{strip_prefix(book)}-{s}"


def pdf_title(raw_path):
    reader = _pdf()
    if not reader or not os.path.isfile(raw_path):
        return ""
    doc = reader.PdfDoc(raw_path)
    title = " ".join((doc.title or "").split())
    doc.close()
    return "" if title.lower() == "untitled" else title      # a PDF writer's placeholder, not a title


def _set_status(text, status):
    return wikiio.set_key(text, "maturity", status)      # front matter only, never a body line


def new_hub_text(raw_rel, rows, total, meta=None, outline_chapters=None):
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
        "outline_chapters": str(outline_chapters if outline_chapters is not None else len(content_ids(rows))),
        "maturity": book_status(rows),
        "chapters": "",
    }
    with open(template_for(hub_type(raw_rel)), encoding="utf-8") as f:
        text = f.read()
    for k, v in fill.items():
        text = text.replace("{{" + k + "}}", v)
    text = frontmatter.fill_conventions(frontmatter.fill_title(text))
    return replace_chapters(text, rows)


def build_book(raw_rel, raw_path=None, chapters_file=None, meta=None):
    """Write the book page with its `## Chapters` table for a filed book PDF. Returns
    (wiki_rel, rows); an existing book page is left alone. Raises BookError when no chapters can be
    found (nothing is written)."""
    raw_path = raw_path or os.path.join(ROOT, raw_rel)
    hub = find_hub(raw_rel)
    if hub:
        return hub[0], chapters_for(raw_rel)[0]
    rows, total, n, _source = plan_chapters(raw_path, chapters_file)
    wiki_rel = f"wiki/{hub_slug(raw_rel)}.md"
    text = new_hub_text(raw_rel, rows, total, meta, outline_chapters=n)
    wikiio.write_page(os.path.join(ROOT, wiki_rel), text)
    return wiki_rel, rows


def record_part(raw_rel, chapter, slug, status, meta=None):
    """Mark chapter `chapter` as digested part [[slug]] on the book page. Returns (wiki_rel, False).
    Raises ValueError when there is no book page or no such chapter (ingest builds both)."""
    rows, _total, hub_rel = chapters_for(raw_rel)
    if not hub_rel:
        raise ValueError(ingest_hint(raw_rel))
    try:
        rows = set_chapter(rows, chapter, status, slug)
    except KeyError:
        raise ValueError(f"[[{hub_slug(raw_rel)}]] has no chapter {chapter!r}") from None
    with open(os.path.join(ROOT, hub_rel), encoding="utf-8") as f:
        text = f.read()
    text = _set_status(wikiio.edit_body(text, lambda t: replace_chapters(t, rows)), book_status(rows))
    fm = parse_frontmatter(text) or {}
    for key in ("authors", "area", "url"):        # the first digest knows what the PDF did not
        val = (meta or {}).get(key)
        if val and not fm.get(key):
            text = wikiio.set_key(text, key, "[" + ", ".join(val) + "]" if isinstance(val, list) else str(val))
    wikiio.write_page(os.path.join(ROOT, hub_rel), text)
    return hub_rel, False

"""Book hub pages and their chapters. Pure functions, no third-party deps.

A book is one `type: book` page. Its `## Chapters` table splits pages 1..book_pages into
disjoint, exhaustive chapters. Each row carries a fixed id taken from the book's own numbering
(`ch1`, `ch11`, `appA`, plus `front` and `back`); a row keeps its id forever. A long chapter may be
split by hand into lettered rows (`ch11a`, `ch11b`); rows are never merged. Each digested chapter
has its own `type: part` page (`chapter: ch3`); undigested chapters are rows, not pages.

    | Id | Chapter | Pages | Status | Note |
    |----|---------|-------|--------|------|
    | front | Front matter · Preface | 1–18 | skip | |
    | ch1 | Chapter 1. Boolean functions | 19–42 | full | [Part title](slug.md) |
    | ch2 | Chapter 2. Social choice | 43–68 | — | |

`chapters(root, raw_rel)` and `select(rows, selector)` are the public entry points for code that
works on one chapter at a time.
"""
import glob
import os
import re
from dataclasses import dataclass

from kb_distillery.vault import frontmatter
from kb_distillery.vault import links as page_links

CHAPTERS_HEADING = "## Chapters"
PARTITION_HEADING = "## Partition"      # the pre-1.6 table; migration 0016 rewrites it
OVERVIEW_HEADING = "## Overview"
OVERVIEW_MIN_CHARS = 120
CHAPTER_LONG_PAGES = 60      # warn above this; a long chapter is kept whole, splitting is manual
PART_MAX_PAGES = CHAPTER_LONG_PAGES
SKIP = "skip"
TODO = "—"
DIGESTED = ("easy", "full", "deep")
ROW_STATUS = {SKIP, TODO, *DIGESTED}
FRONT, BACK = "front", "back"

# ch3, ch11a (a manual split), appA, appB2, front, back
ID_RE = re.compile(r"^(?:front|back|ch\d+[a-z]?|app[A-Z]\d*[a-z]?)$")
_BASE = re.compile(r"^(ch\d+|app[A-Z]\d*)[a-z]?$")
_PAGES = re.compile(r"^\s*(\d+)\s*(?:[–—-]\s*(\d+))?\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Front/back matter: never a reading unit of its own.
_MATTER = re.compile(
    r"^(front matter|back matter|prefaces?|foreword|acknowledg\w*|(table of )?contents|"
    r"list of (notation|symbols|figures|tables)|notation|bibliography|references|"
    r"index|notes|about the authors?|dedication|copyright|title page)\b", re.I)
# End-of-chapter sections that fold into their chapter instead of getting a row.
_FOLD = re.compile(r"^(exercises?|problems?|notes|notes and references|bibliographic notes|"
                   r"exercises and notes|chapter notes)\b", re.I)
_CHAPTER = re.compile(r"^\s*(?:chapter|ch\.?|lecture)\s*([0-9]+|[IVXLC]+)\b", re.I)
_APPENDIX = re.compile(r"^\s*appendix\s*([A-Z])(?:[^a-z]|$)", re.I)
_NUMBERED = re.compile(r"^\s*([0-9]+)(?:\.|\s)\s*\S")


# --------------------------------------------------------------------------
# ids
# --------------------------------------------------------------------------
def valid_id(cid):
    return bool(ID_RE.match(cid or ""))


def base_id(cid):
    """`ch11a` → `ch11`; ids without a split letter are their own base."""
    m = _BASE.match(cid or "")
    return m.group(1) if m else (cid or "")


def _roman(s):
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = vals[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def chapter_id(title):
    """The id a heading names: 'Chapter 3. …' → ch3, '3. …' → ch3, 'Appendix B …' → appB, else ''."""
    t = _clean(title)
    m = _CHAPTER.match(t)
    if m:
        n = m.group(1)
        return f"ch{int(n) if n.isdigit() else _roman(n)}"
    m = _APPENDIX.match(t)
    if m:
        return f"app{m.group(1).upper()}"
    m = _NUMBERED.match(t)
    if m and not re.match(r"^\s*[0-9]+\.[0-9]", t):
        return f"ch{int(m.group(1))}"
    return ""


def _id_key(cid):
    """Sort/compare key: chapters by number, then appendices, split letters after their base."""
    m = re.match(r"^ch(\d+)([a-z]?)$", cid)
    if m:
        return (1, int(m.group(1)), "", m.group(2))
    m = re.match(r"^app([A-Z])(\d*)([a-z]?)$", cid)
    if m:
        return (2, 0, m.group(1) + m.group(2), m.group(3))
    return (0 if cid == FRONT else 3, 0, "", "")


# --------------------------------------------------------------------------
# the table
# --------------------------------------------------------------------------
def section(text, heading):
    """Body of a `## heading` section, up to the next `## `."""
    if heading not in text:
        return ""
    rest = text.split(heading, 1)[1]
    body = []
    for line in rest.split("\n")[1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def overview_ok(text):
    """The Overview must hold at least one real paragraph, not a placeholder."""
    body = _COMMENT.sub("", section(text, OVERVIEW_HEADING))
    prose = " ".join(l.strip() for l in body.split("\n")
                     if l.strip() and not l.lstrip().startswith(("|", "#", ">")))
    return len(prose) >= OVERVIEW_MIN_CHARS


def _first_link(cell):
    """(slug, link text) of the first page link in a table cell, else None."""
    m = page_links.PAGE_LINK.search(cell)
    if m:
        label, slug, _anchor = page_links.link_parts(m)
        return slug, label
    w = page_links.WIKILINK.search(cell)
    return (w.group(1).strip(), (w.group(2) or "").strip()) if w else None


def _status(cell):
    s = cell.strip().strip("*`").lower()
    return TODO if s in ("", "-", "—", "–") else s


def parse_chapters(text):
    """Rows of the `## Chapters` table: [{id, title, start, end, status, slug}], in table order.
    A row whose Pages cell is unreadable keeps start/end None so validation can report it."""
    rows = []
    for line in section(text, CHAPTERS_HEADING).split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if len(cells) < 4 or all(set(c) <= set("-: ") and c for c in cells[:4]) or cells[0].lower() == "id":
            continue
        cells += [""] * (5 - len(cells))
        m = _PAGES.match(cells[2])
        start = int(m.group(1)) if m else None
        end = int(m.group(2) or m.group(1)) if m else None
        link = _first_link(cells[4]) or _first_link(cells[1])
        row = {"id": cells[0].strip("`* "), "title": cells[1].replace("\\|", "|"), "start": start,
               "end": end, "status": _status(cells[3]), "slug": link[0] if link else ""}
        if link and link[1] and link[1] != link[0]:
            row["link_text"] = link[1]
        rows.append(row)
    return rows


def pages_of(row):
    return row["end"] - row["start"] + 1


def content_ids(rows):
    """Distinct base ids of the reading rows (a split chapter counts once)."""
    return list(dict.fromkeys(base_id(r["id"]) for r in rows if r["status"] != SKIP and r["id"]))


def validate(rows, total, outline_chapters=None, cap=CHAPTER_LONG_PAGES):
    """(errors, warnings) for the chapters of pages 1..total."""
    errs, warns = [], []
    if not rows:
        return [f"{CHAPTERS_HEADING} has no rows"], warns
    seen = {}
    for r in rows:
        if not r["id"]:
            errs.append(f"chapter row {r['title']!r}: missing id (ch3, appA, front, back)")
        elif not valid_id(r["id"]):
            errs.append(f"chapter row {r['title']!r}: id {r['id']!r} is not ch<N>, ch<N><letter>, "
                        "app<X>, front or back")
        elif r["id"] in seen:
            errs.append(f"duplicate chapter id {r['id']!r} ({seen[r['id']]!r} and {r['title']!r})")
        else:
            seen[r["id"]] = r["title"]
    for r in rows:
        if r["id"] in (FRONT, BACK) and r["status"] != SKIP:
            errs.append(f"chapter row {r['id']}: front and back matter rows are skip")
        if r["start"] is None:
            errs.append(f"chapter row {r['id'] or r['title']!r}: unreadable Pages cell (use `A–B`)")
    ordered = sorted((r for r in rows if r["start"] is not None), key=lambda r: r["start"])
    expect = 1
    for r in ordered:
        label = f"{r['id'] or '?'} p.{r['start']}–{r['end']}"
        if r["end"] < r["start"]:
            errs.append(f"chapter row {label}: end before start")
            continue
        if r["start"] > expect:
            errs.append(f"chapter gap: pages {expect}–{r['start'] - 1} belong to no chapter")
        elif r["start"] < expect:
            errs.append(f"chapter overlap: {label} starts inside the previous chapter")
        expect = max(expect, r["end"] + 1)
        if r["status"] not in ROW_STATUS:
            errs.append(f"chapter row {label}: status {r['status']!r} not in {sorted(ROW_STATUS)}")
        if r["status"] in DIGESTED and not r["slug"]:
            errs.append(f"chapter row {label}: status {r['status']} needs a link to its part page")
        if r["status"] != SKIP and pages_of(r) > cap:
            warns.append(f"chapter row {label}: {pages_of(r)} pages, over {cap} — kept whole; "
                         f"split it by hand ({r['id']}a, {r['id']}b) if it reads better")
    if total and expect - 1 != total:
        if expect - 1 < total:
            errs.append(f"chapter gap: pages {expect}–{total} belong to no chapter")
        else:
            errs.append(f"chapters run to p.{expect - 1}, past book_pages: {total}")
    if outline_chapters is not None and len(content_ids(rows)) != outline_chapters:
        errs.append(f"{len(content_ids(rows))} chapters in the table but the outline has "
                    f"{outline_chapters} (`outline_chapters:`) — a chapter was dropped or invented")
    return errs, warns


def coverage(rows):
    """(digested pages, content pages). Skip rows count toward neither."""
    ok = [r for r in rows if r["start"] is not None]
    done = sum(pages_of(r) for r in ok if r["status"] in DIGESTED)
    content = sum(pages_of(r) for r in ok if r["status"] != SKIP)
    return done, content


def chapter_coverage(rows):
    """(digested chapters, chapters). A split chapter is done when all its rows are."""
    by_base = {}
    for r in rows:
        if r["status"] == SKIP or not r["id"]:
            continue
        by_base.setdefault(base_id(r["id"]), []).append(r["status"] in DIGESTED)
    return sum(all(v) for v in by_base.values()), len(by_base)


def book_status(rows):
    done, content = chapter_coverage(rows)
    if content and done >= content:
        return "digested"
    return "reading" if done else "to-read"


def coverage_line(rows, cap=CHAPTER_LONG_PAGES):
    done, content = chapter_coverage(rows)
    return f"Coverage: **{done} / {content} chapters** · skip rows excluded"


def render(rows, cap=CHAPTER_LONG_PAGES):
    """Coverage line + table for the `## Chapters` section body."""
    out = [coverage_line(rows, cap), "",
           "| Id | Chapter | Pages | Status | Note |", "|----|---------|-------|--------|------|"]
    for r in sorted(rows, key=lambda r: (r["start"] or 0)):
        note = page_links.link(r["slug"], r.get("link_text") or r["slug"]) if r["slug"] else ""
        title = r["title"].replace("|", "\\|")
        out.append(f"| {r['id']} | {title} | {r['start']}–{r['end']} | {r['status']} | {note} |")
    return "\n".join(out)


def replace_chapters(text, rows, cap=CHAPTER_LONG_PAGES):
    """Rewrite the `## Chapters` section of a book page in place (a `## Partition` heading is
    replaced too, so a migrated page carries one table)."""
    body = render(rows, cap)
    heading = CHAPTERS_HEADING if CHAPTERS_HEADING in text else (
        PARTITION_HEADING if PARTITION_HEADING in text else None)
    if heading is None:
        return text.rstrip() + f"\n\n{CHAPTERS_HEADING}\n\n{body}\n"
    head, rest = text.split(heading, 1)
    lines = rest.split("\n")
    tail = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), None)
    after = "\n".join(lines[tail:]) if tail is not None else ""
    return f"{head}{CHAPTERS_HEADING}\n\n{body}\n" + (f"\n{after}" if after else "")


def find_chapter(rows, cid):
    for r in rows:
        if r["id"] == cid:
            return r
    return None


def row_at(rows, page):
    """The row whose page range holds `page`, else None."""
    for r in rows:
        if r["start"] is not None and r["start"] <= page <= r["end"]:
            return r
    return None


def set_chapter(rows, cid, status, slug):
    """A copy of rows with chapter `cid` marked `status` and linked to `slug`. Raises KeyError."""
    if not find_chapter(rows, cid):
        raise KeyError(cid)
    return [{**r, "status": status, "slug": slug} if r["id"] == cid else dict(r) for r in rows]


# --------------------------------------------------------------------------
# chapters from a PDF outline (entries shaped like ingest.sources.books.book.read_toc)
# --------------------------------------------------------------------------
def _clean(title):
    """Outline titles from LaTeX PDFs can arrive as 'to 1.15Appendix ATechnical Lemmas'."""
    title = re.sub(r"^\s*to\s+[0-9.]+", "", str(title))
    title = re.sub(r"\b(Appendix|Chapter|Part)\s*([A-Z0-9]+?)(?=[A-Z][a-z])", r"\1 \2 ", title)
    return " ".join(title.split())


def _is_matter(title):
    return bool(_MATTER.match(re.sub(r"^[0-9.\s]+", "", _clean(title))))


def _is_fold(title):
    return bool(_FOLD.match(re.sub(r"^[0-9.\s]+", "", _clean(title))))


def _row(cid, title, start, end, status=TODO):
    return {"id": cid, "title": title, "start": start, "end": end, "status": status, "slug": ""}


def propose(entries, total):
    """Chapter rows covering 1..total from outline entries, or [] when no numbered chapter is
    found (the caller then stops: it never guesses). Rules:
      * the chapter level is the shallowest outline level that numbers its entries; deeper
        entries (sections, exercises) belong to their chapter, shallower ones (Part I) are wrappers;
      * pages before the first chapter are `front`, matter after the last one is `back` (skip);
      * exercises / notes entries at the chapter level fold into the chapter before them;
      * an unnumbered entry before the first chapter is `ch0` (an introduction), after a chapter
        it folds into that chapter."""
    if not total or not entries:
        return []
    numbered = {}
    for e in entries:
        cid = chapter_id(e["title"])
        if cid.startswith("ch"):
            numbered.setdefault(e["level"], []).append(cid)
    levels = sorted(lv for lv, ids in numbered.items() if len(set(ids)) >= 2) or sorted(numbered)
    if not levels:
        return []
    level = levels[0]
    seq = [e for e in entries
           if e["level"] == level or (e["level"] < level and chapter_id(e["title"]).startswith("app"))]
    seq = sorted(seq, key=lambda e: e["start"])
    rows = []
    if seq and seq[0]["start"] > 1:
        rows.append(_row(FRONT, "Front matter", 1, seq[0]["start"] - 1, SKIP))
    for n, e in enumerate(seq):
        s = max(1, e["start"])
        f = (seq[n + 1]["start"] - 1) if n + 1 < len(seq) else total
        if f < s:
            f = s if n + 1 == len(seq) else s - 1
            if f < s:
                continue                    # two entries on one page: the later one wins the page
        title = _clean(e["title"])
        cid = chapter_id(title)
        last = rows[-1] if rows else None
        started = any(r["status"] != SKIP for r in rows)
        if cid:
            if last and last["id"] == cid:
                last["end"] = f                       # the same chapter named twice
            else:
                rows.append(_row(cid, title, s, f))
        elif _is_fold(title) and last and last["status"] != SKIP:
            last["end"] = f                           # exercises / notes join their chapter
        elif _is_matter(title) or _is_fold(title):
            rows.append(_row(BACK if started else FRONT, title, s, f, SKIP))
        elif not started:
            if last and last["id"] == "ch0":
                last["end"] = f
            else:
                rows.append(_row("ch0", title, s, f))  # an unnumbered introduction
        else:
            last["end"] = f                           # an unnumbered aside joins what precedes it
    # matter between chapters (a mid-book Notes) folds into the row before it; skip rows of one
    # kind merge
    out = []
    for i, r in enumerate(rows):
        later = any(x["status"] != SKIP for x in rows[i + 1:])
        if out and r["id"] == BACK and later:
            out[-1]["end"] = r["end"]
            continue
        if out and r["status"] == SKIP and out[-1]["status"] == SKIP and out[-1]["id"] == r["id"]:
            out[-1] = {**out[-1], "end": r["end"], "title": f"{out[-1]['title']} · {r['title']}"}
            continue
        out.append(r)
    if not any(r["id"].startswith(("ch", "app")) for r in out):
        return []
    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)):
        return []                                 # the outline numbers two chapters alike: do not guess
    return out


def parse_chapters_file(text, total=None):
    """Rows from a hand-written chapters file, one chapter per line:

        id<TAB>title<TAB>first-last

    Blank lines and `#` comments are ignored. `front`/`back` rows are skip. Raises ValueError on a
    malformed line or a table that does not validate."""
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            raise ValueError(f"chapters file line {n}: want id<TAB>title<TAB>first-last, got {line!r}")
        cid, title, rng = (p.strip() for p in parts)
        m = _PAGES.match(rng)
        if not m:
            raise ValueError(f"chapters file line {n}: pages {rng!r} are not first-last")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        rows.append(_row(cid, title, a, b, SKIP if cid in (FRONT, BACK) else TODO))
    errs, _w = validate(rows, total)
    if errs:
        raise ValueError("chapters file: " + "; ".join(errs))
    return rows


# --------------------------------------------------------------------------
# the public helper: chapters of a raw file, and selectors over them
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    first_page: int
    last_page: int
    status: str
    slug: str = ""

    @property
    def digested(self):
        return self.status in DIGESTED


def _as_chapter(r):
    return Chapter(r["id"], r["title"], r["start"], r["end"], r["status"], r["slug"])


def find_hub(root, raw_rel):
    """(wiki_rel, text) of the book/notebook page whose `raw:` is raw_rel, or None."""
    for path in sorted(glob.glob(os.path.join(root, "wiki", "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if f"raw: {raw_rel}" not in text[:2000]:
            continue
        fm, _body = frontmatter.parse(text)
        if (fm or {}).get("type") in ("book", "notebook") and str(fm.get("raw") or "") == raw_rel:
            return os.path.relpath(path, root).replace(os.sep, "/"), text
    return None


def chapters(root, raw_rel):
    """The ordered chapters of a book raw file, read from its book page, as [Chapter]
    (id, title, first_page, last_page, status, slug). Raises LookupError when the raw file has no
    book page yet (ingest builds it)."""
    hub = find_hub(root, raw_rel)
    if not hub:
        raise LookupError(f"{raw_rel} has no book page — ingest it first "
                          f"(`python3 -m kb_distillery.ingest book {raw_rel}`)")
    rows = [r for r in parse_chapters(hub[1]) if r["start"] is not None]
    return [_as_chapter(r) for r in sorted(rows, key=lambda r: r["start"])]


def _norm_sel(tok):
    tok = tok.strip()
    if re.fullmatch(r"\d+", tok):
        return f"ch{int(tok)}"
    if re.fullmatch(r"(?i)ch\d+[a-z]?", tok):
        return "ch" + tok[2:].lower()
    if re.fullmatch(r"(?i)app[a-z]\d*[a-z]?", tok):
        return "app" + tok[3].upper() + tok[4:]
    if re.fullmatch(r"[A-Z]", tok):
        return f"app{tok}"
    return tok


def select(rows, selector):
    """Resolve a selector to rows (dicts or Chapter objects, in book order):
    `3` / `ch3` (with its splits ch3a, ch3b), `ch3a`, `appA`, `1-3` / `ch1-ch3`, `all`
    (every non-skip row), or a comma list of these. Raises ValueError naming the valid ids."""
    def rid(r):
        return r.id if isinstance(r, Chapter) else r["id"]

    def rstatus(r):
        return r.status if isinstance(r, Chapter) else r["status"]

    def rstart(r):
        return (r.first_page if isinstance(r, Chapter) else r["start"]) or 0

    rows = sorted(rows, key=rstart)
    sel = str(selector or "").strip()
    if not sel:
        raise ValueError("empty chapter selector")
    if sel.lower() == "all":
        return [r for r in rows if rstatus(r) != SKIP]
    picked = []
    for tok in sel.split(","):
        tok = tok.strip()
        m = re.fullmatch(r"(?i)(?:ch)?(\d+)\s*-\s*(?:ch)?(\d+)", tok)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            hits = [r for r in rows if re.fullmatch(r"ch\d+[a-z]?", rid(r))
                    and a <= int(re.match(r"ch(\d+)", rid(r)).group(1)) <= b]
        else:
            want = _norm_sel(tok)
            hits = [r for r in rows if rid(r) == want] or [r for r in rows if base_id(rid(r)) == want]
        if not hits:
            ids = ", ".join(rid(r) for r in rows if rstatus(r) != SKIP)
            raise ValueError(f"no chapter {tok!r} — this book has: {ids}")
        picked += [r for r in hits if r not in picked]
    return sorted(picked, key=rstart)

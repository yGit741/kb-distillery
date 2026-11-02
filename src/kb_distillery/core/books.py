"""Book hub pages and their page partition. Pure functions, no third-party deps.

A book is one `type: book` page. Its `## Partition` table splits pages 1..book_pages into
disjoint, exhaustive parts. Each digested part has its own `type: part` page; undigested
parts are rows, not pages. A part's identity is its page range — the `#` column is display
order only, renumbered whenever a row is split.

    | # | Part | Pages | Status | Note |
    |---|------|-------|--------|------|
    | 1 | Front matter · Preface | 1–18 | skip | |
    | 2 | Chapter 1. Boolean functions and the Fourier expansion | 19–42 | full | [Part title](slug.md) |
    | 3 | Chapter 2. Basic concepts and social choice | 43–68 | — | |
"""
import re
from kb_distillery.core import links as page_links

PARTITION_HEADING = "## Partition"
OVERVIEW_HEADING = "## Overview"
OVERVIEW_MIN_CHARS = 120
PART_MAX_PAGES = 60          # warn above this; a part this long is a book of its own
SKIP = "skip"
TODO = "—"
DIGESTED = ("easy", "full", "deep")
ROW_STATUS = {SKIP, TODO, *DIGESTED}

_PAGES = re.compile(r"^\s*(\d+)\s*(?:[–—-]\s*(\d+))?\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Front/back matter: never a reading unit of its own.
_MATTER = re.compile(
    r"^(front matter|prefaces?|foreword|acknowledg\w*|(table of )?contents|"
    r"list of (notation|symbols|figures|tables)|notation|bibliography|references|"
    r"index|notes|about the authors?)\b", re.I)


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


def parse_partition(text):
    """Rows of the `## Partition` table: [{title, start, end, status, slug}], in table order.
    A row whose Pages cell is unreadable keeps start/end None so validation can report it."""
    rows = []
    for line in section(text, PARTITION_HEADING).split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if len(cells) < 4 or set(cells[0]) <= set("-: ") or cells[0] == "#":
            continue
        cells += [""] * (5 - len(cells))
        m = _PAGES.match(cells[2])
        start = int(m.group(1)) if m else None
        end = int(m.group(2) or m.group(1)) if m else None
        link = _first_link(cells[4]) or _first_link(cells[1])
        rows.append({"title": cells[1].replace("\\|", "|"), "start": start, "end": end,
                     "status": _status(cells[3]), "slug": link[0] if link else "", **({"link_text": link[1]} if link and link[1] and link[1] != link[0] else {})})
    return rows


def pages_of(row):
    return row["end"] - row["start"] + 1


def validate(rows, total, cap=PART_MAX_PAGES):
    """(errors, warnings) for a partition of pages 1..total."""
    errs, warns = [], []
    if not rows:
        return [f"{PARTITION_HEADING} has no rows"], warns
    bad = [r for r in rows if r["start"] is None]
    for r in bad:
        errs.append(f"partition row {r['title']!r}: unreadable Pages cell (use `A–B`)")
    rows = sorted((r for r in rows if r["start"] is not None), key=lambda r: r["start"])
    expect = 1
    for r in rows:
        label = f"p.{r['start']}–{r['end']} {r['title']!r}"
        if r["end"] < r["start"]:
            errs.append(f"partition row {label}: end before start")
            continue
        if r["start"] > expect:
            errs.append(f"partition gap: pages {expect}–{r['start'] - 1} belong to no part")
        elif r["start"] < expect:
            errs.append(f"partition overlap: {label} starts inside the previous part")
        expect = max(expect, r["end"] + 1)
        if r["status"] not in ROW_STATUS:
            errs.append(f"partition row {label}: status {r['status']!r} not in "
                        f"{sorted(ROW_STATUS)}")
        if r["status"] in DIGESTED and not r["slug"]:
            errs.append(f"partition row {label}: status {r['status']} needs a [[part-page]] link")
        if r["status"] != SKIP and pages_of(r) > cap:
            warns.append(f"partition row {label}: {pages_of(r)} pages, over the "
                         f"{cap}-page cap — consider splitting it")
    if total and expect - 1 != total:
        if expect - 1 < total:
            errs.append(f"partition gap: pages {expect}–{total} belong to no part")
        else:
            errs.append(f"partition runs to p.{expect - 1}, past book_pages: {total}")
    return errs, warns


def coverage(rows):
    """(digested pages, content pages). Skip rows count toward neither."""
    ok = [r for r in rows if r["start"] is not None]
    done = sum(pages_of(r) for r in ok if r["status"] in DIGESTED)
    content = sum(pages_of(r) for r in ok if r["status"] != SKIP)
    return done, content


def book_status(rows):
    done, content = coverage(rows)
    if content and done >= content:
        return "digested"
    return "reading" if done else "to-read"


def coverage_line(rows, cap=PART_MAX_PAGES):
    done, content = coverage(rows)
    pct = 100 * done // content if content else 0
    return (f"Coverage: **{done} / {content} pp ({pct}%)** · skip rows excluded · "
            f"parts ≤ {cap} pp")


def render(rows, cap=PART_MAX_PAGES):
    """Coverage line + table for the `## Partition` section body."""
    out = [coverage_line(rows, cap), "",
           "| # | Part | Pages | Status | Note |", "|---|------|-------|--------|------|"]
    for i, r in enumerate(sorted(rows, key=lambda r: r["start"]), 1):
        note = page_links.link(r["slug"], r.get("link_text") or r["slug"]) if r["slug"] else ""
        title = r["title"].replace("|", "\\|")
        out.append(f"| {i} | {title} | {r['start']}–{r['end']} | {r['status']} | {note} |")
    return "\n".join(out)


def replace_partition(text, rows, cap=PART_MAX_PAGES):
    """Rewrite the `## Partition` section of a book page in place."""
    body = render(rows, cap)
    if PARTITION_HEADING not in text:
        return text.rstrip() + f"\n\n{PARTITION_HEADING}\n\n{body}\n"
    head, rest = text.split(PARTITION_HEADING, 1)
    lines = rest.split("\n")
    tail = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), None)
    after = "\n".join(lines[tail:]) if tail is not None else ""
    return f"{head}{PARTITION_HEADING}\n\n{body}\n" + (f"\n{after}" if after else "")


def carve(rows, start, end, status, slug, title):
    """Make [start, end] exactly one row, trimming whatever undigested rows it cuts.
    Raises ValueError if the range cuts into an already digested row."""
    out = []
    for r in rows:
        if r["end"] < start or r["start"] > end:
            out.append(dict(r))
            continue
        if r["status"] in DIGESTED and (r["start"], r["end"]) != (start, end):
            raise ValueError(f"pages {start}–{end} cut into digested part "
                             f"p.{r['start']}–{r['end']} {r['slug']}")
        if r["start"] < start:
            out.append({**r, "end": start - 1})
        if r["end"] > end:
            out.append({**r, "start": end + 1})
    out.append({"title": title, "start": start, "end": end, "status": status, "slug": slug})
    return sorted(out, key=lambda r: r["start"])


def find_row(rows, start, end):
    for r in rows:
        if (r["start"], r["end"]) == (start, end):
            return r
    return None


# --------------------------------------------------------------------------
# proposing a partition from a PDF outline
# --------------------------------------------------------------------------
def _clean(title):
    """Outline titles from LaTeX PDFs can arrive as 'to 1.15Appendix ATechnical Lemmas'."""
    title = re.sub(r"^\s*to\s+[0-9.]+", "", title)
    title = re.sub(r"\b(Appendix|Chapter|Part)\s*([A-Z0-9]+?)(?=[A-Z][a-z])", r"\1 \2 ", title)
    return " ".join(title.split())


def _is_appendix(title):
    return _clean(title).lower().startswith("appendix")


def _is_matter(title):
    return bool(_MATTER.match(re.sub(r"^[0-9.\s]+", "", _clean(title))))


def _children(entries, i):
    """Direct children of entries[i] (outline entries one level deeper, inside its range)."""
    e = entries[i]
    kids = []
    for nxt in entries[i + 1:]:
        if nxt["level"] <= e["level"]:
            break
        if nxt["level"] == e["level"] + 1:
            kids.append(entries.index(nxt))
    return kids


def _rows_for(entries, i, start, end, cap):
    """Rows covering [start, end] for outline entry i, split at child boundaries if too long."""
    e = entries[i]
    title = _clean(e["title"])
    if _is_matter(title):
        return [{"title": title, "start": start, "end": end, "status": SKIP, "slug": ""}]
    kids = _children(entries, i)
    if end - start + 1 <= cap or not kids:
        return [{"title": title, "start": start, "end": end, "status": TODO, "slug": ""}]
    # child spans: the parent's lead-in pages go to the first child, gaps to the previous one
    spans = []
    for n, k in enumerate(kids):
        s = start if n == 0 else entries[k]["start"]
        f = (entries[kids[n + 1]]["start"] - 1) if n + 1 < len(kids) else end
        spans.append((k, s, max(s, f)))
    rows, group = [], []

    def flush():
        if not group:
            return
        names = [_clean(entries[k]["title"]) for k, _s, _f in group]
        label = names[0] if len(names) == 1 else f"{names[0]} → {names[-1]}"
        rows.append({"title": f"{title}: {label}", "start": group[0][1], "end": group[-1][2],
                     "status": TODO, "slug": ""})
        group.clear()

    for k, s, f in spans:
        if _is_matter(entries[k]["title"]):
            flush()
            rows.append({"title": _clean(entries[k]["title"]), "start": s, "end": f,
                         "status": SKIP, "slug": ""})
            continue
        if f - s + 1 > cap and _children(entries, k):
            flush()
            rows += _rows_for(entries, k, s, f, cap)
            continue
        if group and (f - group[0][1] + 1 > cap
                      or _is_appendix(entries[k]["title"]) != _is_appendix(entries[group[-1][0]]["title"])):
            flush()
        group.append((k, s, f))
    flush()
    return rows


def _merge_skips(rows):
    out = []
    for r in rows:
        if out and r["status"] == SKIP and out[-1]["status"] == SKIP:
            out[-1] = {**out[-1], "end": r["end"], "title": f"{out[-1]['title']} · {r['title']}"}
        else:
            out.append(r)
    return out


def propose(entries, total, cap=PART_MAX_PAGES):
    """A disjoint, exhaustive partition of 1..total from outline entries (src/kb_distillery/ingest/book.py
    `read_toc` shape). Splits only at outline boundaries; front/back matter becomes skip rows."""
    if not total:
        return []
    if not entries:
        return [{"title": "Whole book", "start": 1, "end": total, "status": TODO, "slug": ""}]
    top = min(e["level"] for e in entries)
    tops = [i for i, e in enumerate(entries) if e["level"] == top]
    rows = []
    first = entries[tops[0]]["start"]
    if first > 1:
        rows.append({"title": "Front matter", "start": 1, "end": first - 1,
                     "status": SKIP, "slug": ""})
    for n, i in enumerate(tops):
        s = entries[i]["start"]
        f = (entries[tops[n + 1]]["start"] - 1) if n + 1 < len(tops) else total
        if f < s:
            continue
        rows += _rows_for(entries, i, s, f, cap)
    return _merge_skips(rows)

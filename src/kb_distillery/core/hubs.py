"""Course and series hub pages and their contents table. Pure functions, no third-party deps.

A course (or series) is one `type: course` page. Its `## Contents` table lists every raw file
that belongs to it — the same set as the corpus.tsv rows whose `collection` names the hub.
A row is one reading unit: usually one file, sometimes several (a lecture's slides and the
handwritten notes taken in it). Digested rows link the unit's page; undigested rows are rows,
not pages. A row's identity is its raw paths — the `#` column is display order only.

    | # | Item | Raw | Status | Note |
    |---|------|-----|--------|------|
    | 1 | Lecture 1 · Introduction | `raw/presentations/rl-lecture-01-introduction.pdf` | full | [Lecture 1](lecture-….md) |
    | 2 | Lecture 2 · MDPs | `raw/presentations/rl-02.pdf` `raw/handwritten/rl-mdp.pdf` | — | |
    | 3 | Course book | `raw/printed-docs/la-course-book.pdf` | partial | [Course book](book-….md) |

Page-range hubs (book, notebook) live in books.py; this module is their sibling.
"""
import re

from kb_distillery.core.books import DIGESTED, SKIP, TODO, section
from kb_distillery.core import links as page_links

CONTENTS_HEADING = "## Contents"
PARTIAL = "partial"          # the row is itself a book/notebook hub, digested only in part
ROW_STATUS = {SKIP, TODO, PARTIAL, *DIGESTED}

_PATH = re.compile(r"`(raw/[^`]+)`")


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


def parse_contents(text):
    """Rows of the `## Contents` table: [{title, raws, status, slug}], in table order."""
    rows = []
    for line in section(text, CONTENTS_HEADING).split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if len(cells) < 4 or set(cells[0]) <= set("-: ") or cells[0] == "#":
            continue
        cells += [""] * (5 - len(cells))
        link = _first_link(cells[4]) or _first_link(cells[1])
        rows.append({"title": cells[1].replace("\\|", "|"), "raws": _PATH.findall(cells[2]),
                     "status": _status(cells[3]), "slug": link[0] if link else "", **({"link_text": link[1]} if link and link[1] and link[1] != link[0] else {})})
    return rows


def validate(rows, members, hub):
    """(errors, warnings) for a contents table against the corpus rows that name this hub.
    `members` = set of raw paths whose `collection` includes `hub`."""
    errs, warns = [], []
    seen = {}
    for r in rows:
        label = repr(r["title"])
        if not r["raws"]:
            errs.append(f"contents row {label}: no `raw/…` path in the Raw cell")
        if r["status"] not in ROW_STATUS:
            errs.append(f"contents row {label}: status {r['status']!r} not in {sorted(ROW_STATUS)}")
        if (r["status"] in DIGESTED or r["status"] == PARTIAL) and not r["slug"]:
            errs.append(f"contents row {label}: status {r['status']} needs a [[page]] link")
        for p in r["raws"]:
            if p in seen:
                errs.append(f"`{p}` is listed twice (rows {seen[p]!r} and {r['title']!r})")
            seen[p] = r["title"]
            if p not in members:
                errs.append(f"`{p}` is in the table but its corpus.tsv `collection` "
                            f"does not name {hub}")
    for p in sorted(members - set(seen)):
        errs.append(f"`{p}` names {hub} in corpus.tsv `collection` but has no contents row")
    return errs, warns


def coverage(rows):
    """(digested rows, content rows). Skip rows count toward neither."""
    done = sum(1 for r in rows if r["status"] in DIGESTED)
    content = sum(1 for r in rows if r["status"] != SKIP)
    return done, content


def hub_status(rows):
    done, content = coverage(rows)
    if content and done >= content:
        return "digested"
    return "reading" if done else "to-read"


def coverage_line(rows):
    done, content = coverage(rows)
    pct = 100 * done // content if content else 0
    return f"Coverage: **{done} / {content} items ({pct}%)** · skip rows excluded"


def row_status_by_path(rows):
    """raw path → row status, for reconcile: the table, not a stale disposition, is the truth."""
    return {p: r["status"] for r in rows for p in r["raws"]}


def render(rows):
    """Coverage line + table for the `## Contents` section body."""
    out = [coverage_line(rows), "",
           "| # | Item | Raw | Status | Note |", "|---|------|-----|--------|------|"]
    for i, r in enumerate(rows, 1):
        note = page_links.link(r["slug"], r.get("link_text") or r["slug"]) if r["slug"] else ""
        title = r["title"].replace("|", "\\|")
        raws = " ".join(f"`{p}`" for p in r["raws"])
        out.append(f"| {i} | {title} | {raws} | {r['status']} | {note} |")
    return "\n".join(out)


def replace_contents(text, rows):
    """Rewrite the `## Contents` section of a hub page in place (append it if missing)."""
    body = render(rows)
    if CONTENTS_HEADING not in text:
        return text.rstrip() + f"\n\n{CONTENTS_HEADING}\n\n{body}\n"
    head, rest = text.split(CONTENTS_HEADING, 1)
    lines = rest.split("\n")
    tail = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("## ")), None)
    after = "\n".join(lines[tail:]) if tail is not None else ""
    return f"{head}{CONTENTS_HEADING}\n\n{body}\n" + (f"\n{after}" if after else "")


def find_row(rows, raw_rel):
    for i, r in enumerate(rows):
        if raw_rel in r["raws"]:
            return i, r
    return None, None


def add_row(rows, title, raws, status=TODO, slug=""):
    """Append a row for new member files (catalog); no-op for paths already listed."""
    new = [p for p in raws if find_row(rows, p)[1] is None]
    if not new:
        return rows
    return rows + [{"title": title, "raws": new, "status": status, "slug": slug}]


def tick(rows, index, status, slug, label=None):
    """Mark row `index` (0-based) digested as page `slug` (`label` = the link text, default the slug). Refuses to re-digest a finished row."""
    r = rows[index]
    if r["status"] in DIGESTED and r["slug"] and r["slug"] != slug:
        raise ValueError(f"row {index + 1} ({r['title']}) is already digested as {r['slug']}")
    out = [dict(x) for x in rows]
    text = label or (out[index].get("link_text") if out[index].get("slug") == slug else "")
    out[index].pop("link_text", None)
    out[index].update(status=status, slug=slug, **({"link_text": text} if text else {}))
    return out

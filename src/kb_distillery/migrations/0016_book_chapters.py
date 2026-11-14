"""Book chapters (schema 1.6): a book's `## Partition` table becomes a `## Chapters` table with fixed ids.

For every `type: book` / `type: notebook` page that still has `## Partition` and no `## Chapters`, every row is kept
with its page range; only the ids are new:
  * a row whose title names a chapter gets its id: `Chapter 3 …` → ch3, `Appendix A …` → appA (an "A → B" row
    takes A's id); several rows of one chapter become a lettered split ch3a, ch3b … in book order (more than 26
    rows of one chapter: all of them become sec<N> instead);
  * a row with no chapter number (`Pages 19–42`, `Part II`, `Introduction`, a notebook date) is `sec1`, `sec2` …
    in book order;
  * skip rows before the first reading row are `front`, after the last one `back` (adjacent ones of a kind are
    joined); a skip row between chapters keeps its own row as sec<N> with status skip;
  * the one merge: an end-of-chapter row (exercises / notes / problems) joins the row of its chapter right before
    it when neither is digested.
Every join and every sec<N> id is listed in the report, one line each (`NOTE 0016 …`). Note-column text that is not
a link is kept, prose under the heading is kept, the Coverage line is regenerated, `maturity:` follows the
chapters and `outline_chapters:` records the chapter count. A row with an unreadable Pages cell leaves its book
alone; the report names the book page and the row (`ops migrate` shows it).
Every part page linked from a row gets `chapter: <id>`. A part page whose slug does not carry its (lower-cased) id
after the book stem is renamed to `part-<stem>-<id>-<rest>`; its old slug goes into `aliases:` and every link to it
in wiki/ is rewritten outside `## My notes`, so nothing breaks (My notes and think/ are user-owned: their links
stay, aliases resolve them; think/ hits are reported).
Idempotent: a book with `## Chapters` and a part with `chapter:` are skipped. Run directly (`__main__`) it has no
rollback of its own: book pages are written first, then part pages, then renames and relinks; `ops migrate`
snapshots the kb and restores it on any failure.

    python src/kb_distillery/migrations/0016_book_chapters.py [--root R] [--dry-run]
"""
import argparse
import os
import re

from kb_distillery.vault import books, links, wikiio

PRODUCES = (1, 6)
OLD_HEADING = "## Partition"
_PAGES = re.compile(r"^\s*(\d+)\s*(?:[–—-]\s*(\d+))?\s*$")


# -- the pre-1.6 table, read here so this migration never depends on a parser that may go away --------------------
def _old_rows(text):
    rows = []
    for line in books.section(text, OLD_HEADING).split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if len(cells) < 4 or set(cells[0]) <= set("-: ") or cells[0] == "#":
            continue
        cells += [""] * max(0, 5 - len(cells))
        m = _PAGES.match(cells[2])
        st = cells[3].strip().strip("*`").lower()
        link = None
        for cell in (cells[4], cells[1]):
            pm = links.PAGE_LINK.search(cell)
            if pm:
                label, slug, _a = links.link_parts(pm)
                link = (slug, label)
                break
            w = links.WIKILINK.search(cell)
            if w:
                link = (w.group(1).strip(), (w.group(2) or "").strip())
                break
        row = {"id": "", "title": cells[1].replace("\\|", "|"),
               "start": int(m.group(1)) if m else None, "end": int(m.group(2) or m.group(1)) if m else None,
               "status": books.TODO if st in ("", "-", "—", "–") else st, "slug": link[0] if link else ""}
        if link and link[1] and link[1] != link[0]:
            row["link_text"] = link[1]
        note = books._note_text(cells[4]) if len(cells) > 4 else ""
        extra = [c for c in cells[5:] if c]
        if extra:                                   # columns past Note: carried into the note, and reported
            row["extra"] = extra
            note = " ".join([note] + extra).strip()
        if note:
            row["note"] = note
        rows.append(row)
    return rows


def _fm(text, key):
    m = re.search(rf"^{key}:\s*(.*)$", text.split("\n---", 1)[0], re.M)
    return m.group(1).strip() if m else ""


_FOLD = re.compile(r"(?i)\b(exercises?|problems?|notes)\b")


def _fold_row(title):
    """An end-of-chapter row: 'Chapter 11. X: 11.8 Exercises and notes'."""
    tail = title.split(": ", 1)[1] if ": " in title else title
    return bool(_FOLD.search(tail)) and not books.chapter_id(tail)


class Unreadable(ValueError):
    pass


def assign_ids(rows, notes=None):
    """Rows with ids per the module rules; every join and sec<N> id is appended to `notes`.
    Raises Unreadable (naming the row) when a Pages cell cannot be read."""
    notes = notes if notes is not None else []
    rows = [dict(r) for r in rows]
    for n, r in enumerate(rows, 1):
        if r["start"] is None:
            raise Unreadable(f"row {n} {r['title']!r}: unreadable Pages cell (use A–B)")
    rows.sort(key=lambda r: r["start"])
    content = [i for i, r in enumerate(rows) if r["status"] != books.SKIP]
    first = content[0] if content else len(rows)
    last = content[-1] if content else -1
    out = []                                         # rows with "kind": front/back/sec or a chapter base id
    for i, r in enumerate(rows):
        pages = f"p.{r['start']}–{r['end']}"
        if r["status"] == books.SKIP and (i < first or i > last):
            kind = books.FRONT if i < first else books.BACK
            if out and out[-1]["kind"] == kind:
                notes.append(f"joined skip row {r['title']!r} ({pages}) into {kind}")
                out[-1].update(end=r["end"], title=f"{out[-1]['title']} · {r['title']}")
                continue
            out.append({**r, "kind": kind})
            continue
        if r["status"] == books.SKIP:
            out.append({**r, "kind": "sec"})
            continue
        base = books.chapter_id(re.split(r"\s+→\s+", r["title"])[0])
        prev = out[-1] if out else None
        if (base and prev and prev["kind"] == base and _fold_row(r["title"])
                and r["status"] not in books.DIGESTED and prev["status"] not in books.DIGESTED
               ):
            notes.append(f"joined {r['title']!r} ({pages}) into its chapter {base} (neither digested)")
            prev["end"] = r["end"]
            if re.match(r"(?i)^(chapter|appendix)\b", prev["title"]):
                prev["title"] = prev["title"].split(": ")[0]
            continue
        out.append({**r, "kind": base or "sec"})
    groups = {}
    for r in out:
        if r["kind"] not in (books.FRONT, books.BACK, "sec"):
            groups.setdefault(r["kind"], []).append(r)
    for base, rs in groups.items():
        if len(rs) == 1:
            rs[0]["id"] = base
        elif len(rs) <= 26:
            for k, r in enumerate(rs):
                r["id"] = base + "abcdefghijklmnopqrstuvwxyz"[k]
            notes.append(f"{base} spans {len(rs)} rows: kept as a split {rs[0]['id']}…{rs[-1]['id']}")
        else:
            for r in rs:
                r["kind"] = "sec"
            notes.append(f"{base} spans {len(rs)} rows, more than 26 letters: they get sec<N> ids")
    n = 0
    for r in out:
        if r["kind"] in (books.FRONT, books.BACK):
            r["id"] = r["kind"]
        elif r["kind"] == "sec":
            n += 1
            r["id"] = f"sec{n}"
            notes.append(f"row {r['title']!r} (p.{r['start']}–{r['end']}"
                         + (", skip" if r["status"] == books.SKIP else "") + f") has no chapter number: id sec{n}")
        r.pop("kind", None)
    return out


def _add_alias(head, old):
    m = re.search(r"^aliases: \[(.*)\]$", head, re.M)
    if m:
        items = [a.strip() for a in m.group(1).split(",") if a.strip()]
        if old in items:
            return head
        return head[:m.start()] + f"aliases: [{', '.join(items + [old])}]" + head[m.end():]
    block = re.search(r"^aliases:\s*\n((?:\s*- .*\n?)*)", head, re.M)
    if block and block.group(1).strip():
        if re.search(rf"^\s*- {re.escape(old)}\s*$", block.group(1), re.M):
            return head
        return head[:block.end(1)].rstrip("\n") + f"\n  - {old}" + ("\n" + head[block.end(1):] if head[block.end(1):] else "")
    if re.search(r"^aliases:", head, re.M):
        return re.sub(r"^aliases:.*$", f"aliases: [{old}]", head, count=1, flags=re.M)
    return head + f"\naliases: [{old}]"


def _set_chapter(text, cid):
    head, sep, body = text.partition("\n---\n")
    if re.search(r"^chapter:", head, re.M):
        head = re.sub(r"^chapter:.*$", f"chapter: {cid}", head, count=1, flags=re.M)
    elif re.search(r"^book:.*$", head, re.M):
        head = re.sub(r"^(book:.*)$", rf"\1\nchapter: {cid}", head, count=1, flags=re.M)
    else:
        head += f"\nchapter: {cid}"
    return head + sep + body


def _relink(text, mapping):
    """`[x](old.md)`, `[x](old.md#h)`, `[[old…]]` and `old.md` in `related:` → the new slug."""
    for old, new in mapping.items():
        text = re.sub(rf"\]\({re.escape(old)}\.md([)#])", rf"]({new}.md\1", text)
        text = re.sub(rf"\[\[{re.escape(old)}(?=[\]|#\\])", f"[[{new}", text)
        text = re.sub(rf"(^related:.*?)(?<![\w-]){re.escape(old)}\.md", rf"\1{new}.md", text, flags=re.M)
    return text


def _read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _write(p, text):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _note(report, rel, line):
    report["notes"].append(f"{rel}: {line}")


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    report = {"books": 0, "parts": 0, "renamed": {}, "skipped": {}, "relinked": 0, "think": [], "notes": []}
    if not os.path.isdir(wiki):
        return report
    pages = {fn[:-3]: os.path.join(wiki, fn) for fn in sorted(os.listdir(wiki)) if fn.endswith(".md")}
    book_texts, part_texts = {}, {}
    for slug, path in pages.items():
        text = _read(path)
        if _fm(text, "type") not in ("book", "notebook"):
            continue
        if books.CHAPTERS_HEADING in text or OLD_HEADING not in text:
            continue
        rel = f"wiki/{slug}.md"
        old = _old_rows(text)
        notes = []
        try:
            rows = assign_ids(old, notes)
        except Unreadable as e:
            report["skipped"][slug] = f"{rel} left on {OLD_HEADING}: {e} — fix that row, then migrate again"
            continue
        for line in notes:
            _note(report, rel, line)
        for r in old:
            if r.get("extra"):
                _note(report, rel, f"row {r['title']!r} had extra columns {r['extra']}: kept in its Note cell")
        stem = "part-" + re.sub(r"^(book|notebook)-", "", slug) + "-"
        for r in rows:
            r.pop("extra", None)
            if not r["slug"] or r["slug"] not in pages:
                continue
            ptext = part_texts.get(r["slug"]) or _read(pages[r["slug"]])
            part_texts[r["slug"]] = _set_chapter(ptext, r["id"])
            report["parts"] += 1
            old_slug, cid = r["slug"], r["id"].lower()
            if old_slug == stem + cid or old_slug.startswith(f"{stem}{cid}-") or not old_slug.startswith(stem):
                continue
            rest = re.sub(r"^(?:ch\d+[a-z]?|app[a-z]\d*[a-z]?|sec\d+)-", "", old_slug[len(stem):])
            new = f"{stem}{cid}-{rest}"
            if new.lower() in {p.lower() for p in pages} or new in report["renamed"].values():
                report["skipped"][old_slug] = f"cannot rename to {new}: it exists"
                continue
            report["renamed"][old_slug] = new
            r["slug"] = new
        n = len(books.content_ids(rows))
        new_text = books.replace_chapters(text, rows)
        head, sep, body = new_text.partition("\n---\n")
        if not re.search(r"^outline_chapters:", head, re.M):
            head = re.sub(r"^(book_pages:.*)$", rf"\1\noutline_chapters: {n}", head, count=1, flags=re.M)
        head = re.sub(r"^maturity:.*$", f"maturity: {books.book_status(rows)}", head, count=1, flags=re.M)
        book_texts[slug] = head + sep + body
        report["books"] += 1
    if dry_run:
        report["dry_run"] = True
        return report
    mapping = report["renamed"]
    for slug, text in book_texts.items():            # book pages first, then the parts they link
        _write(pages[slug], text)
    for slug, text in part_texts.items():
        if slug not in mapping:
            _write(pages[slug], text)
            continue
        head, sep, body = text.partition("\n---\n")
        old_path, new_path = pages[slug], os.path.join(wiki, mapping[slug] + ".md")
        _write(old_path, _add_alias(head, slug) + sep + body)
        if os.path.exists(new_path) and os.path.samefile(old_path, new_path):
            tmp = old_path + ".0016-rename"            # a case-only rename on a case-insensitive filesystem
            os.rename(old_path, tmp)
            os.rename(tmp, new_path)
        else:
            os.rename(old_path, new_path)
    if mapping:
        for fn in sorted(os.listdir(wiki)):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(wiki, fn)
            text = _read(p)
            # ## My notes is the user's and never rewritten (its old-slug links resolve through aliases:)
            new = wikiio.preserve_my_notes(text, _relink(wikiio.strip_my_notes(text), mapping)) \
                if wikiio.my_notes(text) else _relink(text, mapping)
            if new != text:
                _write(p, new)
                report["relinked"] += 1
        think = os.path.join(root, "think")
        for d, _s, files in os.walk(think) if os.path.isdir(think) else []:
            for fn in files:
                if fn.endswith(".md") and any(o in _read(os.path.join(d, fn)) for o in mapping):
                    report["think"].append(os.path.relpath(os.path.join(d, fn), root))
    for line in report["notes"]:
        print(f"NOTE 0016 {line}")
    for why in report["skipped"].values():
        print(f"NOTE 0016 {why}")
    print(f"book chapters: {report['books']} books, {report['parts']} part pages, "
          f"{len(mapping)} renamed (old slugs kept as aliases), {report['relinked']} pages relinked"
          + (f"; think/ still links old slugs (aliases resolve them): {report['think']}" if report["think"] else ""))
    return report


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(apply(a.root, dry_run=a.dry_run))

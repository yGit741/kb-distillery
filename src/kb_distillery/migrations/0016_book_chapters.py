"""Book chapters (schema 1.6): a book's `## Partition` table becomes a `## Chapters` table with fixed ids.

For every `type: book` / `type: notebook` page that still has `## Partition` and no `## Chapters`:
  * each row gets an id from its title: `Chapter 3 …` → ch3, `Appendix A …` → appA, a skip row before the
    first chapter → front, after the last one → back;
  * two rows of one chapter (a chapter and its separate exercises row) merge into one row when neither is
    digested; otherwise they become a lettered split (ch11a, ch11b);
  * an unnumbered reading row ("Some tips") joins the row before it when neither is digested, else it is a
    lettered split of that chapter; one before any chapter is ch0; a merged row "Chapter 3 → Chapter 4"
    keeps the first chapter's id;
  * the table is rewritten as `| Id | Chapter | Pages | Status | Note |` and `outline_chapters:` records
    its chapter count.
Every part page linked from a row gets `chapter: <id>`. A part page whose slug does not carry its id after the
book stem is renamed to `part-<stem>-<id>-<rest>`; its old slug goes into `aliases:` and every link to it in
wiki/ is rewritten, so nothing breaks (think/ is user-owned: links there are reported, aliases resolve them).
A book whose table cannot be read (a skip row between chapters, an unreadable Pages cell) is left alone and
reported; lint then points at it. Idempotent: a book with `## Chapters` and a part with `chapter:` are skipped.

    python src/kb_distillery/migrations/0016_book_chapters.py [--root R] [--dry-run]
"""
import argparse
import os
import re

from kb_distillery.vault import books, links

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
        cells += [""] * (5 - len(cells))
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
        rows.append(row)
    return rows


def _fm(text, key):
    m = re.search(rf"^{key}:\s*(.*)$", text.split("\n---", 1)[0], re.M)
    return m.group(1).strip() if m else ""


def assign_ids(rows):
    """Rows with ids, merged/split per the module rules. Raises ValueError when the table is unreadable."""
    rows = sorted((dict(r) for r in rows), key=lambda r: r["start"] if r["start"] is not None else -1)
    if any(r["start"] is None for r in rows):
        raise ValueError("a row has an unreadable Pages cell")
    content = [i for i, r in enumerate(rows) if r["status"] != books.SKIP]
    if not content:
        raise ValueError("no reading rows")
    first, last = content[0], content[-1]
    out = []
    for i, r in enumerate(rows):
        digested = r["status"] in books.DIGESTED
        if r["status"] == books.SKIP:
            if first < i < last:
                raise ValueError(f"skip row {r['title']!r} sits between chapters")
            r["id"] = books.FRONT if i < first else books.BACK
            if out and out[-1]["id"] == r["id"]:
                out[-1].update(end=r["end"], title=f"{out[-1]['title']} · {r['title']}")
            else:
                out.append(r)
            continue
        cid = books.chapter_id(re.split(r"\s+→\s+", r["title"])[0])
        prev = out[-1] if out and out[-1]["status"] != books.SKIP else None
        if not cid:
            if prev is None:
                cid = "ch0"
            else:
                cid = books.base_id(prev["id"])
        if prev and books.base_id(prev["id"]) == cid:
            split = bool(re.fullmatch(r"[a-z]", prev["id"][len(cid):]))
            if not digested and prev["status"] not in books.DIGESTED and not split:
                prev["end"] = r["end"]                       # one chapter again: merge
                continue
            if not split:
                prev["id"] = cid + "a"
            letter = chr(ord(prev["id"][-1]) + 1)
            r["id"] = cid + letter
        else:
            r["id"] = cid
        out.append(r)
    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"two rows resolve to one id: {sorted({i for i in ids if ids.count(i) > 1})}")
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


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    if not os.path.isdir(wiki):
        return {"books": 0}
    pages = {fn[:-3]: os.path.join(wiki, fn) for fn in sorted(os.listdir(wiki)) if fn.endswith(".md")}
    report = {"books": 0, "parts": 0, "renamed": {}, "skipped": {}, "relinked": 0, "think": []}
    texts = {}
    for slug, path in pages.items():
        text = _read(path)
        if _fm(text, "type") not in ("book", "notebook"):
            continue
        if books.CHAPTERS_HEADING in text or OLD_HEADING not in text:
            continue
        try:
            rows = assign_ids(_old_rows(text))
        except ValueError as e:
            report["skipped"][slug] = str(e)
            continue
        stem = "part-" + re.sub(r"^(book|notebook)-", "", slug) + "-"
        for r in rows:
            if not r["slug"] or r["slug"] not in pages:
                continue
            ptext = texts.get(r["slug"]) or _read(pages[r["slug"]])
            texts[r["slug"]] = _set_chapter(ptext, r["id"])
            report["parts"] += 1
            old = r["slug"]
            if old == stem + r["id"] or old.startswith(f"{stem}{r['id']}-") or not old.startswith(stem):
                continue
            rest = re.sub(r"^ch\d+[a-z]?-", "", old[len(stem):])
            new = f"{stem}{r['id']}-{rest}"
            if new in pages or new in report["renamed"].values():
                report["skipped"][old] = f"cannot rename to {new}: it exists"
                continue
            report["renamed"][old] = new
            r["slug"] = new
        n = len(books.content_ids(rows))
        new_text = books.replace_chapters(text, rows)
        head, sep, body = new_text.partition("\n---\n")
        if not re.search(r"^outline_chapters:", head, re.M):
            head = re.sub(r"^(book_pages:.*)$", rf"\1\noutline_chapters: {n}", head, count=1, flags=re.M)
        texts[slug] = head + sep + body
        report["books"] += 1
    if dry_run:
        report["dry_run"] = True
        return report
    mapping = report["renamed"]
    for slug, text in texts.items():
        if slug in mapping:
            head, sep, body = text.partition("\n---\n")
            text = _add_alias(head, slug) + sep + body
            _write(os.path.join(wiki, mapping[slug] + ".md"), text)
            os.remove(pages[slug])
        else:
            _write(pages[slug], text)
    if mapping:
        for fn in sorted(os.listdir(wiki)):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(wiki, fn)
            text = _read(p)
            new = _relink(text, mapping)
            if new != text:
                _write(p, new)
                report["relinked"] += 1
        think = os.path.join(root, "think")
        for d, _s, files in os.walk(think) if os.path.isdir(think) else []:
            for fn in files:
                if fn.endswith(".md") and any(o in _read(os.path.join(d, fn)) for o in mapping):
                    report["think"].append(os.path.relpath(os.path.join(d, fn), root))
    print(f"book chapters: {report['books']} books, {report['parts']} part pages, "
          f"{len(mapping)} renamed (old slugs kept as aliases), {report['relinked']} pages relinked"
          + (f"; left alone: {report['skipped']}" if report["skipped"] else "")
          + (f"; think/ still links old slugs (aliases resolve them): {report['think']}" if report["think"] else ""))
    return report


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(apply(a.root, dry_run=a.dry_run))

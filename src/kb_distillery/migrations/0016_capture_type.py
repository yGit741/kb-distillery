"""Capture (schema 1.6): the owner's own thoughts get a source type of their own.

A capture is a thought the owner wrote or said (a reMarkable page, a photo of paper, a screenshot), stored as its
original under raw/images/ with a text extraction on the page below it (`thought-ingest` skill). Before 1.6 such a page
could only be an `article`. Every `type: article` page whose frontmatter says `author: me` becomes `type: capture`,
renamed `article-<stem>` → `capture-<stem>` (a stem already starting with `capture-` is not repeated); the old slug is
kept in `aliases:` and every `old.md` link in wiki/ (bodies, `related:`, `sources:`) and the slug column of
meta/corpus.tsv are rewritten. A kb.toml `[types] order` list gets "capture" appended (the list must name every
type). think/ is user-owned and never rewritten. Idempotent.

    python src/kb_distillery/migrations/0016_capture_type.py [--root R] [--dry-run]
"""
import argparse
import os
import re

PRODUCES = (1, 6)
OLD_PREFIX = "article-"
NEW_PREFIX = "capture-"


def _head(text):
    """The frontmatter block (between the opening `---` and the next `---` line), CRLF tolerated."""
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    return m.group(1) if m else ""


def _fm_get(text, key):
    m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*\r?$", _head(text), re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _is_me(value):
    return value.strip("[]").strip().strip("\"'").lower() == "me"


def _new_slug(old):
    stem = old[len(OLD_PREFIX):]
    return stem if stem.startswith(NEW_PREFIX) else NEW_PREFIX + stem


def plan(root):
    """{old_slug: new_slug}: every wiki/article-*.md typed article with `author: me`, plus every capture page an
    interrupted earlier run already wrote (its `aliases:` names an `article-*` slug), so a rerun still relinks."""
    wiki = os.path.join(root, "wiki")
    out = {}
    for fn in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(wiki, fn), encoding="utf-8") as f:
            text = f.read()
        if fn.startswith(NEW_PREFIX) and _fm_get(text, "type") == "capture":
            for alias in re.findall(r"article-[\w-]+", _fm_get(text, "aliases")):
                if _new_slug(alias) == fn[:-3]:
                    out[alias] = fn[:-3]
            continue
        if not fn.startswith(OLD_PREFIX) or _fm_get(text, "type") != "article" or not _is_me(_fm_get(text, "author")):
            continue
        old, new = fn[:-3], _new_slug(fn[:-3])
        if new in out.values():
            raise RuntimeError(f"refusing to migrate: two pages would become wiki/{new}.md")
        if os.path.exists(os.path.join(wiki, new + ".md")) and not _already(wiki, new, old):
            raise RuntimeError(f"refusing to migrate: wiki/{new}.md already exists")
        out[old] = new
    return out


def _already(wiki, new, old):
    """wiki/<new>.md is this page, written by an interrupted run (a capture whose aliases name `old`)."""
    with open(os.path.join(wiki, new + ".md"), encoding="utf-8") as f:
        text = f.read()
    return _fm_get(text, "type") == "capture" and old in _fm_get(text, "aliases")


def _retype(text, old):
    head = _head(text)
    if not head:
        raise RuntimeError(f"refusing to migrate {old}: no frontmatter block")
    new_head, n = re.subn(r"^type:[ \t]*[\"']?article[\"']?[ \t]*(\r?)$", r"type: capture\1", head, count=1, flags=re.M)
    if not n:
        raise RuntimeError(f"refusing to migrate {old}: cannot find its `type: article` line")
    m = re.search(r"^aliases:[ \t]*\[(.*)\][ \t]*(\r?)$", new_head, re.M)
    block = re.search(r"^aliases:[ \t]*\r?\n((?:[ \t]+- .*\r?\n?)+)", new_head + "\n", re.M)
    if m:
        items = [a.strip() for a in m.group(1).split(",") if a.strip()]
        if old not in items:
            new_head = new_head[:m.start()] + f"aliases: [{', '.join(items + [old])}]{m.group(2)}" + new_head[m.end():]
    elif block:
        if not re.search(rf"^[ \t]+- {re.escape(old)}\s*$", block.group(1), re.M):
            new_head = new_head.rstrip("\n") if block.end(1) >= len(new_head) else new_head
            new_head = new_head[:block.end(1)].rstrip("\r\n") + f"\n  - {old}" + new_head[block.end(1):]
    elif re.search(r"^aliases:", new_head, re.M):
        raise RuntimeError(f"refusing to migrate {old}: unreadable `aliases:`")
    else:
        new_head += f"\naliases: [{old}]"
    i = text.index(head)
    return text[:i] + new_head + text[i + len(head):]


def _relink(text, mapping):
    """`old.md` (markdown links, `related:`, `sources:`) and `[[old]]` wikilinks (My notes) → the new slug."""
    for old, new in mapping.items():
        text = re.sub(rf"(?<![\w-]){re.escape(old)}\.md(?![\w-])", new + ".md", text)
        text = re.sub(rf"\[\[{re.escape(old)}(?=[\]|#])", "[[" + new, text)
    return text


def _corpus(root, mapping):
    path = os.path.join(root, "meta", "corpus.tsv")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    n = 0
    for i, line in enumerate(lines):
        if line.startswith("#") or "\t" not in line:
            continue
        cols = line.split("\t")
        if len(cols) > 4 and cols[4] in mapping:
            cols[4] = mapping[cols[4]]
            lines[i] = "\t".join(cols)
            n += 1
    if n:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
    return n


ORDER = re.compile(r"^(order\s*=\s*\[)([^\]]*)(\])", re.M)


def _order(root, dry_run=False):
    """A kb.toml `[types] order = [...]` must list every type: append "capture" when it is missing."""
    path = os.path.join(root, "kb.toml")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    sec = re.search(r"^\[types\]\s*$", text, re.M)
    if not sec:
        return False
    nxt = re.search(r"^\[(?!types[.\]])", text[sec.end():], re.M)
    m = ORDER.search(text, sec.end(), sec.end() + nxt.start() if nxt else len(text))
    if not m or re.search(r"[\"']capture[\"']", m.group(2)):
        return False
    if not dry_run:
        items = list(re.finditer(r"[\"'][^\"']*[\"']", m.group(2)))
        at = m.start(2) + (items[-1].end() if items else 0)
        text = text[:at] + (', "capture"' if items else '"capture"') + text[at:]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return True


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    mapping = plan(root)                       # raises before anything is written
    if dry_run:
        for o, n in mapping.items():
            print(f"{o} → {n} (capture)")
        print("capture type: [types] order " + ("needs capture" if _order(root, dry_run=True) else "is fine"))
        return {"renamed": len(mapping), "dry_run": True}
    todo = {o: n for o, n in mapping.items() if os.path.exists(os.path.join(wiki, o + ".md"))}
    for old, new in todo.items():             # 1. write every new page (old ones stay until the end)
        with open(os.path.join(wiki, old + ".md"), encoding="utf-8", newline="") as f:
            text = f.read()
        dest = os.path.join(wiki, new + ".md")
        if not os.path.exists(dest):
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(_retype(text, old))
    touched = 0
    for fn in sorted(os.listdir(wiki)):       # 2. relink
        if not fn.endswith(".md") or fn[:-3] in todo:
            continue
        p = os.path.join(wiki, fn)
        with open(p, encoding="utf-8", newline="") as f:
            text = f.read()
        new = _relink(text, mapping)
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            touched += 1
    rows = _corpus(root, mapping)             # 3. corpus slugs
    ordered = _order(root)                    # 4. kb.toml [types] order
    for old in todo:                          # 5. only now drop the old files
        os.remove(os.path.join(wiki, old + ".md"))
    if not mapping and not ordered:
        print("capture type: nothing to change")
        return {"renamed": 0, "order": False}
    print(f"capture type: {len(todo)} pages renamed, {touched} pages relinked, {rows} corpus rows"
          + (", capture added to [types] order" if ordered else ""))
    return {"renamed": len(todo), "relinked": touched, "corpus": rows, "order": ordered}


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.root, dry_run=a.dry_run)

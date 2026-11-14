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


def _fm_get(text, key):
    m = re.search(rf"^{key}:\s*(.*)$", text.split("\n---", 1)[0], re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _new_slug(old):
    stem = old[len(OLD_PREFIX):]
    return stem if stem.startswith(NEW_PREFIX) else NEW_PREFIX + stem


def plan(root):
    """{old_slug: new_slug} for every wiki/article-*.md typed article with `author: me`."""
    wiki = os.path.join(root, "wiki")
    out = {}
    for fn in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not (fn.endswith(".md") and fn.startswith(OLD_PREFIX)):
            continue
        with open(os.path.join(wiki, fn), encoding="utf-8") as f:
            text = f.read()
        if _fm_get(text, "type") != "article" or _fm_get(text, "author") != "me":
            continue
        old = fn[:-3]
        new = _new_slug(old)
        if os.path.exists(os.path.join(wiki, new + ".md")):
            raise RuntimeError(f"refusing to migrate: wiki/{new}.md already exists")
        out[old] = new
    return out


def _retype(text, old):
    head, sep, body = text.partition("\n---\n")
    head = re.sub(r"^type: article$", "type: capture", head, count=1, flags=re.M)
    m = re.search(r"^aliases: \[(.*)\]$", head, re.M)
    if m:
        items = [a.strip() for a in m.group(1).split(",") if a.strip()]
        if old not in items:
            head = head[:m.start()] + f"aliases: [{', '.join(items + [old])}]" + head[m.end():]
    elif not re.search(r"^aliases:", head, re.M):
        head += f"\naliases: [{old}]"
    return head + sep + body


def _relink(text, mapping):
    """`old.md` (markdown links, `related:`, `sources:`) → `new.md`."""
    for old, new in mapping.items():
        text = re.sub(rf"(?<![\w-]){re.escape(old)}\.md(?![\w-])", new + ".md", text)
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
        body = m.group(2).rstrip()
        sep = "" if body.endswith(",") or not body.strip() else ", "
        text = text[:m.start(2)] + body + sep + '"capture"' + text[m.end(2):]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return True


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    ordered = _order(root, dry_run)
    mapping = plan(root)
    if not mapping:
        print("capture type: " + ("added capture to [types] order" if ordered else "nothing to change"))
        return {"renamed": 0, "order": ordered}
    if dry_run:
        for o, n in mapping.items():
            print(f"{o} → {n} (capture)")
        return {"renamed": len(mapping), "dry_run": True}
    for old, new in mapping.items():
        src = os.path.join(wiki, old + ".md")
        with open(src, encoding="utf-8", newline="") as f:
            text = f.read()
        with open(os.path.join(wiki, new + ".md"), "w", encoding="utf-8", newline="") as f:
            f.write(_retype(text, old))
        os.remove(src)
    touched = 0
    for fn in sorted(os.listdir(wiki)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(wiki, fn)
        with open(p, encoding="utf-8", newline="") as f:
            text = f.read()
        new = _relink(text, mapping)
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            touched += 1
    rows = _corpus(root, mapping)
    print(f"capture type: {len(mapping)} pages renamed, {touched} pages relinked, {rows} corpus rows")
    return {"renamed": len(mapping), "relinked": touched, "corpus": rows, "order": ordered}


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.root, dry_run=a.dry_run)

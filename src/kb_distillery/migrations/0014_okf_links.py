"""OKF links (schema 1.5): pages link with standard relative markdown links, `wiki/` is the bundle root.

`[[slug]]` -> `[Title](slug.md)`, `[[slug|label]]` / `[[slug\\|label]]` (table cell) -> `[label](slug.md)`,
`[[slug#Heading]]` -> `[Title](slug.md#heading)`, `![[file.png]]` -> `![file.png](../raw/.../file.png)`.
The shown text is what the app displays for the wikilink today (page `PageReader.prepareMarkdown`): the label, else the
page title the graph holds (`_title`: the first `# ` line, else the slug with spaces) with `[`, `]` and `|` turned into
spaces, else, when the name is an alias or mention and has no title of its own, the name as written.
Every target resolves through vault.links.resolve_slug (slug, `aliases:`, meta/aliases.tsv); the path is built with
vault.links.page_path. A link that does not resolve is not guessed: it stays a wikilink and is listed in the report.
Not touched, byte for byte: front matter, every `## My notes` section (the user's), fenced and inline code, math,
files below wiki/ (drawings), everything outside wiki/ (index.md and meta/log.md are regenerated / moved by the
index-and-log migration). Nothing is written until every page has been processed; idempotent.

    python src/kb_distillery/migrations/0014_okf_links.py [--root R] [--dry-run]
"""
import argparse
import os
import re
import sys

from kb_distillery.vault import frontmatter as fmlib
from kb_distillery.vault import links

PRODUCES = (1, 5)
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
SAFE_SLUG = re.compile(r"^[A-Za-z0-9._-]+$")


def _body_of(text):
    body = fmlib.split_block(text)[1] if text.startswith("---") else text
    return body.replace("\r\n", "\n")            # read as LF; a CRLF body is converted as LF and written back as CRLF


def _assets(root):
    """{file name: path from wiki/} of the files below raw/ whose name is unique there."""
    seen, dup = {}, set()
    for dirpath, _dirs, files in os.walk(os.path.join(root, "raw")):
        for fn in files:
            if fn in seen:
                dup.add(fn)
            seen[fn] = os.path.relpath(os.path.join(dirpath, fn), os.path.join(root, "wiki"))
    return {k: v for k, v in seen.items() if k not in dup}


def _read_wiki(root):
    flat, below = {}, []
    for dirpath, _dirs, files in os.walk(os.path.join(root, "wiki")):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            if dirpath == os.path.join(root, "wiki"):
                flat[fn[:-3]] = (path, text)
            else:
                below.append((path, text))
    return flat, below


def _checks(flat, new_texts, slugs):
    """After-state: page links whose target is no page, and wikilinks left in the prose."""
    broken, left = [], []
    for slug, (_p, old) in flat.items():
        body = _body_of(new_texts.get(slug, old))
        for m in links.PAGE_LINK.finditer(links.prose(body)):
            _label, target, _anchor = links.link_parts(m)
            if target not in slugs:
                broken.append((slug, m.group(0)))
        left += [(slug, w) for w in links.leftover_wikilinks(body)]
    return broken, left


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    report = links.new_report()
    report.update({"changed": [], "pages": 0, "bad_slug": [], "notes_wikilinks": 0, "below_wiki_wikilinks": 0,
                   "before_unresolved": 0, "after_broken": [], "after_wikilinks": [],
                   "notes_changed": []})
    if not os.path.isdir(os.path.join(root, "wiki")):
        return report
    flat, below = _read_wiki(root)
    report["pages"] = len(flat)
    fms = {s: (fmlib.parse(t)[0] or {}) for s, (_p, t) in flat.items()}
    slugs = set(flat)
    report["bad_slug"] = sorted(s for s in slugs if not SAFE_SLUG.match(s))
    headings = {s: {links.slugify(h) for h in HEADING.findall(links.prose(_body_of(t)))} for s, (_p, t) in flat.items()}
    needs_assets = any("![[" in t for _p, t in flat.values())
    rs = links.Resolver(slugs, {s: links.title_of(t, s) for s, (_p, t) in flat.items()}, links.alias_map(fms),
                        links.mention_map(os.path.join(root, "meta", "aliases.tsv")),
                        _assets(root) if needs_assets else {}, headings)
    todo, mixed = {}, []
    for slug, (path, text) in flat.items():
        raw_body = fmlib.split_block(text)[1] if text.startswith("---") else text
        head = text[:len(text) - len(raw_body)]
        eol = "\r\n" if raw_body.startswith("\r\n") else "\n" if text.startswith("---") and raw_body.startswith("\n") else ""
        head, raw_body = head + eol, raw_body[len(eol):]       # the closing fence's own line end belongs to the head
        body = raw_body.replace("\r\n", "\n")
        before_notes = [body[a:b] for a, b in links.notes_spans(body)]
        report["notes_wikilinks"] += sum(len(links.WIKILINK_ANY.findall(n)) for n in before_notes)
        report["before_unresolved"] += sum(1 for m in links.WIKILINK_ANY.finditer(links.prose(body)) if not m.group(1)
                                           and rs.slug(re.split(r"\\?\||#", m.group(2))[0].strip()) is None)
        new_body = links.convert(body, rs, report)
        if [new_body[a:b] for a, b in links.notes_spans(new_body)] != before_notes:
            report["notes_changed"].append(slug)
            raise RuntimeError(f"wiki/{slug}.md: a `## My notes` section would change; nothing was written")
        if new_body != body:
            try:
                todo[slug] = head + fmlib.restore_eols(raw_body, new_body)
            except ValueError:
                mixed.append(os.path.relpath(path, root))
    if mixed:
        raise RuntimeError("these CRLF pages would change their line count, so their line ends cannot be kept; convert them to LF first, "
                           "nothing was written: " + ", ".join(mixed[:10]) + (" …" if len(mixed) > 10 else ""))
    for _path, text in below:
        report["below_wiki_wikilinks"] += len(links.WIKILINK_ANY.findall(text))
    report["after_broken"], report["after_wikilinks"] = _checks(flat, todo, slugs)
    report["changed"] = [os.path.relpath(flat[s][0], root) for s in todo]
    if not dry_run:
        if report["after_broken"]:
            raise RuntimeError(f"{len(report['after_broken'])} converted link(s) point at no page; nothing was written")
        for slug, new in todo.items():
            with open(flat[slug][0], "w", encoding="utf-8", newline="") as f:
                f.write(new)
    _print(report, dry_run)
    return report


def _print(r, dry_run):
    print(f"okf links: {len(r['changed'])} pages {'would change' if dry_run else 'changed'}, {r['converted']} links converted "
          f"({r['via_alias']} through an alias or mention)")
    print(f"  unresolved before: {r['before_unresolved']}  broken after: {len(r['after_broken'])}  "
          f"wikilinks left in prose after: {len(r['after_wikilinks'])}  left in My notes: {r['notes_wikilinks']}  "
          f"below wiki/: {r['below_wiki_wikilinks']}")
    print(f"  link bytes: wikilink {r.get('bytes_wikilink', 0)}, [Title](slug.md) {r.get('bytes_new', 0)}, "
          f"[slug](slug.md) {r.get('bytes_slug_form', 0)}")
    for key in ("unresolved", "embed_unresolved", "anchor_unresolved", "empty", "bad_slug", "after_broken", "after_wikilinks"):
        if r[key]:
            print(f"  {key}: {len(r[key])} e.g. {r[key][:5]}")


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        apply(a.root, dry_run=a.dry_run)
    except RuntimeError as e:
        sys.exit(f"error: {e}")

#!/usr/bin/env python3
"""Explore cataloged raw sources (0 LLM) — the one door from the wiki to raw/.

Prints text and metadata for the calling agent to reason over. Never reads raw/inbox/
(catalog first), never writes anything.

    python3 -m kb_distillery.search.explore_raw find "implicit regularization matrix factorization" --limit 8
    python3 -m kb_distillery.search.explore_raw find "grokking" --scope scope-x   # only that scope's files
    python3 -m kb_distillery.search.explore_raw read raw/printed-docs/2020-x.pdf --pages 1-3
    python3 -m kb_distillery.search.explore_raw check raw/printed-docs/2020-x.pdf --pages-of paper-2020-x
    python3 -m kb_distillery.search.explore_raw recommend raw/printed-docs/2020-x.pdf

Exit codes: 0 ok, 2 refused / not found.
"""
import argparse
import os
import re
import sys

from kb_distillery.config.paths import vault_root
HERE = os.path.join(vault_root(), "meta")

from kb_distillery.lint import lint
from kb_distillery.search import query
from kb_distillery.vault import links
from kb_distillery.vault.graph import extract_section, tokenize, claim_text

ROOT = lint.ROOT
SKIP_DISP = ("asset:", "ink:", "dupe:")
TEXT_EXTS = (".md", ".txt", ".html", ".htm")
TIERS = "tiers: skip | easy (~2-4k) | full (~8-12k) | deep (~25-40k+) — the agent decides"


class Refused(Exception):
    pass


# ── data access (patched in tests) ─────────────────────────────────────────

def _manifest():
    return lint.read_manifest()


def _index():
    return query.parse_index()


def _maturity(slug):
    from kb_distillery.vault import frontmatter
    return str((frontmatter.parse(_wiki_text(slug) or "")[0] or {}).get("maturity") or "")


def _wiki_text(slug):
    path = os.path.join(ROOT, "wiki", f"{slug}.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _hub_rows(raw_path):
    """[(hub slug, row title)] for course/series Contents rows listing raw_path."""
    from kb_distillery.vault import hubs
    out = []
    wiki = os.path.join(ROOT, "wiki")
    if not os.path.isdir(wiki):
        return out
    for name in sorted(os.listdir(wiki)):
        if not name.startswith(("course-", "series-")):
            continue
        with open(os.path.join(wiki, name), encoding="utf-8") as f:
            text = f.read()
        for r in hubs.parse_contents(text):
            if raw_path in r["raws"]:
                out.append((name[:-3], r["title"]))
    return out


def _disp(row):
    d = row.get("disposition", "")
    return "UNDIGESTED (queued)" if d == "queued" else d


def _resolve(raw_path, rows):
    p = os.path.normpath(raw_path)
    if os.path.isabs(p):
        p = os.path.relpath(p, ROOT)
    if p == "raw/inbox" or p.startswith("raw/inbox/"):
        raise Refused(f"{p} is in the inbox — catalog first: python3 -m kb_distillery.ingest catalog {p}")
    if p not in rows:
        raise Refused(f"{p} is not in the corpus (meta/corpus.tsv); try `find` to locate it")
    return p, rows[p]


def _text(path, max_pages, pages):
    from kb_distillery.ingest.extract import extract_text
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        raise Refused(f"{path} is in the manifest but its bytes are not in this checkout")
    return extract_text(full, max_pages=max_pages, pages=pages) or "(no text extracted)"


def _parse_pages(s):
    if not s:
        return None
    m = re.fullmatch(r"(\d+)-(\d+)", s.strip())
    if not m:
        raise Refused(f"--pages must look like A-B, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def _header(path, row):
    lines = [f"path: {path}", f"sha1: {row.get('sha1', '')[:10]}", f"kind: {row.get('kind', '')}",
             f"disposition: {_disp(row)}", f"collection: {row.get('collection', '') or '-'}"]
    slug = row.get("slug", "")
    if slug:
        st = (_index().get(slug) or {}).get("status") or _maturity(slug)    # index rows carry no maturity
        lines.append(f"page: {links.link(slug)} {st}".rstrip())
    for hub, title in _hub_rows(path):
        lines.append(f"hub row: {links.link(hub)} · {title}")
    return "\n".join(lines)


# ── find ───────────────────────────────────────────────────────────────────

def cmd_find(question, limit=10, include_all=False, scope=None):
    qt = tokenize(" ".join(question))
    if not qt:
        print("empty question")
        return 2
    rows, index = _manifest(), _index()
    if scope:
        from kb_distillery.vault import scopes
        members = scopes.rows_of(scope, rows)
        if not members and _wiki_text(scope) is None:
            raise Refused("unknown scope " + repr(scope))
        rows = dict((p, rows[p]) for p in members)
    ranked = []
    for path, r in rows.items():
        d = r.get("disposition", "")
        if d.startswith(SKIP_DISP) or d == "sidecar" or path.startswith("raw/inbox/"):
            continue
        if d == "skip" and not include_all:
            continue
        stem = os.path.splitext(os.path.basename(path.rstrip("/")))[0].lower()
        score, sig = 0, []
        coll = (r.get("collection") or "").lower()
        slug = r.get("slug", "")
        summ = (index.get(slug, {}).get("summary", "") or "").lower()
        head = ""
        if path.lower().endswith(TEXT_EXTS) and os.path.isfile(os.path.join(ROOT, path)):
            with open(os.path.join(ROOT, path), encoding="utf-8", errors="ignore") as f:
                head = f.read(2000).lower()
        for t in qt:
            if t in stem:
                score += 12
                sig.append(f"name:{t}")
            if t in coll:
                score += 5
                sig.append(f"coll:{t}")
            if slug and t in slug.lower():
                score += 6
                sig.append(f"slug:{t}")
            if t in summ:
                score += 6
                sig.append(f"summary:{t}")
            if t in head:
                score += 3
                sig.append(f"text:{t}")
        if score:
            ranked.append((score, path, r, sig))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    if not ranked:
        print(f"NO_MATCHES  {' '.join(question)}  (PDFs are matched by name/metadata only)"
              + (("  [scope " + scope + "]") if scope else ""))
        return 0
    print(f"RAW_CANDIDATES  {' '.join(question)}  ({len(ranked)} hits, showing {min(limit, len(ranked))})")
    for score, path, r, sig in ranked[:limit]:
        d = "UNDIGESTED" if r.get("disposition") == "queued" else r.get("disposition", "")
        why = ",".join(dict.fromkeys(sig[:6]))
        print(f"  {score:3d}  {d:<10}  {path}  coll={r.get('collection') or '-'}  "
              f"page={r.get('slug') or '-'}  [{why}]")
    return 0


# ── read / check / recommend ───────────────────────────────────────────────

def cmd_read(raw, pages, max_pages):
    rows = _manifest()
    p, row = _resolve(raw, rows)
    rng = _parse_pages(pages)
    body = _text(p, max_pages, rng)
    print("=== SOURCE METADATA ===")
    print(_header(p, row))
    print("=== TEXT ===")
    print(body)
    return 0


def _page_block(slug):
    text = _wiki_text(slug)
    if text is None:
        return f"(no wiki page {slug})"
    fm = lint.parse_frontmatter(text) or {}
    out = [f"claims: {claim_text(slug, fm, text) or '(none)'}"]
    for h in ("Takeaways for my thesis", "Connections"):
        s = extract_section(text, h).strip()
        if s:
            out.append(f"--- {h} ---\n{s}")
    return "\n".join(out)


def cmd_check(raw, slugs, pages, max_pages):
    rows = _manifest()
    p, row = _resolve(raw, rows)
    body = _text(p, max_pages, _parse_pages(pages))
    print("=== SOURCE ===")
    print(_header(p, row))
    print(body)
    for s in slugs:
        print(f"=== PAGE {s} ===")
        print(_page_block(s))
    return 0


def _page_count(path):
    full = os.path.join(ROOT, path)
    if not path.lower().endswith(".pdf") or not os.path.isfile(full):
        return None
    try:
        import fitz
        with fitz.open(full) as d:
            return d.page_count
    except Exception:
        return None


def _stem_tokens(path):
    stem = os.path.splitext(os.path.basename(path.rstrip("/")))[0]
    return set(tokenize(re.sub(r"^\d{4}-", "", stem).replace("-", " ")))


def cmd_recommend(raw):
    rows = _manifest()
    p, row = _resolve(raw, rows)
    full = os.path.join(ROOT, p)
    pc = _page_count(p)
    if pc is not None:
        size = f"{pc} pages"
    elif os.path.isfile(full):
        size = f"{os.path.getsize(full)} bytes" + (" (PDF page count unavailable)" if p.endswith(".pdf") else "")
    else:
        size = "bytes not in this checkout"
    slug = row.get("slug", "")
    text = _wiki_text(slug) if slug else None
    fm = (lint.parse_frontmatter(text) or {}) if text else {}
    year = re.match(r"(\d{4})-", os.path.basename(p))
    sidecar = os.path.isfile(os.path.join(os.path.dirname(full), "parsed.md")) or \
        os.path.isfile(os.path.join(full, "parsed.md"))
    print("=== RECOMMEND INPUT ===")
    print(_header(p, row))
    print(f"size: {size}")
    print(f"page exists: {'yes, depth=' + str(fm.get('depth', '?')) if text else 'no'}")
    print(f"year (filename): {year.group(1) if year else '-'}")
    print(f"sidecar parsed.md: {'yes' if sidecar else 'no'}")
    toks = _stem_tokens(p)
    near = []
    for q, r in rows.items():
        if q == p or r.get("disposition", "").startswith(SKIP_DISP) or r.get("disposition") == "sidecar":
            continue
        o = len(toks & _stem_tokens(q))
        if o:
            near.append((o, q, r))
    near.sort(key=lambda x: (-x[0], x[1]))
    print("nearest corpus rows (filename-token overlap):")
    for o, q, r in near[:5]:
        print(f"  {o}  {r.get('disposition', '')}  {q}")
    if not near:
        print("  (none)")
    print(TIERS)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kb_distillery.search.explore_raw")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="rank cataloged raw rows for a question")
    f.add_argument("question", nargs="+")
    f.add_argument("--limit", type=int, default=10)
    f.add_argument("--all", action="store_true", help="include rows dispositioned skip")
    f.add_argument("--scope", help="only the rows of this scope (scope-x)")
    r = sub.add_parser("read", help="metadata header + text of a raw file")
    r.add_argument("path")
    r.add_argument("--pages")
    r.add_argument("--max-pages", type=int, default=5)
    c = sub.add_parser("check", help="source text next to wiki page claims")
    c.add_argument("path")
    c.add_argument("--pages-of", nargs="+", required=True, metavar="SLUG")
    c.add_argument("--pages")
    c.add_argument("--max-pages", type=int, default=3)
    rc = sub.add_parser("recommend", help="facts for choosing a digest tier")
    rc.add_argument("path")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "find":
            return cmd_find(a.question, a.limit, a.all, a.scope)
        if a.cmd == "read":
            return cmd_read(a.path, a.pages, a.max_pages)
        if a.cmd == "check":
            return cmd_check(a.path, a.pages_of, a.pages, a.max_pages)
        return cmd_recommend(a.path)
    except Refused as e:
        print(f"REFUSED  {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

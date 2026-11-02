#!/usr/bin/env python3
"""Wiki query helpers — index-first candidate ranking (0 LLM).

Karpathy pattern: read the root wiki/index.md, then the one section index you need, then drill into pages. At ~200 pages
the index is still enough; this supplements it with full-text term scoring.

    python3 -m kb_distillery.search.query candidates "tensor rank implicit bias"
    python3 -m kb_distillery.search.query candidates "double descent" --limit 8
    python3 -m kb_distillery.search.query mocs
    python3 -m kb_distillery.search.query candidates "double descent" --scope scope-x   # only that scope's pages
    python3 -m kb_distillery.search.query scope-status scope-x                          # coverage + undigested files
"""
import argparse
import os
import re
import sys

from kb_distillery.vault import links as page_links
from kb_distillery.vault.graph import tokenize
from kb_distillery.vault.schema import INDEX_REL
from kb_distillery.vault import wikiindex

from kb_distillery.paths import vault_root
ROOT = vault_root()
WIKI = os.path.join(ROOT, "wiki")
INDEX = os.path.join(ROOT, INDEX_REL)

def parse_index():
    """Return slug -> {section, title, status, summary} from the section indexes under wiki/ (kb_distillery.vault.wikiindex;
    the root index only counts them). `status` is empty: rows carry no maturity."""
    if not os.path.isfile(INDEX):
        return {}
    rows = wikiindex.parse_rows(os.path.dirname(os.path.dirname(INDEX)))
    return {slug: {"section": r["section"], "title": r["title"], "status": "", "summary": r["summary"]}
            for slug, r in rows.items()}


def _ref(slug, meta):
    """How a CLI line names a page: the page link `[Title](slug.md)` (the form the answers cite)."""
    return page_links.link(slug, (meta or {}).get("title") or slug)


def _maturity(slug):
    """The page's `maturity:` (index rows carry none)."""
    from kb_distillery.vault import frontmatter
    try:
        with open(wiki_path(slug), encoding="utf-8") as f:
            return str(frontmatter.parse(f.read())[0].get("maturity") or "")
    except (OSError, AttributeError):
        return ""


def wiki_path(slug):
    return os.path.join(WIKI, f"{slug}.md")


def read_body(slug):
    path = wiki_path(slug)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def score_slug(slug, meta, qtokens):
    slug_l = slug.lower().replace("-", " ")
    summary = (meta or {}).get("summary", "")
    blob = f"{slug_l} {summary.lower()}"
    body = read_body(slug).lower()[:12000]
    score = 0
    hits = []
    for t in qtokens:
        if t in slug_l.replace(" ", "-") or t in slug_l:
            score += 12
            hits.append(f"slug:{t}")
        elif t in summary.lower():
            score += 6
            hits.append(f"summary:{t}")
        elif t in body:
            n = body.count(t)
            score += min(4, 1 + n // 2)
            hits.append(f"body:{t}")
    if meta and meta.get("section") == "Maps of Content" and score > 0:
        score += 2
    return score, hits


def load_scope(scope_slug):
    """scope_context for the checkout this script lives in (raises scopes.ScopeUnknown)."""
    from kb_distillery.vault import scopes
    return scopes.scope_context(scope_slug, ROOT)


def cmd_candidates(query, limit=12, scope=None):
    qtokens = tokenize(query)
    if not qtokens:
        print("empty query")
        return 1
    allowed = None
    if scope:
        from kb_distillery.vault import scopes
        try:
            allowed = load_scope(scope)["pages"]
        except scopes.ScopeUnknown as e:
            print("ERROR  " + str(e), file=sys.stderr)
            return 2
    index = parse_index()
    ranked = []
    for slug, meta in index.items():
        if slug in ("AGENTS", "log", "thesis"):
            continue
        if allowed is not None and slug not in allowed:
            continue
        if not os.path.isfile(wiki_path(slug)):
            continue
        score, hits = score_slug(slug, meta, qtokens)
        if score > 0:
            ranked.append((score, slug, meta, hits))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    if not ranked:
        print("NO_MATCHES  " + query + (("  [scope " + scope + "]") if scope else ""))
        print("the scope's pages do not cover this yet; see scope-status" if scope
              else "read wiki/index.md, then the section you need; broaden terms or check MOCs")
        return 0
    print(f"CANDIDATES  {query}" + (("  [scope " + scope + "]") if scope else "") + f"  ({len(ranked)} hits, showing {min(limit, len(ranked))})")
    for score, slug, meta, hits in ranked[:limit]:
        summary = (meta.get("summary") or "")[:90]
        why = ", ".join(dict.fromkeys(hits[:4]))
        print(f"  {score:3d}  {_ref(slug, meta)}  {meta.get('section', '')}  {why}")
        if summary:
            print(f"       {summary}")
    return 0


def cmd_scope_status(scope, max_files=200):
    from kb_distillery.vault import scopes
    try:
        ctx = load_scope(scope)
    except scopes.ScopeUnknown as exc:
        print("ERROR  " + str(exc), file=sys.stderr)
        return 2
    index = parse_index()
    print("SCOPE  " + ctx["slug"] + "  " + ctx["title"])
    print(scopes.coverage_line(ctx))
    pages = sorted(ctx["pages"] - {ctx["slug"]})
    print("PAGES  (" + str(len(pages)) + ")")
    for s in pages:
        print("  " + _ref(s, index.get(s)) + "  " + (index.get(s, {}).get("summary") or "")[:90])
    unc = ctx["uncovered"]
    print("NOT_YET_DIGESTED  (" + str(len(unc)) + ")")
    for u in unc[:max_files]:
        print("  " + u["path"])
    if len(unc) > max_files:
        print("  ... and " + str(len(unc) - max_files) + " more")
    return 0


def cmd_mocs():
    index = parse_index()
    print("THEME_ENTRY_POINTS")
    for slug, meta in sorted(index.items()):
        if slug.startswith("theme-"):
            print(f"  {_ref(slug, meta)}  {meta.get('status') or _maturity(slug)}  {(meta.get('summary') or '')[:100]}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb_distillery.search.query")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("candidates", help="rank wiki slugs for a natural-language query")
    c.add_argument("query")
    c.add_argument("--limit", type=int, default=12)
    c.add_argument("--scope", help="restrict to the knowledge projection of a scope (scope-x)")

    st = sub.add_parser("scope-status", help="a scope's pages, coverage and undigested files")
    st.add_argument("scope")

    sub.add_parser("mocs", help="list theme MOC entry points")

    args = p.parse_args(argv)
    if args.cmd == "candidates":
        return cmd_candidates(args.query, args.limit, args.scope)
    if args.cmd == "scope-status":
        return cmd_scope_status(args.scope)
    if args.cmd == "mocs":
        return cmd_mocs()
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Wiki query helpers — index-first candidate ranking (0 LLM).

Karpathy pattern: read index.md first, then drill into pages. At ~200 pages
the index is still enough; this supplements it with full-text term scoring.

    python3 -m kb.search.query candidates "tensor rank implicit bias"
    python3 -m kb.search.query candidates "double descent" --limit 8
    python3 -m kb.search.query mocs
    python3 -m kb.search.query candidates "double descent" --scope scope-x   # only that scope's pages
    python3 -m kb.search.query scope-status scope-x                          # coverage + undigested files
"""
import argparse
import os
import re
import sys

from kb.core.graph import tokenize

from kb.paths import vault_root
from kb.core.links import WIKILINK_TARGET
ROOT = vault_root()
WIKI = os.path.join(ROOT, "wiki")
INDEX = os.path.join(ROOT, "index.md")

LINK = WIKILINK_TARGET
INDEX_ROW = re.compile(r"^\| \[\[([^\]]+)\]\] \| ([^|]*) \| (.*) \|$")


def parse_index():
    """Return slug -> {section, status, summary}."""
    if not os.path.isfile(INDEX):
        return {}
    entries = {}
    section = ""
    for line in open(INDEX, encoding="utf-8"):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = INDEX_ROW.match(line.strip())
        if not m:
            continue
        slug, status, summary = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        entries[slug] = {"section": section, "status": status, "summary": summary}
    return entries


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
    from kb.core import scopes
    return scopes.scope_context(scope_slug, ROOT)


def cmd_candidates(query, limit=12, scope=None):
    qtokens = tokenize(query)
    if not qtokens:
        print("empty query")
        return 1
    allowed = None
    if scope:
        from kb.core import scopes
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
              else "read index.md; broaden terms or check MOCs")
        return 0
    print(f"CANDIDATES  {query}" + (("  [scope " + scope + "]") if scope else "") + f"  ({len(ranked)} hits, showing {min(limit, len(ranked))})")
    for score, slug, meta, hits in ranked[:limit]:
        summary = (meta.get("summary") or "")[:90]
        why = ", ".join(dict.fromkeys(hits[:4]))
        print(f"  {score:3d}  [[{slug}]]  {meta.get('section', '')}  {why}")
        if summary:
            print(f"       {summary}")
    return 0


def cmd_scope_status(scope, max_files=200):
    from kb.core import scopes
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
        print("  [[" + s + "]]  " + (index.get(s, {}).get("summary") or "")[:90])
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
            print(f"  [[{slug}]]  {meta.get('status', '')}  {(meta.get('summary') or '')[:100]}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.search.query")
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

#!/usr/bin/env python3
"""Semantic find — 1-hop bundles for LLM review (0 LLM)."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from kb.core.graph import claim_text, extract_section, one_hop, outbound_links, score_pair
from kb.lint.lint import LINK, parse_frontmatter
from kb.core.schema import SOURCE_TYPES

from kb.paths import vault_root
ROOT = vault_root()
SEMFIND_DIR = os.path.join(ROOT, "meta", ".semfind")
WIKI_DIR = "wiki"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def walk(d, ext=None, root=None):
    """Like lint.walk, but relative to this module's ROOT (honours KB_ROOT), or to `root`."""
    root = root or ROOT
    out = []
    base = os.path.join(root, d)
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if not x.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") or (ext and not fn.endswith(ext)):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    return sorted(out)


def load_pages(root=None):
    """{slug: (rel, frontmatter, text)} of the active knowledge base's wiki, or of the one at `root`."""
    root = root or ROOT
    pages = {}
    for rel in walk(WIKI_DIR, ".md", root):
        if "excalidraw" in rel:
            continue
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        slug = os.path.basename(rel)[:-3]
        fm = parse_frontmatter(text)
        if fm:
            pages[slug] = (rel, fm, text)
    return pages


def _session_id(source):
    return hashlib.sha1(source.encode()).hexdigest()[:12]


def _snippets(slug, pages):
    if slug not in pages:
        return ""
    _rel, fm, text = pages[slug]
    t = fm.get("type", "")
    lines = [f"### [[{slug}]] ({t}, {fm.get('status', '')})"]
    if t in SOURCE_TYPES:
        for h in ("Problem", "Main result", "Takeaways for my thesis", "Connections", "Links out"):
            block = extract_section(text, h)
            if block:
                lines.append(f"**{h}:** {block[:800]}")
    elif t == "question":
        for h in ("Question", "Current state"):
            block = extract_section(text, h)
            if block:
                lines.append(f"**{h}:** {block[:800]}")
    elif t == "idea":
        for h in ("One-liner", "Formal"):
            block = extract_section(text, h)
            if block:
                lines.append(f"**{h}:** {block[:800]}")
    else:
        for h in ("Scope", "Threads"):
            block = extract_section(text, h)
            if block:
                lines.append(f"**{h}:** {block[:800]}")
    return "\n".join(lines)


def _top_pairs(seeds, pages, max_pairs=6):
    neighbors = set()
    for s in seeds:
        neighbors.add(s)
        neighbors.update(one_hop(s, pages))
    pair_scores = []
    slist = sorted(neighbors)
    for i, a in enumerate(slist):
        for b in slist[i + 1 :]:
            sc = score_pair(a, b, pages)
            if sc > 5:
                pair_scores.append((sc, a, b))
    pair_scores.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [(a, b, sc) for sc, a, b in pair_scores[:max_pairs]]


def build_bundle(seeds, source, max_pairs=6, session_id=None):
    pages = load_pages()
    seed_slugs = []
    for s in seeds:
        s = s.replace("wiki/", "").replace(".md", "")
        if s in pages:
            seed_slugs.append(s)
    if not seed_slugs:
        print("no valid seed slugs")
        return 1

    pairs = _top_pairs(seed_slugs, pages, max_pairs=max_pairs)
    neighbors = set(seed_slugs)
    for s in seed_slugs:
        neighbors.update(one_hop(s, pages))

    sid = session_id or _session_id(source)
    sdir = os.path.join(SEMFIND_DIR, sid)
    os.makedirs(sdir, exist_ok=True)

    from kb.core.coherence import check_coherence, classify_pair_kind

    scoped_hits = []
    for h in check_coherence(pages, rows={}):
        sl = set(h["slugs"].split(","))
        if sl & neighbors:
            scoped_hits.append(h)

    manifest = {
        "source": source,
        "created_at": _now(),
        "seeds": seed_slugs,
        "neighbors": sorted(neighbors),
        "pairs": [{"a": a, "b": b, "score": sc} for a, b, sc in pairs],
    }
    with open(os.path.join(sdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    with open(os.path.join(sdir, "coherence.json"), "w", encoding="utf-8") as f:
        json.dump(scoped_hits, f, indent=2)
        f.write("\n")

    lines = [
        f"# Semfind bundle — {source}",
        "",
        f"Seeds: {', '.join(f'[[{s}]]' for s in seed_slugs)}",
        "",
        "## Pairs to review",
        "",
    ]
    for a, b, sc in pairs:
        ka = classify_pair_kind(a, b, pages)
        lines.append(f"### [[{a}]] vs [[{b}]] (score={sc}, kind={ka})")
        lines.append("")
        lines.append(_snippets(a, pages))
        lines.append("")
        lines.append(_snippets(b, pages))
        lines.append("")
        if ka == "external":
            lines.append(
                f"> **external:** note on each paper's ## Connections / ## Links out — "
                f"`Disagrees with [[{b}]] on …`"
            )
        else:
            lines.append("> **internal:** fix ingestion — re-digest or edit wiki.")
        lines.append("")

    bundle_path = os.path.join(sdir, "bundle.md")
    with open(bundle_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    rel_bundle = os.path.relpath(bundle_path, ROOT).replace(os.sep, "/")
    print(f"SEMFIND_READY {rel_bundle} ({len(neighbors)} pages, {len(pairs)} pairs)")
    return 0


def bundle_from_ingest(sha):
    ingest_dir = os.path.join(ROOT, "meta", ".ingest", sha)
    session_path = os.path.join(ingest_dir, "session.json")
    plan_path = os.path.join(ingest_dir, "plan.json")
    if not os.path.isfile(session_path):
        return 1
    with open(session_path, encoding="utf-8") as f:
        session = json.load(f)
    seeds = []
    for rel in session.get("new_files", []) + session.get("modified_files", []):
        if rel.startswith("wiki/") and rel.endswith(".md"):
            seeds.append(rel)
    if os.path.isfile(plan_path):
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        for upd in plan.get("moc_updates", []):
            seeds.append(f"wiki/{upd['moc']}.md")
    return build_bundle(seeds, f"ingest:{sha}")


def bundle_from_distill(think_rel, plan):
    seeds = []
    for p in plan.get("proposals", []):
        seeds.append(p.get("target", ""))
    return build_bundle(seeds, f"distill:{think_rel}")


def cmd_moc(moc_slug, max_pairs=10):
    moc_slug = moc_slug.replace("wiki/", "").replace(".md", "")
    path = os.path.join(ROOT, WIKI_DIR, f"{moc_slug}.md")
    if not os.path.isfile(path):
        print(f"missing {moc_slug}")
        return 1
    text = open(path, encoding="utf-8").read()
    linked = sorted(outbound_links(text, parse_frontmatter(text)))
    source = f"moc:{moc_slug}"
    return build_bundle(
        [f"wiki/{moc_slug}.md"] + [f"wiki/{s}.md" for s in linked if s != moc_slug],
        source,
        max_pairs=max_pairs,
        session_id=f"moc-{moc_slug}",
    )


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.search.semfind")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bundle")
    b.add_argument("--seeds", required=True, help="comma-separated wiki paths or slugs")
    b.add_argument("--source", default="manual")
    b.add_argument("--max-pairs", type=int, default=6)

    m = sub.add_parser("topic", aliases=["theme", "moc"], help="bundle a topic page and its neighbours")
    m.add_argument("moc_slug", metavar="topic_slug")
    m.add_argument("--max-pairs", type=int, default=10)

    args = p.parse_args(argv)
    if args.cmd == "bundle":
        seeds = [x.strip() for x in args.seeds.split(",") if x.strip()]
        return build_bundle(seeds, args.source, max_pairs=args.max_pairs)
    if args.cmd in ("topic", "theme", "moc"):
        return cmd_moc(args.moc_slug, max_pairs=args.max_pairs)
    return 1


if __name__ == "__main__":
    sys.exit(main())

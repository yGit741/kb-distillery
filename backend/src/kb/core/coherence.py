#!/usr/bin/env python3
"""Semantic coherence checks — 0 LLM. See meta/coherence-warnings.tsv."""
import argparse
import csv
import hashlib
import json
import os
import sys

from kb.core.schema import SOURCE_TYPES, strip_prefix
from kb.core.graph import (  # noqa: E402
    claim_text,
    inbound_index,
    jaccard,
    outbound_links,
    polarity_clash,
    tokenize,
)

from kb.paths import vault_root
from kb.core.summary import unquote
ROOT = vault_root()  # KB_ROOT: share build
WARNINGS_PATH = os.path.join(ROOT, "meta", "coherence-warnings.tsv")
WARNINGS_COLS = ["id", "score", "kind", "slugs", "summary", "status"]
INTERNAL_ERROR_THRESHOLD = 70
LEXICAL_CLASH_CAP = 60      # a purely lexical polarity clash never reaches the error threshold
STATUSES = frozenset({"open", "dismissed", "fixed", "noted"})


def _first_line(text):
    body = text.split("\n---", 1)[-1]
    seen_h1 = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            seen_h1 = True
            continue
        if seen_h1 and s and not s.startswith(("#", ">", "-", "|", "*")):
            return s.rstrip(".")
    return ""


def _hit_id(kind, slugs, summary):
    key = f"{kind}|{'|'.join(sorted(slugs))}|{summary[:80]}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _page_type(pages, slug):
    if slug not in pages:
        return ""
    return pages[slug][1].get("type", "")


def _is_digested_paper(pages, slug):
    if slug not in pages:
        return False
    fm = pages[slug][1]
    return fm.get("type") in SOURCE_TYPES and fm.get("status") == "digested"


def classify_pair_kind(slug_a, slug_b, pages):
    ta, tb = _page_type(pages, slug_a), _page_type(pages, slug_b)
    if ta in SOURCE_TYPES and tb in SOURCE_TYPES and _is_digested_paper(pages, slug_a) and _is_digested_paper(pages, slug_b):
        return "external"
    if ta in ("question", "idea", "topic") or tb in ("question", "idea", "topic"):
        return "internal"
    return "internal"


def _score_hit(kind, base, extra=0):
    score = min(100, base + extra)
    if kind == "internal":
        score = min(100, score + 10)
    return score


def check_coherence(pages, rows=None, err_fn=None, warn_fn=None, prior=None, fresh=None):
    """Run coherence heuristics. Returns list of hit dicts."""
    hits = []
    inbound = inbound_index(pages)
    rows = rows or {}
    prior = prior or load_warnings()
    fresh = set(fresh or ())     # pages of the session being finalized (paper + its new stubs)

    def add(kind, slugs, summary, score):
        slugs = sorted(set(slugs))
        hits.append({
            "id": _hit_id(kind, slugs, summary),
            "score": score,
            "kind": kind,
            "slugs": ",".join(slugs),
            "summary": summary,
            "status": "open",
        })

    # Polarity / status checks on linked pairs
    seen_pairs = set()
    for slug, (rel, fm, text) in pages.items():
        claim = claim_text(slug, fm, text)
        for other in outbound_links(text, fm):
            # visit each pair once, ordered by slug *without* its type prefix, so renaming
            # `2017-x` → `paper-2017-x` doesn't change which side's links are compared
            if other not in pages or (strip_prefix(other), other) <= (strip_prefix(slug), slug):
                continue
            if slug in fresh and other in fresh:
                continue
            pair = (slug, other)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            ofm, otext = pages[other][1], pages[other][2]
            oclaim = claim_text(other, ofm, otext)
            clash, shared = polarity_clash(claim, oclaim,
                                           ignore=tokenize(slug) + tokenize(other))
            if not clash:
                continue
            kind = classify_pair_kind(slug, other, pages)
            base = 30 + min(30, shared * 3)
            add(kind, [slug, other],
                f"polarity clash on shared topic ({shared} tokens)",
                min(LEXICAL_CLASH_CAP, _score_hit(kind, base)))

        # q-* status tension vs digested paper
        if fm.get("type") == "question" and fm.get("status") in ("open", "partial"):
            cs = claim_text(slug, fm, text).lower()
            if any(w in cs for w in ("unknown", "open", "unclear", "not known")):
                for other in outbound_links(text, fm):
                    if _is_digested_paper(pages, other):
                        oclaim = claim_text(other, pages[other][1], pages[other][2])
                        if len(set(tokenize(claim)) & set(tokenize(oclaim))) >= 2:
                            add("internal", [slug, other],
                                "q-* still open/unknown but linked digested paper may resolve it",
                                _score_hit("internal", 55))

    # Near-duplicate one-liners (cosmetic)
    for slug, (rel, fm, text) in pages.items():
        one = _first_line(text)
        if not one or len(one) < 20:
            continue
        for nb in inbound.get(slug, set()):
            if nb not in pages:
                continue
            nrel, nfm, ntext = pages[nb]
            none = _first_line(ntext)
            sim = jaccard(one, none)
            if 0.6 <= sim < 0.98:
                add("cosmetic", [slug, nb], "near-duplicate one-liner", 25)

    # Asymmetric MOC links
    for slug, (rel, fm, text) in pages.items():
        if fm.get("type") not in ("idea", "question"):
            continue
        for target in outbound_links(text, fm):
            if not target.startswith("theme-") or target not in pages:
                continue
            ttext = pages[target][2]
            if slug not in outbound_links(ttext, pages[target][1]):
                add("cosmetic", [slug, target], "asymmetric link to theme", 20)

    # Re-ingest drift: queued raw with existing digested slug
    for raw_path, row in rows.items():
        if row.get("disposition") != "queued":
            continue
        wiki_slug = row.get("slug", "")
        if not wiki_slug or wiki_slug not in pages:
            continue
        wfm = pages[wiki_slug][1]
        if wfm.get("type") != "paper" or wfm.get("status") != "digested":
            continue
        add("internal", [wiki_slug],
            f"raw re-queued but wiki still digested — re-digest `{raw_path}`",
            _score_hit("internal", 80))

    # Index drift
    index_path = os.path.join(ROOT, "index.md")
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_text = f.read()
        for slug, (rel, fm, text) in pages.items():
            if f"[[{slug}]]" not in index_text:
                continue
            fl = unquote(fm.get("summary")) or _first_line(text)     # index.md shows the summary when set
            if fl and fl[:40].replace("|", "\\|") not in index_text:
                add("cosmetic", [slug], "index summary may be stale vs page body", 15)

    # Route to lint err/warn
    for h in hits:
        old = prior.get(h["id"], {})
        if old.get("status") in ("dismissed", "fixed", "noted"):
            continue
        loc = h["slugs"].replace(",", " vs ")
        msg = f"[{h['kind']}] score={h['score']} {h['summary']} ({loc})"
        if h["kind"] == "internal" and h["score"] >= INTERNAL_ERROR_THRESHOLD and err_fn:
            err_fn("coherence", msg)
        elif h["kind"] in ("internal", "external", "scope") and warn_fn:
            warn_fn("coherence", msg)
        elif h["kind"] == "cosmetic" and warn_fn:
            warn_fn("coherence", msg)

    return hits


def load_warnings():
    if not os.path.isfile(WARNINGS_PATH):
        return {}
    out = {}
    with open(WARNINGS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            out[row["id"]] = row
    return out


def merge_warnings(fresh_hits, prior=None):
    prior = prior or load_warnings()
    merged = {}
    fresh_ids = {h["id"] for h in fresh_hits}
    for h in fresh_hits:
        old = prior.get(h["id"], {})
        status = old.get("status", "open")
        if status not in STATUSES:
            status = "open"
        if status in ("dismissed", "fixed", "noted") and h["id"] in prior:
            merged[h["id"]] = {**h, "status": status}
        else:
            merged[h["id"]] = h
    for hid, row in prior.items():
        if hid not in fresh_ids and row.get("status") == "open":
            continue  # drop stale open rows
        if hid not in merged:
            merged[hid] = row
    return merged


def write_warnings(merged):
    os.makedirs(os.path.dirname(WARNINGS_PATH), exist_ok=True)
    with open(WARNINGS_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=WARNINGS_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for hid in sorted(merged.keys()):
            row = merged[hid]
            w.writerow({c: row.get(c, "") for c in WARNINGS_COLS})


def run_coherence_lint(pages, rows, err_fn, warn_fn, fresh=None):
    hits = check_coherence(pages, rows=rows, err_fn=err_fn, warn_fn=warn_fn, fresh=fresh)
    merged = merge_warnings(hits)
    write_warnings(merged)
    internal = sum(1 for r in merged.values() if r.get("kind") == "internal" and r.get("status") == "open")
    external = sum(1 for r in merged.values() if r.get("kind") == "external" and r.get("status") == "open")
    return merged, internal, external


def cmd_status():
    merged = load_warnings()
    open_rows = [r for r in merged.values() if r.get("status") == "open"]
    print(f"{len(open_rows)} open / {len(merged)} total")
    for r in sorted(open_rows, key=lambda x: -int(x.get("score", 0))):
        print(f"  {r['id']}  {r['kind']}  {r['score']}  {r['slugs']}  {r['summary'][:60]}")
    return 0


_STATUS_MAP = {"dismiss": "dismissed", "fixed": "fixed", "noted": "noted"}


def _regenerate():
    """Recompute the manifest from the current wiki (what a lint run would write)."""
    try:
        from kb.lint import lint
        pages = lint.load_wiki_pages()
        hits = check_coherence(pages, rows={})
        return merge_warnings(hits)
    except Exception:
        return None


def cmd_set_status(wid, status):
    merged = load_warnings()
    if wid not in merged:
        fresh = _regenerate() or {}             # lint just regenerated: recompute before failing
        if wid in fresh:
            merged[wid] = fresh[wid]
    if wid not in merged:
        print(f"unknown id {wid}")
        return 1
    merged[wid]["status"] = status
    write_warnings(merged)
    print(f"{wid} -> {status}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.core.coherence")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    for st in ("dismiss", "fixed", "noted"):
        sp = sub.add_parser(st)
        sp.add_argument("id")
    args = p.parse_args(argv)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd in _STATUS_MAP:
        return cmd_set_status(args.id, _STATUS_MAP[args.cmd])
    return 1


if __name__ == "__main__":
    sys.exit(main())

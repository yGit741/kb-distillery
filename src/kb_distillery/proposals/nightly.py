"""Tier-3 checks: nightly suggestions, one LLM batch for the whole kb.

`scan` finds cheap candidates (no model): open coherence warnings, near-duplicate page pairs (title and link overlap)
and oversized pages (> 3x the median body length). `submit` sends ONE batch (`kb_distillery.llm.submit`, backend batch
unless the caller picks another) with one request per candidate and remembers the batch under
`<kb>/.local/proposals-nightly/<batch>.json`. `collect` turns each answer into either an open proposal (producer.kind
"lint") when the model returned a concrete `edit_page` text for one of the candidate's pages, or a `suggestion`
record in `<kb>/.local/suggestions/` (no ops) that the review inbox lists. Nothing is ever applied here.
"""
from __future__ import annotations

import csv
import json
import os
import statistics

from kb_distillery import llm
from kb_distillery.proposals import service, store
from kb_distillery.proposals.model import ProposalError, new_id, now
from kb_distillery.vault import links
from kb_distillery.vault import pages as vault_pages
from kb_distillery.vault.graph import jaccard, outbound_links
from kb_distillery.vault.schema import LOCAL_DIR

BATCH_DIR = "proposals-nightly"
SUGGESTIONS = "suggestions"
OVERSIZED_FACTOR = 3
OVERLAP_MIN = 0.6
MAX_CANDIDATES = 50
PAGE_CHARS = 12000
SYSTEM = "You maintain a personal wiki. Reply with one JSON object and nothing else."


def _body(text):
    return links.body_of(text).split("## My notes", 1)[0]


def _coherence(root):
    path = os.path.join(root, "meta", "coherence-warnings.tsv")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("status") == "open" and row.get("kind") in ("internal", "external"):
                slugs = [s for s in (row.get("slugs") or "").split(",") if s]
                out.append({"kind": "coherence", "slugs": slugs, "detail": row.get("summary") or "", "key": row["id"]})
    return out


def _overlap(pages):
    out, slugs = [], sorted(pages)
    titles = {s: links.title_of(pages[s][2], s) for s in slugs}
    outs = {s: outbound_links(pages[s][2], pages[s][1]) for s in slugs}
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            t = jaccard(titles[a], titles[b])
            u = outs[a] | outs[b]
            shared = len(outs[a] & outs[b]) / len(u) if len(u) >= 3 else 0.0
            score = max(t, shared)
            if score >= OVERLAP_MIN:
                out.append({"kind": "overlap", "slugs": [a, b], "key": f"{a}|{b}",
                            "detail": f"title/link overlap {score:.2f}"})
    return out


def _oversized(pages):
    sizes = {s: len(_body(p[2])) for s, p in pages.items()}
    if len(sizes) < 3:
        return []
    med = statistics.median(sizes.values())
    return [{"kind": "oversized", "slugs": [s], "key": s,
             "detail": f"{n} characters, median is {int(med)}"} for s, n in sorted(sizes.items())
            if med and n > OVERSIZED_FACTOR * med]


def scan(root: str) -> list[dict]:
    """Candidates, cheapest first, capped at MAX_CANDIDATES; each {id, kind, slugs, detail, key}."""
    pages = vault_pages.load_wiki_pages(root)
    cands = [c for c in _coherence(root) + _overlap(pages) + _oversized(pages) if all(s in pages for s in c["slugs"])]
    cands = cands[:MAX_CANDIDATES]
    for i, c in enumerate(cands):
        c["id"] = f"c{i}"
    return cands


def prompt_for(root: str, cand: dict) -> str:
    pages = vault_pages.load_wiki_pages(root)
    shown = "\n\n".join(f"[page: {s}]\n{pages[s][2][:PAGE_CHARS]}" for s in cand["slugs"])
    return (f"Finding ({cand['kind']}): {cand['detail']}\n\n{shown}\n\n"
            "Suggest a fix. Never touch the `## My notes` section. If one concrete edit to ONE of these pages fixes it, "
            "give that page's complete new text; otherwise leave `edit` null and describe what to do. Reply as JSON:\n"
            '{"summary": "one sentence on the fix", "edit": {"slug": "page slug", "new_text": "complete page text"} or null}')


def requests_for(root: str, cands: list[dict]) -> list:
    return [llm.Request(prompt=prompt_for(root, c), id=c["id"], system=SYSTEM, model="sonnet", max_tokens=16000)
            for c in cands]


def _dir(root, name):
    d = os.path.join(root, LOCAL_DIR, name)
    os.makedirs(d, exist_ok=True)
    return d


def submit(root: str, backend: str = "batch") -> dict:
    cands = scan(root)
    if not cands:
        return {"batch": None, "candidates": 0}
    reqs = requests_for(root, cands)
    if backend == "batch":
        bid = llm.submit(reqs)
        record = {"batch": bid, "backend": backend, "submitted": now(), "candidates": cands}
        with open(os.path.join(_dir(root, BATCH_DIR), f"{bid}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=1)
        return {"batch": bid, "candidates": len(cands)}
    results = llm.run(reqs, backend=backend)
    return {"batch": None, "candidates": len(cands), "written": write(root, cands, results)}


def collect(root: str, bid: str, wait_s: int = 24 * 3600) -> dict:
    path = os.path.join(root, LOCAL_DIR, BATCH_DIR, f"{bid}.json")
    if not os.path.isfile(path):
        raise ProposalError(404, f"no nightly batch {bid!r}")
    with open(path, encoding="utf-8") as f:
        record = json.load(f)
    results = llm.collect(bid, wait_s=wait_s)
    out = write(root, record["candidates"], results)
    if any(r.ok for r in results):                     # a batch that is still running leaves its record to retry
        os.replace(path, path + ".done")
    return out


def write(root: str, cands: list[dict], results: list) -> dict:
    """Proposals (producer lint) for concrete edits, suggestion records for the rest. Returns the counts and ids."""
    by_id = {r.id: r for r in results}
    out = {"proposals": [], "suggestions": [], "failed": 0}
    seen = _seen(root)
    for c in cands:
        r = by_id.get(c["id"])
        if r is None or not r.ok:
            out["failed"] += 1
            continue
        if (c["kind"], c["key"]) in seen:               # already open as a proposal or a suggestion
            continue
        obj = llm.json_object(r.text) or {}
        summary = " ".join(str(obj.get("summary") or "").split()) or c["detail"]
        edit = obj.get("edit") if isinstance(obj.get("edit"), dict) else None
        pid = _propose(root, c, summary, edit) if edit else None
        if pid:
            out["proposals"].append(pid)
        else:
            out["suggestions"].append(_suggest(root, c, summary))
    return out


def _seen(root):
    """(kind, key) of every open lint proposal and open suggestion, so a nightly run never repeats one."""
    seen = {(r["finding"], r["key"]) for r in list_suggestions(root) if r.get("status") == "open" and r.get("key")}
    for pid in store.all_ids(root):
        p = store.load(root, pid)
        ctx = p["producer"].get("context") or {}
        if p["producer"]["kind"] == "lint" and p["status"] in ("open", "stale") and ctx.get("key"):
            seen.add((ctx.get("finding"), ctx["key"]))
    return seen


def _propose(root, c, summary, edit):
    slug, text = edit.get("slug"), edit.get("new_text")
    if slug not in c["slugs"] or not isinstance(text, str) or not text.strip():
        return None
    title = f"Suggested fix ({c['kind']}): {', '.join(c['slugs'])}"
    try:
        p = service.create(title, [{"kind": "edit_page", "slug": slug, "new_text": text, "reason": summary}],
                           producer={"kind": "lint", "instruction": summary,
                                     "context": {"finding": c["kind"], "key": c["key"], "slugs": c["slugs"],
                                                "detail": c["detail"]}},
                           note="nightly suggestion", root=root)
    except Exception:  # noqa: BLE001  (fall back to a suggestion; one bad candidate never aborts the run)
        return None
    return p["id"]


def _suggest(root, c, summary):
    sid = new_id()
    rec = {"id": sid, "kind": "suggestion", "finding": c["kind"], "key": c.get("key", ""), "slugs": c["slugs"],
           "detail": c["detail"], "summary": summary, "created": now(), "status": "open"}
    with open(os.path.join(_dir(root, SUGGESTIONS), f"{sid}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return sid


def list_suggestions(root: str) -> list[dict]:
    d = os.path.join(root, LOCAL_DIR, SUGGESTIONS)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            with open(os.path.join(d, n), encoding="utf-8") as f:
                out.append(json.load(f))
    return sorted(out, key=lambda r: r["created"], reverse=True)

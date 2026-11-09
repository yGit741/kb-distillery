"""Tier-2 checks: a scoped semantic review of a proposal revision (one model call per touched page).

Scope = the touched pages plus their direct graph neighbours (pages they link to, pages that link to them), capped at
`scope_cap()` pages, so the cost scales with the change and never with the kb. Each call sees the after-text of that
page's hunks and short excerpts of its neighbours and answers with strict JSON findings
{code: contradiction|unsupported|duplicate|overclaim, severity: warning|info, message, hunk_id, evidence,
neighbour_slug}. Findings on an unknown hunk id are dropped; severity is never `error`, so tier 2 never blocks apply.
The kb's open internal coherence warnings (0 LLM, meta/coherence-warnings.tsv) on a touched page ride along as
`coherence` findings. The set replaces the revision's previous tier-2 findings.
"""
from __future__ import annotations

import csv
import os

from kb_distillery import llm
from kb_distillery.proposals import store
from kb_distillery.proposals.checks import finding
from kb_distillery.proposals.model import ProposalError, now
from kb_distillery.vault import links
from kb_distillery.vault import pages as vault_pages
from kb_distillery.vault.graph import outbound_links

CODES = ("contradiction", "unsupported", "duplicate", "overclaim")
SEVERITIES = ("warning", "info")
DEFAULT_CAP = 20
ENV_CAP = "KB_PROPOSAL_SEMANTIC_CAP"
EXCERPT = 700                       # characters of a neighbour's body shown to the model
HUNK_CHARS = 3000                   # per hunk after-text

SYSTEM = ("You review a proposed edit to a personal wiki against the pages it touches. Reply with one JSON object "
          "and nothing else.")


def scope_cap() -> int:
    try:
        return max(1, int(os.environ.get(ENV_CAP) or DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def _out(pages, slug):
    """Pages `slug` links to; `## My notes` links are the owner's and do not make a neighbour."""
    _rel, fm, text = pages[slug]
    return {t for t in outbound_links(text.split("## My notes", 1)[0], fm) if t in pages and t != slug}


def neighbours(pages: dict, slug: str) -> list[str]:
    """Direct graph neighbours of `slug` (links out, links in), sorted; only pages that exist."""
    if slug not in pages:
        return []
    return sorted(_out(pages, slug) | {s for s in pages if s != slug and slug in _out(pages, s)})


def select_scope(pages: dict, touched: list[str], cap: int | None = None) -> tuple[list[str], dict]:
    """(scope, {touched slug: its neighbours inside the scope}); touched pages first, then neighbours, capped."""
    cap = cap or scope_cap()
    per = {s: neighbours(pages, s) for s in touched}
    scope = list(touched)[:cap]
    for s in touched:
        for n in per[s]:
            if len(scope) >= cap:
                break
            if n not in scope and n not in touched:
                scope.append(n)
    return scope, {s: [n for n in per[s] if n in scope] for s in touched}


def _excerpt(pages, slug):
    _rel, fm, text = pages[slug]
    body = links.body_of(text)
    body = body.split("## My notes", 1)[0].strip()
    desc = str((fm or {}).get("description") or "").strip()
    return (f"description: {desc}\n" if desc else "") + body[:EXCERPT]


def build_prompt(slug: str, hunks: list[dict], near: list[str], pages: dict) -> str:
    changed = "\n\n".join(f"[hunk_id: {h['id']}]\n{h['after'][:HUNK_CHARS]}" for h in hunks)
    context = "\n\n".join(f"[page: {n}]\n{_excerpt(pages, n)}" for n in near) or "(no neighbouring pages)"
    return (
        f"The page `{slug}` is being edited. The new text of each changed passage:\n\n{changed}\n\n"
        f"Neighbouring pages it links to or that link to it:\n\n{context}\n\n"
        "Find only real problems the edit introduces against those pages. Codes: contradiction (a new claim conflicts "
        "with a neighbour), unsupported (a new claim no neighbour backs up), duplicate (it restates a neighbour), "
        "overclaim (stronger than the neighbours support). Reply as JSON:\n"
        '{"findings": [{"code": "contradiction|unsupported|duplicate|overclaim", "severity": "warning|info", '
        '"message": "one sentence", "hunk_id": "one of the ids above", "evidence": "short quote from the neighbour", '
        '"neighbour_slug": "the neighbour page or empty"}]}\n'
        'Use {"findings": []} when there is nothing to report.')


def parse(text: str, slug: str, hunk_ids: set, neighbour_slugs: set) -> list[dict]:
    """Valid findings from a model reply: unknown hunk ids, codes and malformed rows are dropped."""
    obj = llm.json_object(text) or {}
    rows = obj.get("findings")
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("hunk_id") not in hunk_ids or r.get("code") not in CODES:
            continue
        msg = " ".join(str(r.get("message") or "").split())
        if not msg:
            continue
        f = finding(r.get("severity") if r.get("severity") in SEVERITIES else "warning", r["code"], msg, slug,
                    r["hunk_id"], source="tier2")
        ev, nb = " ".join(str(r.get("evidence") or "").split())[:300], str(r.get("neighbour_slug") or "")
        if ev:
            f["evidence"] = ev
        if nb in neighbour_slugs:
            f["neighbour_slug"] = nb
        out.append(f)
    return out


def coherence_findings(root: str, touched: list[str], hunks: list[dict]) -> list[dict]:
    """Open internal contradictions already reported by the 0-LLM coherence lint that involve a touched page."""
    path = os.path.join(root, "meta", "coherence-warnings.tsv")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("status") != "open" or row.get("kind") != "internal":
                continue
            slugs = [s for s in (row.get("slugs") or "").split(",") if s]
            for s in touched:
                if s in slugs:
                    first = next((h["id"] for h in hunks if h["slug"] == s), None)
                    other = next((x for x in slugs if x != s), "")
                    f2 = finding("warning", "coherence", row.get("summary") or "open coherence warning", s, first,
                                 source="tier2")
                    if other:
                        f2["neighbour_slug"] = other
                    out.append(f2)
    return out


def check(root: str, proposal: dict, backend: str | None = None) -> list[dict]:
    """Tier-2 findings for the proposal's current revision (no persistence)."""
    rev = proposal["revisions"][proposal["current"]]
    hunks = rev["hunks"]
    by_slug: dict[str, list[dict]] = {}
    for h in hunks:
        by_slug.setdefault(h["slug"], []).append(h)
    pages = vault_pages.load_wiki_pages(root)
    cap = scope_cap()
    scope, near = select_scope(pages, [s for s in by_slug if s in pages], cap)
    touched = list(by_slug)
    by_slug = {s: hs for s, hs in by_slug.items() if s in scope or s not in pages}      # the cap bounds the calls too
    out: list[dict] = []
    for slug, hs in by_slug.items():
        res = llm.ask(build_prompt(slug, hs, near.get(slug, []), pages), backend=backend, system=SYSTEM,
                      model="sonnet", run_kw={"wait_s": 600, "poll_every": 10})
        if not res.ok:
            raise ProposalError(502, f"the semantic check failed on {slug}: {res.error[:200]}")
        out += parse(res.text, slug, {h["id"] for h in hs}, set(near.get(slug, [])))
    return out + coherence_findings(root, touched, hunks)


def run(root: str, proposal_id: str, backend: str | None = None) -> dict:
    """Run tier 2 on the proposal's current revision, replace `checks.tier2` and persist. Returns the findings."""
    p = store.load(root, proposal_id)
    if p["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {p['status']}")
    try:
        found = check(root, p, backend)
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    n = p["revisions"][p["current"]]["n"]
    fresh = store.load(root, proposal_id)                    # the call was slow: keep decisions/revisions made meanwhile
    if fresh["revisions"][fresh["current"]]["n"] != n:
        raise ProposalError(409, "the proposal got a new revision while the check ran; run it again")
    fresh["checks"]["tier2"] = found
    fresh["updated"] = now()
    store.save(root, fresh)
    return {"findings": found, "revision": n}

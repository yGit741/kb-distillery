"""Render wiki markdown into session staging/ from claims + plan."""
import json
import os
import sys

from kb.core.schema import TOPIC_SLUGS

from .paths import session_dir, load_session, wiki_slugs, resolve_wikilink_slug
from .schemas import validate_claims, validate_plan


def _theme_areas(areas):
    out = []
    for a in areas or []:
        bare = a[6:] if isinstance(a, str) and a.startswith("theme-") else a
        if bare in TOPIC_SLUGS and bare not in out:
            out.append(bare)
    return out[:5]


def _equations_block(equations):
    lines = []
    for eq in equations:
        latex = eq.get("latex", "").strip()
        if not latex:
            continue
        label = eq.get("label", "")
        if label:
            lines.append(f"**{label}:**")
        if "\n" in latex or len(latex) > 80:
            lines.append(f"$${latex}$$")
        else:
            lines.append(f"${latex}$")
        vars_ = eq.get("variables") or {}
        if vars_:
            vline = ", ".join(f"${k}$: {v}" for k, v in vars_.items())
            lines.append(f"Variables: {vline}")
        lines.append("")
    return "\n".join(lines) if lines else "—"


def run_draft(sha):
    session = load_session(sha)
    sdir = session_dir(sha)

    with open(os.path.join(sdir, "claims.json"), encoding="utf-8") as f:
        claims = json.load(f)
    with open(os.path.join(sdir, "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    validate_claims(claims)
    validate_plan(plan)

    slug = plan["wiki_slug"]
    known = wiki_slugs()
    areas = _theme_areas(plan.get("areas") or claims.get("concepts", []))
    if not areas:
        areas = ["learning-theory"]
    link_slugs = plan.get("link_slugs") or list((plan.get("link_existing") or {}).values())
    area_links = [s for a in areas if (s := resolve_wikilink_slug(a, known))]
    related = list(dict.fromkeys([*link_slugs, *(plan.get("link_existing") or {}).values(), *area_links]))[:8]
    concepts_links = ", ".join(f"[[{s}]]" for s in related[:5])

    results = claims.get("results") or []
    main_result = results[0] if results else ""
    extra_results = "\n".join(f"- {r}" for r in results[1:3])

    year = claims.get("year") or ""
    authors = claims.get("authors") or []
    authors_yaml = "[" + ", ".join(authors) + "]" if authors else "[]"

    person = plan.get("person") or claims.get("person")
    recommended_by = f"[{person}]" if person else "[]"
    links_person = f"- Person: [[{person}]]\n" if person else ""

    digestion = plan.get("depth") or session.get("depth") or "full"
    paper_status = "digested" if digestion in ("easy", "full", "deep") else "to-read"     # listed → to-read
    raws = plan.get("raws") or [claims["raw"]]
    raw_field = raws[0] if len(raws) == 1 else "[" + ", ".join(raws) + "]"

    scope = session.get("scope") or {}
    book = plan.get("book") if plan.get("type") == "part" else None
    if book:
        a, b = scope["pages"]
        section = (scope.get("label") or "").replace("#", "").replace(":", " –")
        head = (f"type: part\nlayer: source\nbook: {book}\n", f"section: {section}\nsection_pages: {a}-{b}\n",
                f"\n> Part of [[{book}]] · pp. {a}–{b} · {section}\n")
        plan["areas_resolved"] = areas
    elif plan.get("hub"):
        hub_key = "series" if plan["hub"].startswith("series-") else "course"
        head = (f"type: {plan.get('type') or 'paper'}\nlayer: source\n{hub_key}: {plan['hub']}\n", "",
                f"\n> Row {plan.get('hub_row')} of [[{plan['hub']}]]\n")
    else:
        head = (f"type: {plan.get('type') or 'paper'}\nlayer: source\n", "", "")

    body = f"""---
{head[0]}authors: {authors_yaml}
year: {year}
area: [{", ".join(areas)}]
status: {paper_status}
depth: {digestion}
raw: {raw_field}
{head[1]}citekey: {claims.get("citekey") or ""}
url: {claims.get("url") or ""}
recommended_by: {recommended_by}
discussed_with: []
---

# {claims["title"]}
{head[2]}
**Problem:** {claims["problem"]}

**Main result:** {main_result}

## Setup & assumptions

{claims.get("method", "")}

## Proof idea (sketch only)

{extra_results}

## Key equations

{_equations_block(claims.get("equations", []))}

## Takeaways for my thesis

- {results[-1] if len(results) > 1 else main_result}
- Concepts: {concepts_links}

## Links out

- Concepts: {concepts_links}
{links_person}"""

    staging = os.path.join(sdir, "staging")
    os.makedirs(staging, exist_ok=True)
    out = os.path.join(staging, f"{slug}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)

    preview = os.path.join(sdir, "draft.md")
    with open(preview, "w", encoding="utf-8") as f:
        f.write(body)

    for q in plan.get("question_updates", []):
        if q.get("action") != "create":
            continue
        qslug = q["slug"]
        qfile = f"{qslug}.md"
        qpath = os.path.join(staging, qfile)
        if os.path.isfile(qpath):
            continue
        qbody = f"""---
type: question
layer: concept
area: [{", ".join(areas[:3])}]
status: open
priority: med
discussed_with: []
---

# {q.get("text", qslug)}

**Question:** {q.get("text", "")}

## Why I care

Spawned during ingest of [[{slug}]].

## What I know so far
-

## Hypotheses
-

## Papers / concepts to read
- [[{slug}]]
"""
        with open(qpath, "w", encoding="utf-8") as f:
            f.write(qbody)
        q["staging_file"] = qfile

    with open(os.path.join(sdir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")

    print(f"draft → staging/{slug}.md")
    return out

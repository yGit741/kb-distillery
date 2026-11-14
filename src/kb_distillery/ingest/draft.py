"""Render wiki markdown into session staging/ from claims + plan."""
import json
import os
import sys

from kb_distillery.config import pages as page_conventions
from kb_distillery.vault import frontmatter, links
from kb_distillery.vault.schema import TOPIC_SLUGS
from kb_distillery.lint.lint import QUESTION_TITLE_MAX

from .fm_merge import merge_frontmatter
from .paths import ROOT, session_dir, load_session, wiki_titles, resolve_wikilink_slug
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
        mark = (eq.get("mark") or "").strip()                       # an unsettled formula keeps its mark link
        if "\n" in latex or len(latex) > 80:
            lines.append(f"$${latex}$$")
            if mark:
                lines += ["", mark]
        else:
            lines.append(f"${latex}$" + (f" {mark}" if mark else ""))
        vars_ = eq.get("variables") or {}
        if vars_:
            vline = ", ".join(f"${k}$: {v}" for k, v in vars_.items())
            lines.append(f"Variables: {vline}")
        lines.append("")
    return "\n".join(lines) if lines else "—"


def _exercises_block(claims):
    """`## Exercises` (a book part's exercises, in full) and `## Notes and references`, each only when claims has it."""
    out = []
    rows = [x for x in claims.get("exercises") or [] if (x.get("statement") or "").strip()]
    if rows:
        out.append("## Exercises\n")
        for x in rows:
            label = (x.get("label") or "").strip()
            out.append((f"**{label}.** " if label else "") + x["statement"].strip() + "\n")
    if (claims.get("notes") or "").strip():
        out.append("## Notes and references\n\n" + claims["notes"].strip() + "\n")
    return ("\n".join(out) + "\n") if out else ""


def _title_yaml(title):
    """`title: "…"` plus its newline, or '' when the title is the `# ` heading the page is written with."""
    line = frontmatter.title_line(title)
    return line + "\n" if line else ""


def question_name(text, limit=QUESTION_TITLE_MAX):
    """The H1 of a q- stub: the question's short name. Lint caps it at QUESTION_TITLE_MAX chars, so a long
    `open_questions` sentence is clipped at a word boundary — the full statement goes in `## Question`."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def run_draft(sha):
    session = load_session(sha)
    sdir = session_dir(sha)

    with open(os.path.join(sdir, "claims.json"), encoding="utf-8") as f:
        claims = json.load(f)
    with open(os.path.join(sdir, "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    validate_plan(plan)
    validate_claims(claims, page_type=plan["type"])

    slug = plan["wiki_slug"]
    known = wiki_titles()
    self_title = links.shown_title(claims.get("title") or slug)
    existing = None                       # deepening a page in place: its frontmatter survives (merge below)
    existing_path = os.path.join(ROOT, "wiki", f"{slug}.md")
    if os.path.isfile(existing_path):
        with open(existing_path, encoding="utf-8") as f:
            existing = f.read()
    areas = _theme_areas(plan.get("areas") or claims.get("concepts", []))
    if not areas:
        areas = [] if existing else ["learning-theory"]     # never file an existing page under a guessed topic
    link_slugs = plan.get("link_slugs") or list((plan.get("link_existing") or {}).values())
    area_links = [s for a in areas if (s := resolve_wikilink_slug(a, known))]
    related = list(dict.fromkeys([*link_slugs, *(plan.get("link_existing") or {}).values(), *area_links]))[:8]
    concepts_links = ", ".join(links.page_link(s, known) for s in related[:5])

    results = claims.get("results") or []
    main_result = results[0] if results else ""
    extra_results = "\n".join(f"- {r}" for r in results[1:])

    year = claims.get("year") or ""
    authors = claims.get("authors") or []
    authors_yaml = "[" + ", ".join(authors) + "]" if authors else "[]"

    person = plan.get("person") or claims.get("person")
    recommended_by = f"[{person}]" if person else "[]"
    links_person = f"- Person: {links.page_link(person, known)}\n" if person else ""

    digestion = plan.get("depth") or session.get("depth") or "full"
    paper_status = "digested" if digestion in ("easy", "full", "deep") else "to-read"     # listed → to-read
    raws = plan.get("raws") or [claims["raw"]]
    raw_field = raws[0] if len(raws) == 1 else "[" + ", ".join(raws) + "]"

    title_fm = _title_yaml(claims["title"])
    draft_fm = "status: draft\n" if digestion == "listed" else ""             # OKF lifecycle: a listed stub is a draft
    scope = session.get("scope") or {}
    book = plan.get("book") if plan.get("type") == "part" else None
    if book:
        a, b = scope["pages"]
        section = (scope.get("label") or "").replace("#", "").replace(":", " –")
        head = (f"type: part\nlayer: source\n{title_fm}book: {book}\n", f"section: {section}\nsection_pages: {a}-{b}\n",
                f"\n> Part of {links.page_link(book, known)} · pp. {a}–{b} · {section}\n")
        plan["areas_resolved"] = areas
    elif plan.get("hub"):
        hub_key = "series" if plan["hub"].startswith("series-") else "course"
        head = (f"type: {plan.get('type') or 'paper'}\nlayer: source\n{title_fm}{hub_key}: {plan['hub']}\n", "",
                f"\n> Row {plan.get('hub_row')} of {links.page_link(plan['hub'], known)}\n")
    else:
        head = (f"type: {plan.get('type') or 'paper'}\nlayer: source\n{title_fm}", "", "")

    body = f"""---
{head[0]}authors: {authors_yaml}
year: {year}
area: [{", ".join(areas)}]
maturity: {paper_status}
{draft_fm}depth: {digestion}
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

## {page_conventions.takeaways_heading()}

- {results[-1] if len(results) > 1 else main_result}
- Concepts: {concepts_links}

{_exercises_block(claims)}## Links out

- Concepts: {concepts_links}
{links_person}"""

    if existing:
        body = merge_frontmatter(existing, body)

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
{_title_yaml(question_name(q.get("text") or qslug))}area: [{", ".join(areas[:3])}]
maturity: open
priority: med
discussed_with: []
---

# {question_name(q.get("text") or qslug)}

## Question

{q.get("text", "")}

## Why I care

Spawned during ingest of {links.link(slug, self_title)}.

## What I know so far
-

## Hypotheses
-

## Papers / concepts to read
- {links.link(slug, self_title)}
"""
        with open(qpath, "w", encoding="utf-8") as f:
            f.write(qbody)
        q["staging_file"] = qfile

    with open(os.path.join(sdir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")

    print(f"draft → staging/{slug}.md")
    return out

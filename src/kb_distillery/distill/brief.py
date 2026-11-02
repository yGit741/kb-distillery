"""Render distilled-think wiki pages."""
from datetime import datetime, timezone

from kb_distillery.core import frontmatter
from .paths import think_cite


def render_summary(plan, think_text, prior_summary=""):
    if prior_summary and prior_summary.strip():
        return prior_summary.strip()

    touches = plan.get("touches") or []
    themes = plan.get("themes_detected") or []
    not_promoted = plan.get("not_promoted") or []
    lines = []

    blob = (think_text or "").strip()
    if blob:
        para = blob.split("\n\n")[0].replace("\n", " ").strip()
        if len(para) > 40:
            lines.append(para[:600] + ("…" if len(para) > 600 else ""))

    if themes:
        theme_links = ", ".join(f"[[theme-{t}]]" for t in themes[:5])
        lines.append(
            f"This deliberation connects to {theme_links}. "
            "Theme page threads may be updated on propagate."
        )

    q = [t for t in touches if t.startswith("q-")][:4]
    if q:
        lines.append("Questions in play: " + ", ".join(f"[[{x}]]" for x in q) + ".")

    if not_promoted:
        lines.append("Some notes should stay in think/ only — see Not promoting.")

    if not lines:
        lines.append("Add prose here during review, or write in think/ and re-run propose.")

    return "\n\n".join(lines)


def render_proposals_table(proposals):
    if not proposals:
        return "_No proposals — nothing to propagate._"
    rows = [
        "| # | Target | Action | Rationale |",
        "|---|--------|--------|-----------|",
    ]
    for i, p in enumerate(proposals, 1):
        target = p.get("target", "").replace("wiki/", "").replace(".md", "")
        rows.append(
            f"| {i} | [[{target}]] | {p.get('action', '')} | {(p.get('rationale') or '')[:80]} |"
        )
    return "\n".join(rows)


def render_distilled_page(plan, think_rel, summary, applied=False):
    ts = plan.get("distilled_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = think_basename_display(think_rel)
    status = "applied" if applied else "review"
    footer = f"\n\n_Applied {ts[:10]}._\n" if applied else ""
    return f"""---
type: distilled-think
layer: concept
{frontmatter.title_line("Distilled · " + title)}
maturity: {status}
{frontmatter.sources_line([think_cite(think_rel)])}
distilled_at: {ts}
---

# Distilled · {title}

## Summary

{summary.strip()}{footer}

## Proposed propagation

{render_proposals_table(plan.get("proposals") or [])}

## Not promoting

{render_not_promoted(plan.get("not_promoted") or [])}
"""


def think_basename_display(think_rel):
    import os
    base = os.path.basename(think_rel)
    return base[:-3].replace("-", " ").title() if base.endswith(".md") else base


def render_not_promoted(items):
    if not items:
        return "—"
    return "\n".join(f"- {x}" for x in items)

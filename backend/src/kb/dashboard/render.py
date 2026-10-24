"""Render dashboard HTML from a health snapshot."""
import html
import json
import os

from kb.core.health import CLUSTERS, METRICS, format_metric_value
from kb.dashboard.shell import render_nav

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")


def render_page(snapshot):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    cards = []
    for cluster_id, cluster_title in CLUSTERS:
        rows = []
        for metric_id, meta in METRICS.items():
            if meta["cluster"] != cluster_id:
                continue
            value = snapshot["values"][metric_id]
            status = snapshot["statuses"][metric_id]
            display = format_metric_value(metric_id, value)
            rows.append(
                f'<div class="metric-row" data-status="{status}">'
                f'<span class="metric-label">{html.escape(meta["label"])}</span>'
                f'<span class="metric-value">{html.escape(display)}</span>'
                f'<span class="metric-pill">{status}</span>'
                f'<button type="button" class="help-btn" aria-label="Help" '
                f'data-help="{html.escape(meta["help"])}">?</button>'
                f"</div>"
            )
        cards.append(
            f'<section class="card" data-cluster="{cluster_id}"><h2>{html.escape(cluster_title)}</h2>{"".join(rows)}</section>'
        )

    extra = ""
    if snapshot.get("compression_pct"):
        extra = (
            f'<p class="subtle">Wiki is ~{snapshot["compression_pct"]}% of estimated raw tokens '
            f'({snapshot["wiki_pages"]} pages · {snapshot["raw_files"]} raw files)</p>'
        )

    orphans = snapshot.get("orphan_slugs") or []
    orphan_note = ""
    if orphans:
        orphan_note = (
            '<details class="orphan-list"><summary>Top orphan slugs</summary><ul>'
            + "".join(f"<li><code>{html.escape(s)}</code></li>" for s in orphans)
            + "</ul></details>"
        )

    return (
        template.replace("{{NAV}}", render_nav("health"))
        .replace("{{GENERATED_AT}}", html.escape(snapshot["generated_at"]))
        .replace("{{CARDS}}", "\n".join(cards))
        .replace("{{EXTRA}}", extra)
        .replace("{{ORPHAN_NOTE}}", orphan_note)
        .replace("{{SNAPSHOT_JSON}}", json.dumps(snapshot))
    )

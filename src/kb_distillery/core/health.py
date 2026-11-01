"""Vault health metrics — shared by lint --health and kb_distillery.dashboard."""
import os
import time
from datetime import datetime, timezone
from kb_distillery.core.links import WIKILINK_TARGET

LINK = WIKILINK_TARGET

ORPHAN_EXCLUDE = frozenset({"AGENTS", "log", "thesis"})

METRICS = {
    "errors": {
        "label": "Errors",
        "cluster": "integrity",
        "help": "Schema violations that must be zero before commit.",
        "format": "int",
    },
    "warnings": {
        "label": "Warnings",
        "cluster": "integrity",
        "help": "Non-blocking issues (broken wikilinks, inbox files) worth fixing soon.",
        "format": "int",
    },
    "hooks": {
        "label": "Guard hooks",
        "cluster": "integrity",
        "help": "Whether Cursor and Claude guard hooks point at the write guard (kb_distillery.git.guard).",
        "format": "hooks",
    },
    "broken": {
        "label": "Broken links",
        "cluster": "knowledge",
        "help": "Wikilinks in wiki pages that resolve to no existing slug.",
        "format": "int",
    },
    "orphans": {
        "label": "Orphans",
        "cluster": "knowledge",
        "help": "Wiki pages no other page links to (excluding MOCs and meta slugs).",
        "format": "int",
    },
    "queued": {
        "label": "Queued raw",
        "cluster": "knowledge",
        "help": "Raw files in corpus.tsv marked queued — not yet digested.",
        "format": "int",
    },
    "coherence_internal": {
        "label": "Coherence internal",
        "cluster": "coherence",
        "help": "Open semantic lint hits (bad ingestion) — fix required.",
        "format": "int",
    },
    "coherence_external": {
        "label": "Coherence external",
        "cluster": "coherence",
        "help": "Open paper-vs-paper tensions — note in Connections.",
        "format": "int",
    },
    "coherence_cosmetic": {
        "label": "Coherence cosmetic",
        "cluster": "coherence",
        "help": "Open graph-hygiene hits (asymmetric MOC links, near-duplicates).",
        "format": "int",
    },
    "coherence_open": {
        "label": "Coherence open",
        "cluster": "coherence",
        "help": "Total open semantic coherence warnings across all kinds.",
        "format": "int",
    },
    "lint_ms": {
        "label": "Lint total",
        "cluster": "performance",
        "help": "Wall-clock time for the last full health collection run.",
        "format": "ms",
    },
    "sha1_ms": {
        "label": "SHA1 phase",
        "cluster": "performance",
        "help": "Time spent hashing raw files during manifest reconcile.",
        "format": "ms",
    },
    "wiki_ms": {
        "label": "Wiki phase",
        "cluster": "performance",
        "help": "Time spent reading and parsing all wiki frontmatter.",
        "format": "ms",
    },
    "links_ms": {
        "label": "Links phase",
        "cluster": "performance",
        "help": "Time spent scanning wikilinks across all pages.",
        "format": "ms",
    },
    "raw_tokens": {
        "label": "Raw tokens",
        "cluster": "tokens",
        "help": "Estimated tokens across all of raw/ if fully read (~bytes÷4 per file).",
        "format": "tokens",
    },
    "wiki_tokens": {
        "label": "Wiki tokens",
        "cluster": "tokens",
        "help": "Estimated tokens in all wiki page bodies (~chars÷4).",
        "format": "tokens",
    },
    "index_savings_pct": {
        "label": "Index savings",
        "cluster": "tokens",
        "help": "Percent of wiki tokens you skip by reading index.md first instead of every page.",
        "format": "pct",
    },
    "queued_mb": {
        "label": "Queued MB",
        "cluster": "tokens",
        "help": "Megabytes of queued raw PDFs — proxy for future ingest/extract cost.",
        "format": "mb",
    },
}

CLUSTERS = [
    ("integrity", "Integrity"),
    ("coherence", "Coherence"),
    ("knowledge", "Knowledge"),
    ("performance", "Performance"),
    ("tokens", "Token efficiency"),
]

LINT_CATEGORIES = ("coherence", "wiki", "raw", "inbox", "corpus", "root", "other")


def estimate_tokens(text):
    return len(text) // 4


def wiki_body(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def format_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def format_metric_value(metric_id, value):
    fmt = METRICS[metric_id]["format"]
    if fmt == "int":
        return str(value)
    if fmt == "ms":
        if value >= 1000:
            return f"{value / 1000:.1f}s"
        return f"{int(value)}ms"
    if fmt == "tokens":
        return format_tokens(value)
    if fmt == "pct":
        return f"{value}%"
    if fmt == "mb":
        return f"{value:.1f}MB"
    if fmt == "hooks":
        return value if isinstance(value, str) else ("ok" if value else "MISS")
    return str(value)


def compute_in_degree(pages):
    degree = {slug: 0 for slug in pages}
    for _slug, (_rel, _fm, text) in pages.items():
        for target in LINK.findall(text):
            target = target.strip()
            if target in degree:
                degree[target] += 1
    return degree


def is_orphan_slug(slug):
    if slug.startswith(("theme-", "distilled-think-", "scope-")):
        return False
    return slug not in ORPHAN_EXCLUDE


def compute_orphans(pages):
    degree = compute_in_degree(pages)
    return sorted(slug for slug, n in degree.items() if n == 0 and is_orphan_slug(slug))


def in_degree_buckets(degree):
    buckets = {"0": 0, "1": 0, "2+": 0}
    for slug, n in degree.items():
        if slug.startswith(("theme-", "distilled-think-", "scope-")) or slug in ORPHAN_EXCLUDE:
            continue
        if n == 0:
            buckets["0"] += 1
        elif n == 1:
            buckets["1"] += 1
        else:
            buckets["2+"] += 1
    return buckets


def compute_raw_tokens(root, raw_files):
    total = 0
    for rel in raw_files:
        path = os.path.join(root, rel)
        try:
            total += os.path.getsize(path) // 4
        except OSError:
            pass
    return total


def compute_wiki_tokens(pages):
    total = 0
    for _slug, (_rel, _fm, text) in pages.items():
        total += estimate_tokens(wiki_body(text))
    return total


def compute_index_tokens(root):
    path = os.path.join(root, "index.md")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            return estimate_tokens(f.read())
    except OSError:
        return 0


def index_savings_pct(wiki_tokens, index_tokens):
    if wiki_tokens <= 0:
        return 0
    return round(100 * (1 - index_tokens / wiki_tokens))


def compute_queued_mb(root, rows):
    total = 0
    for path, row in rows.items():
        if row.get("disposition") != "queued":
            continue
        full = os.path.join(root, path)
        try:
            total += os.path.getsize(full)
        except OSError:
            pass
    return total / (1024 * 1024)


def compression_pct(raw_tokens, wiki_tokens):
    if raw_tokens <= 0:
        return 0
    return round(100 * wiki_tokens / raw_tokens)


def lint_issue_field(issue):
    return issue.split(":", 1)[0].strip()


def lint_issue_category(field):
    if field == "vault-root":
        return "root"
    if field == "coherence":
        return "coherence"
    if "inbox" in field:
        return "inbox"
    if field.startswith("wiki/"):
        return "wiki"
    if field.startswith("raw/"):
        return "raw"
    if "corpus" in field:
        return "corpus"
    return "other"


def bucket_lint_issues(errors, warnings):
    buckets = {
        "errors": {cat: 0 for cat in LINT_CATEGORIES},
        "warnings": {cat: 0 for cat in LINT_CATEGORIES},
    }
    for issue in errors:
        buckets["errors"][lint_issue_category(lint_issue_field(issue))] += 1
    for issue in warnings:
        buckets["warnings"][lint_issue_category(lint_issue_field(issue))] += 1
    return buckets


def summarize_coherence(merged):
    """Summarize coherence manifest rows for dashboard metrics and graphs."""
    merged = merged or {}
    by_kind = {"internal": 0, "external": 0, "cosmetic": 0}
    by_status = {"open": 0, "fixed": 0, "noted": 0, "dismissed": 0}
    for row in merged.values():
        status = row.get("status", "open")
        if status in by_status:
            by_status[status] += 1
        if status != "open":
            continue
        kind = row.get("kind", "")
        if kind in by_kind:
            by_kind[kind] += 1
    by_kind["total"] = sum(by_kind.values())
    return {"by_kind": by_kind, "by_status": by_status}


def metric_status(metric_id, value, snapshot):
    if metric_id == "errors":
        return "ok" if value == 0 else "bad"
    if metric_id == "warnings":
        return "ok" if value == 0 else "warn"
    if metric_id == "hooks":
        return "ok" if snapshot.get("hooks_ok") else "bad"
    if metric_id == "broken":
        return "ok" if value == 0 else "warn"
    if metric_id == "orphans":
        return "ok" if value < 20 else "warn"
    if metric_id == "queued":
        return "ok" if value == 0 else "warn"
    if metric_id == "index_savings_pct":
        return "ok" if value >= 80 else "warn"
    if metric_id in ("lint_ms", "sha1_ms", "wiki_ms", "links_ms"):
        return "ok"
    if metric_id in ("raw_tokens", "wiki_tokens", "queued_mb"):
        return "ok"
    if metric_id in ("coherence_internal", "coherence_external", "coherence_open"):
        return "ok" if value == 0 else "warn"
    if metric_id == "coherence_cosmetic":
        return "ok"
    return "ok"


def build_snapshot(
    *,
    pages,
    raw_files,
    rows,
    broken,
    errors,
    warnings,
    inbox_count,
    queued_count,
    hooks_status,
    hooks_ok,
    coherence_merged=None,
    timings,
):
    coherence_summary = summarize_coherence(coherence_merged)
    coherence_by_kind = coherence_summary["by_kind"]
    coherence_internal = coherence_by_kind["internal"]
    coherence_external = coherence_by_kind["external"]
    coherence_cosmetic = coherence_by_kind["cosmetic"]
    coherence_open = coherence_by_kind["total"]

    wiki_tokens = compute_wiki_tokens(pages)
    index_tokens = compute_index_tokens(timings.get("root", "."))
    raw_tokens = compute_raw_tokens(timings.get("root", "."), raw_files)
    orphans = compute_orphans(pages)
    degree = compute_in_degree(pages)

    values = {
        "errors": len(errors),
        "warnings": len(warnings),
        "hooks": hooks_status,
        "broken": broken,
        "orphans": len(orphans),
        "queued": queued_count,
        "coherence_internal": coherence_internal,
        "coherence_external": coherence_external,
        "coherence_cosmetic": coherence_cosmetic,
        "coherence_open": coherence_open,
        "lint_ms": timings.get("lint_ms", 0),
        "sha1_ms": timings.get("sha1_ms", 0),
        "wiki_ms": timings.get("wiki_ms", 0),
        "links_ms": timings.get("links_ms", 0),
        "raw_tokens": raw_tokens,
        "wiki_tokens": wiki_tokens,
        "index_savings_pct": index_savings_pct(wiki_tokens, index_tokens),
        "queued_mb": compute_queued_mb(timings.get("root", "."), rows),
    }

    statuses = {mid: metric_status(mid, values[mid], {"hooks_ok": hooks_ok})
                for mid in METRICS}

    lint_total = max(values["lint_ms"], 1)
    phase_pct = {
        "sha1": round(100 * values["sha1_ms"] / lint_total),
        "wiki": round(100 * values["wiki_ms"] / lint_total),
        "links": round(100 * values["links_ms"] / lint_total),
    }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "values": values,
        "statuses": statuses,
        "hooks_ok": hooks_ok,
        "inbox_count": inbox_count,
        "wiki_pages": len(pages),
        "raw_files": len(raw_files),
        "orphan_slugs": orphans[:15],
        "compression_pct": compression_pct(raw_tokens, wiki_tokens),
        "graphs": {
            "in_degree": in_degree_buckets(degree),
            "lint_phases_ms": {
                "sha1": values["sha1_ms"],
                "wiki": values["wiki_ms"],
                "links": values["links_ms"],
            },
            "lint_phases_pct": phase_pct,
            "coherence_by_kind": {
                "internal": coherence_internal,
                "external": coherence_external,
                "cosmetic": coherence_cosmetic,
            },
            "coherence_by_status": coherence_summary["by_status"],
            "lint_by_category": bucket_lint_issues(errors, warnings),
        },
    }


def print_health_terminal(snapshot):
    v = snapshot["values"]
    print(f"integrity   errors={v['errors']}  warnings={v['warnings']}  hooks={v['hooks']}")
    print(f"coherence   internal={v.get('coherence_internal', 0)}  external={v.get('coherence_external', 0)}  "
          f"cosmetic={v.get('coherence_cosmetic', 0)}  open={v.get('coherence_open', 0)}")
    line = f"knowledge   broken={v['broken']}  orphans={v['orphans']}  queued={v['queued']}"
    if v.get("to_read_stubs"):
        line += f"  to-read-stubs={v['to_read_stubs']}"
    if v.get("partial_books"):
        line += f"  partial-books={v['partial_books']}"
    if v.get("persons_unverified"):
        line += f"  persons-unverified={v['persons_unverified']}"
    if v.get("person_unknowns"):
        line += f"  person-unknowns={v['person_unknowns']}"
    if v.get("lineage_stubs"):
        line += f"  lineage-stubs={v['lineage_stubs']}"
    print(line)
    print(f"performance lint={format_metric_value('lint_ms', v['lint_ms'])}  "
          f"sha1={format_metric_value('sha1_ms', v['sha1_ms'])}  "
          f"wiki={format_metric_value('wiki_ms', v['wiki_ms'])}  "
          f"links={format_metric_value('links_ms', v['links_ms'])}")
    print(f"tokens      raw~{format_tokens(v['raw_tokens'])}  "
          f"wiki~{format_tokens(v['wiki_tokens'])}  "
          f"index saves {v['index_savings_pct']}%  "
          f"queued={format_metric_value('queued_mb', v['queued_mb'])}")
    print("dashboard   python3 -m kb_distillery.dashboard")

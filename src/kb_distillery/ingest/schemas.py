"""Validate claims.json and plan.json without third-party deps."""
import os
import sys

from kb_distillery.core.schema import SOURCE_TYPES

REQUIRED_CLAIMS = ("raw", "title", "problem", "method", "results", "equations", "concepts")
REQUIRED_PLAN = ("wiki_slug", "type", "link_existing", "create_concepts", "moc_updates", "question_updates")


def _check_type(name, data, key, typ):
    if key not in data:
        raise ValueError(f"{name}: missing {key!r}")
    if not isinstance(data[key], typ):
        raise ValueError(f"{name}: {key!r} must be {typ.__name__}, got {type(data[key]).__name__}")


def validate_claims(data):
    if not isinstance(data, dict):
        raise ValueError("claims must be a JSON object")
    for k in REQUIRED_CLAIMS:
        _check_type("claims", data, k, str if k in ("raw", "title", "problem", "method") else list)
    if not data["results"]:
        raise ValueError("claims.results must be non-empty")
    if not data["equations"]:
        raise ValueError("claims.equations must be non-empty (extract defining equations)")
    for eq in data["equations"]:
        if not isinstance(eq, dict) or "latex" not in eq:
            raise ValueError("each equation needs a latex field")
    return True


def validate_plan(data):
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object")
    for k in REQUIRED_PLAN:
        if k not in data:
            raise ValueError(f"plan: missing {k!r}")
    if data["type"] not in SOURCE_TYPES:
        raise ValueError(f"plan.type must be a source type: {sorted(SOURCE_TYPES)}")
    if data["type"] == "part" and not data.get("book"):
        raise ValueError("plan.type part requires plan.book (the book hub slug)")
    if not str(data["wiki_slug"]).strip():
        raise ValueError("plan.wiki_slug required")
    return True

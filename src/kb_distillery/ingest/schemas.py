"""Validate claims.json and plan.json without third-party deps."""
import os
import re
import sys

from kb_distillery.vault.schema import EQUATION_TYPES, SOURCE_TYPES

MARK_LINK = re.compile(r"\[(!!?)\]\(mark:[0-9a-f]{12}/p\d{4}/\d+\)")
REQUIRED_CLAIMS = ("raw", "title", "problem", "method", "results", "concepts")
REQUIRED_PLAN = ("wiki_slug", "type", "link_existing", "create_concepts", "moc_updates", "question_updates")


def _check_type(name, data, key, typ):
    if key not in data:
        raise ValueError(f"{name}: missing {key!r}")
    if not isinstance(data[key], typ):
        raise ValueError(f"{name}: {key!r} must be {typ.__name__}, got {type(data[key]).__name__}")


def validate_claims(data, page_type=None):
    """`equations` is optional (an article, a mail or a video has none). It must hold a real equation only when the
    page is of a type that has a Key equations section to fill (`EQUATION_TYPES`): the caller passes `page_type`
    once the plan has fixed it (draft); before that (extract, map) the type is not known and nothing is enforced."""
    if not isinstance(data, dict):
        raise ValueError("claims must be a JSON object")
    for k in REQUIRED_CLAIMS:
        _check_type("claims", data, k, str if k in ("raw", "title", "problem", "method") else list)
    if not data["results"]:
        raise ValueError("claims.results must be non-empty")
    equations = data.get("equations", [])
    if not isinstance(equations, list):
        raise ValueError(f"claims: 'equations' must be list, got {type(equations).__name__}")
    for eq in equations:
        if not isinstance(eq, dict) or "latex" not in eq:
            raise ValueError("each equation needs a latex field")
        if isinstance(eq["latex"], str) and MARK_LINK.search(eq["latex"]):
            raise ValueError("a mark link goes in the equation's `mark` field, never inside `latex`")
        if eq.get("mark") and not (isinstance(eq["mark"], str) and MARK_LINK.fullmatch(eq["mark"].strip())):
            raise ValueError("an equation's mark must be the mark link exactly as the transcript wrote it")
    exercises = data.get("exercises", [])
    if not isinstance(exercises, list) or any(not isinstance(x, dict) or not isinstance(x.get("statement", ""), str)
                                              or not isinstance(x.get("label", ""), str) for x in exercises):
        raise ValueError("claims: 'exercises' must be a list of {label, statement}")
    if not isinstance(data.get("notes", ""), str):
        raise ValueError("claims: 'notes' must be a string")
    if page_type in EQUATION_TYPES and not any(isinstance(eq["latex"], str) and eq["latex"].strip() not in ("", "—") for eq in equations):
        raise ValueError(f"claims.equations must be non-empty for a {page_type} page (extract defining equations)")
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

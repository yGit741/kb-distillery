"""The proposal model: producer kinds, op kinds and their validation, ids and timestamps. Plain dicts (JSON on disk)."""
from __future__ import annotations

import datetime
import hashlib
import re
import secrets

PRODUCER_KINDS = ("manual", "chat", "flags", "ingest", "restructure", "lint", "restore")
STATUSES = ("open", "applied", "rejected", "stale", "undone")
DECISIONS = ("accept", "reject", "correct")
SEVERITIES = ("error", "warning", "info")

# op kind -> required fields (besides `kind`); optional fields are listed in OPTIONAL
OP_KINDS = {
    "edit_page": ("slug", "new_text"),
    "create_page": ("slug", "text"),
    "tombstone_page": ("slug", "redirect_to"),
    "rewrite_link": ("slug", "from_slug", "to_slug"),
    "move_block": ("from_slug", "to_slug", "block_id"),
    "set_frontmatter": ("slug", "key", "value"),
}
OPTIONAL = {"reason": "", "sources": None}
NOT_YET = ("move_block",)                           # validated, but apply raises until a later item fills it

SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class ProposalError(Exception):
    """An HTTP-free failure with the status the router relays (400 bad input, 404, 405 read-only, 409 stale, 422 checks)."""

    def __init__(self, status: int, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.extra = extra or {}


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return secrets.token_hex(4)


def sha(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_slug(slug, field="slug"):
    if not isinstance(slug, str) or not SLUG.match(slug) or ".." in slug:
        raise ProposalError(400, f"{field}: {slug!r} is not a page slug (lowercase letters, digits, . _ -)")
    return slug


def validate_op(op, i=0) -> dict:
    """A clean copy of one op, or ProposalError(400)."""
    if not isinstance(op, dict):
        raise ProposalError(400, f"ops[{i}] is not an object")
    kind = op.get("kind")
    if kind not in OP_KINDS:
        raise ProposalError(400, f"ops[{i}].kind {kind!r} is not one of {', '.join(OP_KINDS)}")
    out = {"kind": kind}
    for field in OP_KINDS[kind]:
        if field not in op or op[field] is None:
            raise ProposalError(400, f"ops[{i}] ({kind}) needs `{field}`")
        out[field] = op[field]
    for field in ("slug", "from_slug", "to_slug", "redirect_to"):
        if field in out:
            check_slug(out[field], f"ops[{i}].{field}")
    for field in ("new_text", "text"):
        if field in out and not isinstance(out[field], str):
            raise ProposalError(400, f"ops[{i}].{field} must be a string")
    if kind == "set_frontmatter":
        if not isinstance(out["key"], str) or not KEY.match(out["key"]):
            raise ProposalError(400, f"ops[{i}].key {out['key']!r} is not a frontmatter key")
        if not isinstance(out["value"], str) or "\n" in out["value"]:
            raise ProposalError(400, f"ops[{i}].value must be a one-line string")
    out["reason"] = str(op.get("reason") or "")
    srcs = op.get("sources") or []
    if not isinstance(srcs, list) or not all(isinstance(s, str) for s in srcs):
        raise ProposalError(400, f"ops[{i}].sources must be a list of strings")
    out["sources"] = srcs
    out["id"] = f"op{i + 1}"
    return out


def validate_ops(ops) -> list[dict]:
    if not isinstance(ops, list) or not ops:
        raise ProposalError(400, "ops must be a non-empty list")
    clean = [validate_op(op, i) for i, op in enumerate(ops)]
    created = [o["slug"] for o in clean if o["kind"] == "create_page"]
    if len(created) != len(set(created)):
        raise ProposalError(400, "a page is created twice in one revision")
    return clean


def validate_producer(producer) -> dict:
    producer = producer or {}
    if not isinstance(producer, dict):
        raise ProposalError(400, "producer must be an object")
    kind = producer.get("kind", "manual")
    if kind not in PRODUCER_KINDS:
        raise ProposalError(400, f"producer.kind {kind!r} is not one of {', '.join(PRODUCER_KINDS)}")
    context = producer.get("context") or {}
    if not isinstance(context, dict):
        raise ProposalError(400, "producer.context must be an object")
    return {"kind": kind, "instruction": str(producer.get("instruction") or ""), "context": context}


def touched_slugs(ops) -> list[str]:
    """Every page a revision reads or writes, in first-seen order."""
    seen = []
    for o in ops:
        for field in ("slug", "from_slug", "to_slug") if o["kind"] == "move_block" else ("slug",):
            if o.get(field) and o[field] not in seen:
                seen.append(o[field])
    return seen

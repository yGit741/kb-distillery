"""Proposals on disk: one JSON file per proposal in `<kb>/.local/proposals/<id>.json` (kb-local state, never committed)."""
from __future__ import annotations

import json
import os
import re
import tempfile

from kb_distillery.proposals.model import ProposalError
from kb_distillery.vault.schema import LOCAL_DIR

DIR = "proposals"
_ID = re.compile(r"^[0-9a-f]{4,32}$")


def folder(root: str) -> str:
    return os.path.join(root, LOCAL_DIR, DIR)


def path(root: str, pid: str) -> str:
    if not isinstance(pid, str) or not _ID.match(pid):
        raise ProposalError(404, f"no proposal {pid!r}")
    return os.path.join(folder(root), f"{pid}.json")


def load(root: str, pid: str) -> dict:
    p = path(root, pid)
    if not os.path.isfile(p):
        raise ProposalError(404, f"no proposal {pid!r}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(root: str, proposal: dict) -> dict:
    p = path(root, proposal["id"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    return proposal


def all_ids(root: str) -> list[str]:
    d = folder(root)
    if not os.path.isdir(d):
        return []
    return sorted(n[:-5] for n in os.listdir(d) if n.endswith(".json") and _ID.match(n[:-5]))

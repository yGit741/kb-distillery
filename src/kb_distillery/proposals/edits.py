"""The before -> after edit application shared by the producers that ask a model for page edits (chat, flags).

Only the part of a page above `## My notes` can change: that section is the owner's and is never edited.
"""
from __future__ import annotations

MY_NOTES = "## My notes"


def split(text):
    """(editable part, My notes part): the second starts at `## My notes` or is empty."""
    i = text.find("\n" + MY_NOTES)
    return (text, "") if i < 0 else (text[:i + 1], text[i + 1:])


def apply_edits(text: str, edits: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """(new text, applied edits, skipped [{before, reason}]); only the part above `## My notes` changes."""
    editable, notes = split(text)
    applied, skipped = [], []
    for e in edits:
        b = e["before"]
        if not b.strip():
            skipped.append({"before": b, "reason": "empty before"})
        elif b in editable:
            editable = editable.replace(b, e["after"], 1)
            applied.append(e)
        elif notes and b in notes:
            skipped.append({"before": b, "reason": "in My notes, which is never edited"})
        else:
            skipped.append({"before": b, "reason": "text not found on the page"})
    return editable + notes, applied, skipped

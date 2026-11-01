"""Apply plan proposals to wiki targets."""
import os
import re

from .paths import ROOT
from kb_distillery.core import wikiio


def _read(rel):
    """The page without its `## My notes`: proposals never see or edit the user's notes."""
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return wikiio.strip_my_notes(f.read())


def _write(rel, text):
    wikiio.write_page(os.path.join(ROOT, rel), text)       # puts the page's ## My notes back, last


def _append_section(text, heading, block):
    marker = f"## {heading}"
    if marker not in text:
        return text.rstrip() + f"\n\n{marker}\n\n{block.strip()}\n"
    before, rest = text.split(marker, 1)
    lines = rest.splitlines()
    body_lines = []
    for line in lines[1:]:
        if line.startswith("## "):
            break
        body_lines.append(line)
    insert_at = len(before) + len(marker) + 1 + len(body_lines)
    return text[:insert_at].rstrip() + "\n" + block.strip() + "\n" + text[insert_at:].lstrip("\n")


def _update_section(text, heading, block):
    marker = f"## {heading}"
    if marker not in text:
        return _append_section(text, heading, block)
    before, rest = text.split(marker, 1)
    lines = rest.splitlines()
    body = []
    tail_start = 1
    for i, line in enumerate(lines[1:], 1):
        if line.startswith("## "):
            tail_start = i + 1
            break
        body.append(line)
    new_body = (block.strip() + "\n" if block.strip() else "")
    return before + marker + "\n" + new_body + "\n".join(lines[tail_start:])


def apply_proposal(proposal):
    rel = proposal["target"]
    action = proposal["action"]
    text = _read(rel)

    if action == "append_threads":
        text = _append_section(text, "Threads", proposal.get("text", ""))
    elif action == "append_papers":
        text = _append_section(text, "Papers", proposal.get("text", ""))
    elif action == "update_section":
        text = _update_section(text, proposal.get("section", "Current state"), proposal.get("text", ""))
    elif action == "append_related":
        # append slug to related: frontmatter if present
        slug = proposal.get("slug", "")
        if slug and "related:" in text:
            text = re.sub(
                r"(related:\s*\[)([^\]]*)(\])",
                lambda m: f"{m.group(1)}{m.group(2)}, {slug}{m.group(3)}" if slug not in m.group(2) else m.group(0),
                text,
                count=1,
            )
    else:
        raise ValueError(f"unknown action {action!r}")

    _write(rel, text)
    return rel

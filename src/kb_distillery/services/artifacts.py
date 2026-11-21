"""The intermediate layer of a knowledge base: `artifacts/graph.json`, written by a builder.

A knowledge base may carry an intermediate layer: artifacts that are neither pages nor sources (a codebase's
repositories, folders, files, symbols, models ...), the relations between them, the views that draw them, and cards
of fact ids (`F` + 5 hex digits) the pages cite. A builder (a code toolkit's `export`, say) writes it all to
`<root>/artifacts/graph.json`; this module reads it and adds which page cites which fact, so the graph can go from a
page to the code it rests on and back. No file, no layer: every caller treats None as "this knowledge base has none".
"""
import json
import re
from pathlib import Path

FACT = re.compile(r"\bF[0-9a-f]{5}\b")
RESERVED = {"index.md", "log.md"}


def graph_path(root) -> Path:
    return Path(root) / "artifacts" / "graph.json"


def page_cites(wiki: Path, known: set[str]) -> dict[str, list[str]]:
    """page slug (file stem) -> the known fact ids its text names, in order of first mention."""
    out: dict[str, list[str]] = {}
    if not wiki.is_dir():
        return out
    for p in sorted(wiki.rglob("*.md")):
        if p.name in RESERVED or any(part.startswith(".") for part in p.relative_to(wiki).parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen = dict.fromkeys(f for f in FACT.findall(text) if f in known)
        if seen:
            out[p.stem] = list(seen)
    return out


def load(root) -> dict | None:
    """The artifact graph of the knowledge base at `root` with `cites` added, or None when it has none (or it is unreadable)."""
    path = graph_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not data["nodes"]:
        return None
    data.setdefault("links", [])
    known = {fid for card in (data.get("cards") or {}).values() if isinstance(card, dict) for fid in (card.get("facts") or {})}
    data["cites"] = page_cites(Path(root) / "wiki", known)
    return data

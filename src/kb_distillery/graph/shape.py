"""The style clause of a graph view: how the selected nodes are drawn (0 LLM, pure Python).

A view is a Cypher selection (kb_distillery.graph.query) plus a few style clauses, separated by `;` or newlines:

  group by <prop|label|edge-kind>     cluster nodes by a property, by their labels, or by the edge kind that links them
  colour by <prop|label|degree>       (`color` too) one colour per value, or a ramp for the degree
  size by <degree|prop>               node size from the degree or a numeric property
  layout <force|radial|grid|timeline>
  hide <label|edge-kind>              `hide Paper` (a node label), `hide MENTIONS` (an edge kind, all caps);
                                      `hide label x` / `hide edge x` say which when the spelling is ambiguous
  label <prop>                        the text shown beside a node

`parse_style` returns a `StyleSpec` (JSON-ready) or raises `ShapeError` with a hint, like the Cypher engine does.
`format_style` is its inverse, so a spec round-trips through the text a person edits.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field

# What a node carries in the Cypher graph (kb_distillery.graph.model.to_graph); `area` is accepted for `areas`.
NODE_PROPS = ("slug", "title", "type", "layer", "depth", "maturity", "areas", "year", "path")
LAYOUTS = ("force", "radial", "grid", "timeline")
LABEL_WORDS = ("label", "labels")
EDGE_WORDS = ("edge-kind", "edge-kinds", "edge_kind", "edge", "edges", "kind")
GRAMMAR = ("group by <prop|label|edge-kind>; colour by <prop|label|degree>; size by <degree|prop>; "
           f"layout <{'|'.join(LAYOUTS)}>; hide <label|edge-kind>; label <prop>")


class ShapeError(ValueError):
    """Free text that cannot become a view: `message` says why and what to write instead; `status` is the HTTP
    status the server answers with (422 for text, 502/400 when the LLM could not be asked)."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


class Target(BaseModel):
    """What a style reads: a node property, the node labels, the degree, or the edge kind."""
    by: Literal["prop", "label", "degree", "edge-kind"]
    name: str | None = Field(None, description="the property name when `by` is `prop`")


class StyleSpec(BaseModel):
    group_by: Target | None = None
    colour_by: Target | None = None
    size_by: Target | None = None
    layout: Literal["force", "radial", "grid", "timeline"] | None = None
    hide_labels: list[str] = []
    hide_edge_kinds: list[str] = []
    label: str | None = Field(None, description="node property shown as the node's text")

    def is_empty(self):
        return not self.model_dump(exclude_none=True, exclude_defaults=True)


def _hint(what):
    return f"{what}. Style clauses: {GRAMMAR}"


def _camel(text):
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[^A-Za-z0-9]+", text) if p)


def _edge_kind(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").upper()


def _prop(word, clause):
    p = word.lower()
    p = "areas" if p == "area" else p
    if p not in NODE_PROPS:
        raise ShapeError(_hint(f"`{clause}`: unknown property `{word}`; nodes carry {', '.join(NODE_PROPS)}"))
    return p


def _target(clause, rest, allowed):
    """`rest` = the words after `<verb> by`; `allowed` = which of label/degree/edge-kind the verb takes."""
    if not rest:
        raise ShapeError(_hint(f"`{clause}`: name what to use"))
    word = "-".join(rest).lower()
    if word in LABEL_WORDS:
        kind = "label"
    elif word in EDGE_WORDS:
        kind = "edge-kind"
    elif word == "degree":
        kind = "degree"
    else:
        kind = "prop"
    if kind != "prop" and kind not in allowed:
        raise ShapeError(_hint(f"`{clause}`: `{word}` is not allowed here; use {', '.join(sorted(allowed))} "
                               f"or a property"))
    return Target(by="prop", name=_prop("".join(rest), clause)) if kind == "prop" else Target(by=kind)


def _hide(clause, rest, spec):
    if not rest:
        raise ShapeError(_hint(f"`{clause}`: name a node label (`hide Paper`) or an edge kind (`hide MENTIONS`)"))
    explicit = None
    if rest[0].lower() in LABEL_WORDS:
        explicit, rest = "label", rest[1:]
    elif rest[0].lower() in EDGE_WORDS:
        explicit, rest = "edge", rest[1:]
        if rest and rest[0].lower() in ("kind", "kinds"):
            rest = rest[1:]
    names = [n for n in re.split(r"\s*,\s*", " ".join(rest)) if n.strip()]
    if not names:
        raise ShapeError(_hint(f"`{clause}`: nothing to hide"))
    for n in names:
        if explicit is None and len(n.split()) > 1:
            raise ShapeError(_hint(f"`{clause}`: `{n}` is not one label or edge kind; name it (`hide Paper`), "
                                   f"or write `hide label Open Problem` for a multi-word name"))
        is_edge = explicit == "edge" or (explicit is None and n.upper() == n and any(c.isalpha() for c in n))
        bucket = spec["hide_edge_kinds"] if is_edge else spec["hide_labels"]
        value = _edge_kind(n) if is_edge else _camel(n)
        if value and value not in bucket:
            bucket.append(value)


def parse_style(text):
    """`group by type; colour by degree` → StyleSpec. A later clause of the same verb replaces an earlier one;
    `hide` accumulates. Raises ShapeError (with a hint) on an unknown clause or value."""
    spec = {"hide_labels": [], "hide_edge_kinds": []}
    for raw in re.split(r"[;\n]", text or ""):
        clause = raw.strip().rstrip(".").strip()
        if not clause:
            continue
        words = clause.split()
        verb, rest = words[0].lower(), words[1:]
        by = bool(rest) and rest[0].lower() == "by"
        if verb == "group" and by:
            spec["group_by"] = _target(clause, rest[1:], {"label", "edge-kind"})
        elif verb in ("colour", "color") and by:
            spec["colour_by"] = _target(clause, rest[1:], {"label", "degree"})
        elif verb == "size" and by:
            spec["size_by"] = _target(clause, rest[1:], {"degree"})
        elif verb == "layout":
            if len(rest) != 1 or rest[0].lower() not in LAYOUTS:
                raise ShapeError(_hint(f"`{clause}`: layout is one of {', '.join(LAYOUTS)}"))
            spec["layout"] = rest[0].lower()
        elif verb == "hide":
            _hide(clause, rest, spec)
        elif verb == "label":
            if len(rest) != 1:
                raise ShapeError(_hint(f"`{clause}`: label takes one node property"))
            spec["label"] = _prop(rest[0], clause)
        else:
            raise ShapeError(_hint(f"unknown style clause `{clause}`"))
    return StyleSpec(**spec)


def _target_text(t):
    return t.name if t.by == "prop" else t.by


def format_style(spec):
    """StyleSpec → the canonical clause list (`;` separated); `parse_style(format_style(s)) == s`."""
    parts = []
    if spec.group_by:
        parts.append(f"group by {_target_text(spec.group_by)}")
    if spec.colour_by:
        parts.append(f"colour by {_target_text(spec.colour_by)}")
    if spec.size_by:
        parts.append(f"size by {_target_text(spec.size_by)}")
    if spec.layout:
        parts.append(f"layout {spec.layout}")
    parts += [f"hide label {n}" for n in spec.hide_labels]
    parts += [f"hide edge {n}" for n in spec.hide_edge_kinds]
    if spec.label:
        parts.append(f"label {spec.label}")
    return "; ".join(parts)


_RAW = re.compile(r"\s*MATCH\s*\(", re.I)           # `MATCH (`: English "match papers to ideas" is free text
_STYLE_LINE = re.compile(r"^\s*(--(?!>)|style\s*:)", re.I)


def is_cypher(text):
    return bool(_RAW.match(text or ""))


def split_cypher(text):
    """`MATCH …` plus an optional style clause after the first line that starts with `--` or `style:` →
    (cypher, style_text). Everything from that line on is style; a `-->` arrow at a line start is not a marker."""
    lines = (text or "").strip().splitlines()
    for i, line in enumerate(lines):
        if _STYLE_LINE.match(line):
            head = _STYLE_LINE.sub("", line, count=1)
            return "\n".join(lines[:i]).strip(), "\n".join([head, *lines[i + 1:]]).strip()
    return "\n".join(lines).strip(), ""

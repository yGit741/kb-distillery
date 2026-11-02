"""The page types of a knowledge base, read from its `kb.toml` `[types]` (explorer defaults otherwise).

The explorer fixes the three layers (Source, Collection, Concept) and the two tool-owned auxiliary types
(`scope`, `distilled-think`). Everything else is the knowledge base's: which sources it digests, which
collections group them, which concepts it grows. `kb_distillery.vault.schema` exposes the result under its historical
constant names; this module only knows kb.toml and the defaults.

    [types]
    order = ["topic", "idea", ...]        # optional; the default is concepts, collections, sources
    areas = ["statistics", ...]           # the `area:` whitelist (topic pages are theme-<area>)
    deprecated_areas = [...]
    source_fields = ["authors", "venue"]  # extra frontmatter fields on source pages

    [types.source.paper]                  # a layer table given in kb.toml replaces that layer's defaults
    label = "Paper"                       # required
    prefix = "paper-"                     # "" = bare slug
    yeared = true                         # filename year must agree with `year:`
    status = ["to-read", "reading", "digested"]   # default for sources and collections
    color = "#ff6b7a"                     # optional; a palette colour otherwise

    [types.collection.book]
    kind = "partition"                    # partition (a page range of its own PDF) | contents (member files)

    [types.concept.idea]
    status = ["seed", "growing", "solid"] # default for concepts; [] = no status
"""
from __future__ import annotations

from dataclasses import dataclass

from kb_distillery.config import kb as kbconfig

LAYERS = ("concept", "collection", "source")
READ_STATUS = {"to-read", "reading", "digested"}
GROW_STATUS = {"seed", "growing", "solid"}
# Tool-owned auxiliary types, the same in every knowledge base.
AUX_LAYER = {"scope": "collection", "distilled-think": "concept"}
AUX_STATUS = {"distilled-think": {"review", "applied", "archived"}, "scope": {"active", "parked"}}
AUX_PREFIX = {"distilled-think": "distilled-think-", "scope": "scope-"}
AUX_LABEL = {"distilled-think": "Distilled", "scope": "Scope"}
AUX_COLOR = {"distilled-think": "#e0af68", "scope": "#e6c07b"}

# Explorer defaults: a research knowledge base's types, which double as a sensible general set.
DEFAULT_TYPES = {
    "source": {
        "paper":     {"label": "Paper", "prefix": "paper-", "yeared": True, "color": "#ff6b7a"},   # academic work
        "part":      {"label": "Book part", "prefix": "part-", "yeared": True, "color": "#eab0ee"},   # a page range of a book
        "lecture":   {"label": "Lecture", "prefix": "lecture-", "color": "#ffc777"},   # one class session
        "article":   {"label": "Article", "prefix": "article-", "color": "#4fd6be"},   # web clip, tutorial
        "video":     {"label": "Video", "prefix": "video-", "color": "#f7768e"},
        "mail":      {"label": "Mail", "prefix": "mail-", "color": "#73daca"},         # an email thread (raw/emails/)
        "ai-chat":   {"label": "AI chat", "prefix": "chat-", "color": "#ff9e64"},      # an LLM chat (meta/chats/ trees)
        "blog-post": {"label": "Blog post", "prefix": "blog-", "color": "#ff79c6"},    # one post of a blog series
    },
    "collection": {
        "book":     {"label": "Book", "prefix": "book-", "kind": "partition", "yeared": True, "color": "#d16bd8"},
        "notebook": {"label": "Notebook", "prefix": "notebook-", "kind": "partition", "color": "#c099ff"},
        "course":   {"label": "Course", "prefix": "course-", "kind": "contents", "color": "#2ac3de"},
        "series":   {"label": "Series", "prefix": "series-", "kind": "contents", "color": "#7dcfff"},
    },
    "concept": {
        "topic":    {"label": "Topic", "prefix": "theme-", "color": "#9ece6a"},
        "idea":     {"label": "Idea", "prefix": "", "color": "#7aa2ff"},
        "question": {"label": "Question", "prefix": "q-", "status": ["open", "partial", "resolved"], "color": "#f6c177"},
        "person":   {"label": "Person", "prefix": "", "status": [], "color": "#bb9af7"},   # progress is `verified:`
    },
}
DEFAULT_ORDER = ("topic", "idea", "question", "person", "course", "series", "book", "notebook",
                 "paper", "part", "lecture", "article", "blog-post", "video", "ai-chat", "mail")
PALETTE = ("#7aa2ff", "#9ece6a", "#f6c177", "#bb9af7", "#2ac3de", "#ff6b7a", "#4fd6be", "#ffc777",
           "#ff9e64", "#73daca", "#d16bd8", "#7dcfff", "#eab0ee", "#f7768e", "#ff79c6", "#c099ff")


class TypesError(ValueError):
    """`[types]` in kb.toml is invalid; the message names the type and the key."""


@dataclass(frozen=True)
class Types:
    source_types: frozenset
    partition_collections: frozenset
    contents_collections: frozenset
    concept_types: frozenset
    layer_of: dict
    type_status: dict
    yeared: set
    slug_prefix: dict
    bare_types: set
    type_label: dict
    type_order: tuple
    type_color: dict
    areas: frozenset
    deprecated_areas: frozenset
    source_fields: tuple
    spec: dict           # layer → type → its table, as loaded (for /api/kb)


def _layer_tables(section: dict) -> dict:
    out = {}
    for layer in LAYERS:
        given = section.get(layer)
        if given is None:
            out[layer] = {k: dict(v) for k, v in DEFAULT_TYPES[layer].items()}
            continue
        if not isinstance(given, dict) or not given:
            raise TypesError(f"[types.{layer}] must be a table of at least one type")
        out[layer] = {}
        for name, table in given.items():
            if not isinstance(table, dict) or not table.get("label"):
                raise TypesError(f"[types.{layer}.{name}] needs a `label`")
            out[layer][name] = dict(table)
    return out


def build(section: dict | None) -> Types:
    section = section or {}
    tables = _layer_tables(section)
    seen: dict = {}
    for layer in LAYERS:
        for name in tables[layer]:
            if name in seen or name in AUX_LAYER:
                raise TypesError(f"type {name!r} defined twice ({seen.get(name, 'tool-owned')} and {layer})")
            seen[name] = layer
    sources = frozenset(tables["source"])
    partition = frozenset(n for n, t in tables["collection"].items() if t.get("kind", "contents") == "partition")
    contents = frozenset(tables["collection"]) - partition
    concepts = frozenset(tables["concept"])

    layer_of = {**seen, **AUX_LAYER}
    status, prefix, label, color, yeared = {}, {}, {}, {}, set()
    for layer in LAYERS:
        default_status = GROW_STATUS if layer == "concept" else READ_STATUS
        for name, t in tables[layer].items():
            status[name] = set(t["status"]) if "status" in t else set(default_status)
            prefix[name] = str(t.get("prefix", f"{name}-"))
            label[name] = str(t["label"])
            if t.get("color"):
                color[name] = str(t["color"])
            if t.get("yeared"):
                yeared.add(name)
    for name in AUX_LAYER:
        status[name], prefix[name], label[name], color[name] = AUX_STATUS[name], AUX_PREFIX[name], AUX_LABEL[name], AUX_COLOR[name]
    used = set(color.values())
    for name in seen:
        if name not in color:
            color[name] = next((c for c in PALETTE if c not in used), PALETTE[len(used) % len(PALETTE)])
            used.add(color[name])

    # no `order` given: the explorer's default order for the types it knows, then the kb's own in table order
    order = tuple(section.get("order") or [t for t in DEFAULT_ORDER if t in seen]
                  + [n for l in LAYERS for n in tables[l] if n not in DEFAULT_ORDER])
    missing = set(seen) - set(order)
    extra = set(order) - set(seen)
    if missing or extra:
        raise TypesError(f"[types] order must list every type once: missing {sorted(missing)}, unknown {sorted(extra)}")
    order = tuple(order) + ("distilled-think", "scope")
    prefixes = [p for p in prefix.values() if p]
    if len(prefixes) != len(set(prefixes)):
        raise TypesError("[types] two types share a filename prefix")

    return Types(
        source_types=sources, partition_collections=partition, contents_collections=contents,
        concept_types=concepts, layer_of=layer_of, type_status=status, yeared=yeared,
        slug_prefix={n: p for n, p in prefix.items() if p}, bare_types={n for n, p in prefix.items() if not p},
        type_label=label, type_order=order, type_color=color,
        areas=frozenset(section.get("areas") or ()), deprecated_areas=frozenset(section.get("deprecated_areas") or ()),
        source_fields=tuple(section.get("source_fields") or ()), spec=tables,
    )


def load(cfg: kbconfig.KbConfig | None = None) -> Types:
    """The active knowledge base's types (`kbconfig.current()`), or the explorer defaults."""
    cfg = cfg or kbconfig.current()
    section = cfg.section("types") if cfg else None
    try:
        return build(section)
    except TypesError as e:
        raise TypesError(f"{cfg.path if cfg else 'defaults'}: {e}") from None

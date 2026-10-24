"""The vault schema as the dashboard JS sees it (`/api/schema`, and `schema` inside `/api/graph`).

backend/src/kb/core/schema.py is the single source of truth; the static pages keep no type, layer, depth or
disposition lists of their own. Colours are presentation, but they are keyed by type here too so a
new type needs one edit.
"""
import os
import sys

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb.core import schema

TYPE_COLOR = {
    "paper": "#ff6b7a", "part": "#eab0ee", "lecture": "#ffc777", "article": "#4fd6be",
    "video": "#f7768e", "conversation": "#73daca", "ai-chat": "#ff9e64", "blog-post": "#ff79c6",
    "book": "#d16bd8", "notebook": "#c099ff", "course": "#2ac3de", "series": "#7dcfff",
    "topic": "#9ece6a", "idea": "#7aa2ff", "question": "#f6c177", "person": "#bb9af7",
    "distilled-think": "#e0af68", "scope": "#e6c07b",
}
LAYER_COLOR = {"concept": "#7aa2ff", "collection": "#2ac3de", "source": "#ff6b7a"}
# Concept types shown when the graph opens; the rest of the concept layer is one chip away.
DEFAULT_VISIBLE = ("topic", "idea", "question")
assert set(TYPE_COLOR) == set(schema.LAYER_OF)


def schema_payload():
    return {
        "version": list(schema.SCHEMA_VERSION),
        "layers": [{"id": l, "label": schema.LAYER_LABEL[l], "color": LAYER_COLOR[l],
                    "types": [t for t in schema.TYPE_ORDER if schema.LAYER_OF[t] == l]}
                   for l in schema.LAYERS],
        "types": [{"id": t, "label": schema.TYPE_LABEL[t], "layer": schema.LAYER_OF[t],
                   "color": TYPE_COLOR[t], "prefix": schema.SLUG_PREFIX.get(t, ""),
                   "statuses": sorted(schema.TYPE_STATUS[t])} for t in schema.TYPE_ORDER],
        "source_types": sorted(schema.SOURCE_TYPES),
        "collection_types": sorted(schema.COLLECTION_TYPES),
        "concept_types": sorted(schema.CONCEPT_TYPES),
        "depth": list(schema.DEPTH),
        "dispositions": sorted(schema.DISPOSITIONS),
        "default_visible": list(DEFAULT_VISIBLE),
    }

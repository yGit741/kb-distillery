"""The vault schema as the dashboard JS sees it (`/api/schema`, and `schema` inside `/api/graph`).

src/kb_distillery/vault/schema.py is the single source of truth; the static pages keep no type, layer, depth or
disposition lists of their own. Colours are presentation, but they are keyed by type here too so a
new type needs one edit.
"""
import os
import sys

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.vault import schema

TYPE_COLOR = schema.TYPE_COLOR            # per type, from the knowledge base's kb.toml (palette fallback)
LAYER_COLOR = {"concept": "#7aa2ff", "collection": "#2ac3de", "source": "#ff6b7a"}
# Concept types shown when the graph opens; the rest of the concept layer is one chip away.
DEFAULT_VISIBLE = tuple(t for t in ("topic", "idea", "question") if t in schema.CONCEPT_TYPES) or tuple(
    t for t in schema.TYPE_ORDER if schema.LAYER_OF[t] == "concept")


def schema_payload(types=None):
    """The active knowledge base's schema, or the one `types` (a `kbtypes.Types`) describes."""
    t_ = types or schema._T
    order, layer_of = t_.type_order, t_.layer_of
    concept = t_.concept_types
    visible = tuple(t for t in ("topic", "idea", "question") if t in concept) or tuple(
        t for t in order if layer_of[t] == "concept")
    return {
        "version": list(schema.SCHEMA_VERSION),
        "layers": [{"id": l, "label": schema.LAYER_LABEL[l], "color": LAYER_COLOR[l],
                    "types": [t for t in order if layer_of[t] == l]}
                   for l in schema.LAYERS],
        "types": [{"id": t, "label": t_.type_label[t], "layer": layer_of[t],
                   "color": t_.type_color[t], "prefix": t_.slug_prefix.get(t, ""),
                   "statuses": sorted(t_.type_status[t])} for t in order],
        "source_types": sorted(t_.source_types),
        "collection_types": sorted(t_.partition_collections | t_.contents_collections),
        "concept_types": sorted(concept),
        "depth": list(schema.DEPTH),
        "dispositions": sorted(schema.DISPOSITIONS),
        "default_visible": list(visible),
    }

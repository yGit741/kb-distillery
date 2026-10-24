"""Legacy -> new data-model adapter. DELETE after data-model stage 7.

The live vault still carries the old 16 page types and the `digestion-status` field. The harness
speaks the new vocabulary only (type / kind / depth); this is the ONE place that knows the old
names. Everything else (invariants, goldens, fixture names, reports) calls `to_new_model`.
"""

_SOURCE = {"paper", "article", "blog-post", "video", "lecture", "conversation", "ai-chat", "part"}
_COLLECTION = {"book", "notebook", "course", "series"}
_CONCEPT = {"theme": "topic", "concept": "idea", "question": "question", "person": "person"}


def to_new_model(fm):
    """Front matter of a current-model page -> (type, kind, depth).

    depth is "" for pages that have none. Transient/other legacy types (distilled-think, scope,
    meta) come back as ("draft", <old type>, "") so they are counted, never silently dropped.
    """
    old = (fm.get("type") or "unknown").strip()
    depth = (fm.get("digestion-status") or fm.get("depth") or "").strip()
    if old in ("source", "collection", "concept") and fm.get("kind"):
        return old, str(fm["kind"]).strip(), depth        # already in the new form
    if old in _SOURCE:
        return "source", old, depth
    if old in _COLLECTION:
        return "collection", old, depth
    if old in _CONCEPT:
        return "concept", _CONCEPT[old], ""
    return "draft", old, ""

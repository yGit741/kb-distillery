"""A scrap-youtube bundle as the app shows it: video.json next to the bundle's video.md, anchors with raw paths."""
import json
import os

from kb_distillery.core.schema import RAW_VIDEOS, VIDEO_ITEM
from kb_distillery.services import corpus


def load_bundle(rel):
    """`raw/videos/<dir>/video.md` (or the folder) → the bundle's data, or None when it is not a bundle.
    Each frame gains `path`, its raw path, for the raw file route."""
    rel = rel.rstrip("/")
    if not rel.endswith(f"/{VIDEO_ITEM}"):
        rel = f"{rel}/{VIDEO_ITEM}"
    parts = rel.split("/")
    if len(parts) != 4 or parts[0] != "raw" or parts[1] != RAW_VIDEOS:
        return None
    full, err = corpus.check_raw_path(rel)
    if err or not full:
        return None
    data_path = os.path.join(os.path.dirname(full), "video.json")
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    folder = "/".join(parts[:3])
    for a in data.get("anchors") or []:
        a["path"] = f"{folder}/{a['thumb']}"
    data.pop("frames", None)                     # a bundle from before anchors: re-scrap it to get them
    data["raw"] = rel
    return data

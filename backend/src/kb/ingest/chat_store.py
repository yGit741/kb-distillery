"""Durable conversation-tree store: meta/chats/<conv_id>.json + a regenerable index.

Survives lint/guard/daily_sync untouched: lint only walks .md files, guard.py's
raw/ restriction doesn't apply to meta/**.json, and only DOT-prefixed meta/
subdirs (meta/.ingest/, etc.) are gitignored — meta/chats/ is committed.
"""
import glob
import json
import os
import sys

from kb.core.schema import CHATS_DIR, CHAT_TREE_SCHEMA

from kb.paths import vault_root
ROOT = vault_root()
CHATS_ABS = os.path.join(ROOT, CHATS_DIR)
INDEX_PATH = os.path.join(CHATS_ABS, "index.json")
INDEX_SCHEMA = "conversation-index/1"


def _ensure_dir():
    os.makedirs(CHATS_ABS, exist_ok=True)


def _path(conv_id):
    return os.path.join(CHATS_ABS, conv_id + ".json")


def new_id(root_hash):
    """conv-<root_hash> with a numeric suffix on collision against a DIFFERENT root."""
    base = "conv-" + root_hash[:12]
    if not os.path.isfile(_path(base)):
        return base
    n = 1
    while os.path.isfile(_path(f"{base}-{n}")):
        n += 1
    return f"{base}-{n}"


def load(conv_id):
    path = _path(conv_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(conv):
    """Atomic (tmp + os.replace), deterministic (sort_keys) write."""
    _ensure_dir()
    conv["schema"] = CHAT_TREE_SCHEMA
    path = _path(conv["id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conv, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def all_conversations():
    _ensure_dir()
    for path in sorted(glob.glob(os.path.join(CHATS_ABS, "conv-*.json"))):
        with open(path, encoding="utf-8") as f:
            yield json.load(f)


def load_index():
    if not os.path.isfile(INDEX_PATH):
        return rebuild_index()
    with open(INDEX_PATH, encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("schema") != INDEX_SCHEMA:
        return rebuild_index()
    return idx


def rebuild_index():
    _ensure_dir()
    idx = {
        "schema": INDEX_SCHEMA,
        "by_turn": {},
        "by_clip": {},
        "by_url": {},
        "by_wiki": {},
    }
    for conv in all_conversations():
        cid = conv["id"]
        for node in conv.get("nodes", {}).values():
            idx["by_turn"].setdefault(node["hash"], [])
            if cid not in idx["by_turn"][node["hash"]]:
                idx["by_turn"][node["hash"]].append(cid)
        for clip_rel in conv.get("clips", {}):
            idx["by_clip"][clip_rel] = cid
        for url in conv.get("source_urls", []):
            idx["by_url"][url] = cid
        if conv.get("wiki"):
            idx["by_wiki"][conv["wiki"]] = cid
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, INDEX_PATH)
    return idx

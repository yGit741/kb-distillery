"""Conversation identity + merge: does a new clip start a new conversation,
extend one, branch one, or turn out to be an exact duplicate / mid-tree segment?

Node ids are content-addressed over the ANCESTOR CHAIN (Merkle over content
hashes, not over ephemeral creation order): id = sha1(parent_id + "\\x00" + hash).
This makes the id a pure function of the FINAL tree structure — order-independent
across catalog runs — at the cost of needing a cascade id-recompute on the rare
"prefix superset" re-parent (see _reparent_root). This mirrors how git commit
hashes shift on rebase: expected, not a bug, and bounded to the shifted subtree.
"""
import hashlib
import sys
import os

from . import chat_store  # noqa: E402
from . import chat_signal  # noqa: E402

MIN_COVER = 0.25
ROOT_BONUS = 0.25
# An unbroken run of turns matching a parent->child chain is far stronger evidence
# than the same number of turns scattered across the tree, and it does NOT dilute
# with clip length the way the cover RATIO does. A long clip that continues an
# existing conversation only overlaps at its head, so its cover can sit below
# MIN_COVER while the match is unambiguous — hence a separate acceptance path.
MIN_RUN = 3
# Turns that must match beneath a child before a hash-mismatched turn is treated
# as a re-capture of that child rather than a new branch.
VARIANT_LOOKAHEAD = 2


def _node_id(parent_id, content_hash):
    seed = (parent_id or "") + "\x00" + content_hash
    return "t-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def new_conversation(turns, fm, slug=None, title=None, provider="gemini"):
    fm = fm or {}
    return {
        "id": None,
        "provider": provider,
        "title": title or fm.get("title"),
        "slug": slug,
        "source_urls": [fm["source"]] if fm.get("source") else [],
        "wiki": None,
        "canonical_clip": None,
        "clips": {},
        "root": None,
        "nodes": {},
        "leaves": [],
        "branch_points": [],
        "landed_well": [],
        "status": {
            "digest": "queued",
            "needs_redigest": False,
            "redigest_reason": None,
            "digested_leaves": [],
        },
    }


def _make_node(turn, parent_id, depth, clip_rel, clipped_date):
    nid = _node_id(parent_id, turn.hash)
    return {
        "id": nid,
        "role": turn.role,
        "hash": turn.hash,
        "parent": parent_id,
        "children": [],
        "depth": depth,
        "text_ref": {"clip": clip_rel, "start_line": turn.start_line, "end_line": turn.end_line},
        "seen_in": [clip_rel],
        "first_seen": clipped_date,
        "variant_of": None,
        "code_fences": [
            {
                "lang": f.lang, "start_line": f.start_line, "end_line": f.end_line,
                "sha1": f.sha1, "looks_runnable": f.looks_runnable, "artifact": None,
            }
            for f in turn.fences
        ],
        "math": dict(turn.math),
        "inline_visuals": getattr(turn, "inline_visuals", 0),
        "signal": dict(turn.signal) if turn.signal else
                  {"explicit": False, "marker": None, "score": 0, "matched": []},
    }


def find_conversation(turns, source_url=None, clip_path=None, index=None, load=None):
    """Tiered match. Returns (conv_id_or_None, info_dict). `load` overrides
    chat_store.load (an in-memory rebuild passes its own)."""
    index = index if index is not None else chat_store.load_index()
    load = load or chat_store.load

    if source_url and source_url in index.get("by_url", {}):
        return index["by_url"][source_url], {"tier": "url"}

    if clip_path and clip_path in index.get("by_clip", {}):
        return index["by_clip"][clip_path], {"tier": "clip"}

    if not turns:
        return None, {}

    by_turn = index.get("by_turn", {})
    candidate_ids = set()
    for t in turns:
        candidate_ids.update(by_turn.get(t.hash, []))
    if not candidate_ids:
        return None, {}

    turn_hashes = [t.hash for t in turns]
    turn_hash_set = set(turn_hashes)

    best = None  # (eligible, cover, run, shared, cid)
    for cid in candidate_ids:
        conv = load(cid)
        if not conv or not conv.get("nodes"):
            continue
        node_hashes = {n["hash"] for n in conv["nodes"].values()}
        shared = len(turn_hash_set & node_hashes)
        if shared == 0:
            continue
        cover = shared / min(len(turns), len(conv["nodes"]))
        root_hash = conv["nodes"].get(conv.get("root", ""), {}).get("hash")
        if root_hash and turn_hashes and turn_hashes[0] == root_hash:
            cover += ROOT_BONUS
        run = _longest_chain_run(conv, turns)
        eligible = cover >= MIN_COVER or run >= MIN_RUN
        key = (eligible, cover, run, shared, cid)
        if best is None or key > best:
            best = key

    if best is None:
        return None, {"tier": "overlap"}
    eligible, cover, run, shared, cid = best
    info = {"tier": "overlap" if eligible else "overlap-rejected",
            "cover": cover, "run": run, "shared": shared}
    return (cid if eligible else None), info


def _longest_chain_run(conv, turns):
    """Longest run of consecutive `turns` that follows an unbroken parent->child
    chain in conv's tree. Contiguity is the point: it distinguishes a real shared
    conversation segment from incidental repeats of common turns ('ok', 'continue')."""
    nodes = conv["nodes"]
    by_hash = {}
    for n in nodes.values():
        by_hash.setdefault(n["hash"], []).append(n)

    best = 0
    for i in range(len(turns)):
        if len(turns) - i <= best:
            break  # no remaining start can beat the best run found
        for start in by_hash.get(turns[i].hash, ()):
            cursor, j = start, i + 1
            while j < len(turns):
                nxt = None
                for cid in cursor["children"]:
                    if nodes[cid]["hash"] == turns[j].hash:
                        nxt = nodes[cid]
                        break
                if nxt is None:
                    break
                cursor, j = nxt, j + 1
            if j - i > best:
                best = j - i
    return best


def _locate_anchor(conv, turns):
    """Find the best existing node matching turns[0], scored by how many of the
    FOLLOWING turns also match that candidate's descendant chain — disambiguates
    repeated content ('ok', 'continue') by preferring the longest continued run."""
    nodes = conv["nodes"]
    candidates = [n for n in nodes.values() if n["hash"] == turns[0].hash]
    if not candidates:
        return None

    def run_length(node):
        cursor = node
        i = 1
        while i < len(turns):
            nxt = None
            for cid in cursor["children"]:
                if nodes[cid]["hash"] == turns[i].hash:
                    nxt = nodes[cid]
                    break
            if nxt is None:
                break
            cursor = nxt
            i += 1
        return i

    return max(candidates, key=run_length)


def _find_prefix_superset(conv, turns):
    """Does conv's current root hash appear at turns[k], k>0? If so this clip is a
    superset that extends BEFORE the current root. Returns k or None."""
    root_hash = conv["nodes"][conv["root"]]["hash"]
    for k in range(1, len(turns)):
        if turns[k].hash == root_hash:
            return k
    return None


def _reparent_root(conv, turns, k, clip_rel, clipped_date):
    """Insert turns[0..k-1] as new ancestors above the current root, then
    cascade-recompute ids for the shifted subtree (old root + all descendants)."""
    old_root_id = conv["root"]
    new_ids = []
    parent_id = None
    for i in range(k):
        node = _make_node(turns[i], parent_id, depth=i, clip_rel=clip_rel, clipped_date=clipped_date)
        conv["nodes"][node["id"]] = node
        if parent_id is not None:
            conv["nodes"][parent_id]["children"].append(node["id"])
        parent_id = node["id"]
        new_ids.append(node["id"])

    # link the last new ancestor to the old root, then cascade ids downward.
    conv["nodes"][parent_id]["children"].append(old_root_id)
    _cascade_reparent(conv, old_root_id, parent_id, base_depth=k)
    conv["root"] = new_ids[0]
    return new_ids


def _cascade_reparent(conv, node_id, new_parent_id, base_depth):
    """Recompute (id, parent, depth) for node_id and its whole subtree after its
    ancestor chain changed. Returns nothing; mutates conv['nodes'] in place,
    replacing keys as ids change."""
    nodes = conv["nodes"]
    old_node = nodes.pop(node_id)
    new_id = _node_id(new_parent_id, old_node["hash"])
    old_node["id"] = new_id
    old_node["parent"] = new_parent_id
    old_node["depth"] = base_depth
    nodes[new_id] = old_node

    # fix any branch_points / leaves / landed_well referencing the old id
    _rewrite_id_everywhere(conv, node_id, new_id)

    # old_node["children"] still holds the OLD child ids here; recursing renames
    # each child and rewrites every reference to it (including inside old_node's
    # own children list, since old_node now lives under new_id and is part of
    # conv["nodes"]) before moving to the next sibling.
    for child_old_id in list(old_node["children"]):
        _cascade_reparent(conv, child_old_id, new_id, base_depth + 1)


def _rewrite_id_everywhere(conv, old_id, new_id):
    if conv.get("root") == old_id:
        conv["root"] = new_id
    conv["leaves"] = [new_id if x == old_id else x for x in conv.get("leaves", [])]
    for bp in conv.get("branch_points", []):
        if bp.get("node") == old_id:
            bp["node"] = new_id
        for v in bp.get("variants", []):
            if v.get("child") == old_id:
                v["child"] = new_id
    for h in conv.get("landed_well", []):
        if h.get("praise_node") == old_id:
            h["praise_node"] = new_id
        if h.get("credited_node") == old_id:
            h["credited_node"] = new_id
    for n in conv["nodes"].values():
        if n.get("variant_of") == old_id:
            n["variant_of"] = new_id
        n["children"] = [new_id if c == old_id else c for c in n["children"]]


def attach_clip(conv, clip_rel, turns, meta):
    """Walk turns against conv's tree, extending/branching as needed. Mutates conv
    in place. Returns a report dict: {relation, added_nodes, branch_at, notes}."""
    clipped_date = meta.get("clipped")
    report = {"relation": None, "added_nodes": 0, "branch_at": None, "notes": []}

    if not conv["nodes"]:
        # brand-new conversation
        parent_id = None
        for i, t in enumerate(turns):
            node = _make_node(t, parent_id, depth=i, clip_rel=clip_rel, clipped_date=clipped_date)
            conv["nodes"][node["id"]] = node
            if parent_id is not None:
                conv["nodes"][parent_id]["children"].append(node["id"])
            parent_id = node["id"]
        conv["root"] = next(iter(conv["nodes"])) if len(conv["nodes"]) == 1 else _first_node_id(conv)
        conv["leaves"] = [parent_id] if parent_id else []
        conv["canonical_clip"] = clip_rel
        conv["clips"][clip_rel] = {
            "sha1": meta.get("sha1"), "clipped": clipped_date,
            "inbox_name": meta.get("inbox_name"), "relation": "root",
            "path_node_ids": list(conv["nodes"].keys()), "added_nodes": len(turns),
        }
        report["relation"] = "new"
        report["added_nodes"] = len(turns)
        _merge_landed_well(conv, turns, conv["clips"][clip_rel]["path_node_ids"])
        return report

    anchor = _locate_anchor(conv, turns)
    cursor = None
    i = 0
    prefix_new_ids = []

    if anchor is None:
        k = _find_prefix_superset(conv, turns)
        if k is not None:
            prefix_new_ids = _reparent_root(conv, turns, k, clip_rel, clipped_date)
            # walk down the freshly-inserted chain to the (now re-id'd) old root
            cursor = conv["nodes"][conv["root"]]
            for _ in range(k):
                cursor = conv["nodes"][cursor["children"][0]]
            i = k + 1
            report["relation"] = "extension"
            report["added_nodes"] += k
        else:
            report["relation"] = "unrelated"
            report["notes"].append("no anchor and no prefix-superset match; treating as no-op")
            conv["clips"][clip_rel] = {
                "sha1": meta.get("sha1"), "clipped": clipped_date,
                "inbox_name": meta.get("inbox_name"), "relation": "unrelated",
                "path_node_ids": [], "added_nodes": 0,
            }
            return report
    else:
        cursor = anchor
        i = 1

    path_node_ids = prefix_new_ids + [cursor["id"]]
    while i < len(turns):
        t = turns[i]
        child_id = None
        for cid in cursor["children"]:
            if conv["nodes"][cid]["hash"] == t.hash:
                child_id = cid
                break
        if child_id is not None:
            node = conv["nodes"][child_id]
            if clip_rel not in node["seen_in"]:
                node["seen_in"].append(clip_rel)
            _merge_signal(node, t)
            cursor = node
            path_node_ids.append(cursor["id"])
            i += 1
            continue

        same = _capture_variant(conv, cursor, turns, i)
        if same is not None:
            # Same turn, captured differently (citation chips, a dropped bullet):
            # the clip's next turns continue under it, so this is not a fork.
            node = conv["nodes"][same]
            node.setdefault("capture_variants", [])
            if t.hash not in [v["hash"] for v in node["capture_variants"]]:
                node["capture_variants"].append({"hash": t.hash, "clip": clip_rel})
            if clip_rel not in node["seen_in"]:
                node["seen_in"].append(clip_rel)
            cursor = node
            path_node_ids.append(cursor["id"])
            i += 1
            continue

        was_leaf = len(cursor["children"]) == 0
        node = _make_node(t, cursor["id"], cursor["depth"] + 1, clip_rel, clipped_date)
        cursor["children"].append(node["id"])
        conv["nodes"][node["id"]] = node
        if not was_leaf:
            node["variant_of"] = cursor["children"][0]
            variants = [
                {"child": cid, "clips": conv["nodes"][cid]["seen_in"][:]}
                for cid in cursor["children"]
            ]
            # One branch_point per forking node: a third variant UPDATES the existing
            # entry rather than appending a duplicate for the same node.
            existing_bp = next(
                (b for b in conv["branch_points"] if b["node"] == cursor["id"]), None
            )
            if existing_bp is not None:
                existing_bp["variants"] = variants
            else:
                conv["branch_points"].append({
                    "node": cursor["id"], "depth": cursor["depth"], "variants": variants,
                })
            if report["relation"] is None:
                report["relation"] = "branch"
            report["branch_at"] = cursor["id"]
        else:
            if report["relation"] is None:
                report["relation"] = "extension"
        if cursor["id"] in conv["leaves"]:
            conv["leaves"].remove(cursor["id"])
        cursor = node
        path_node_ids.append(cursor["id"])
        report["added_nodes"] += 1
        i += 1

    if cursor["id"] not in conv["leaves"] and len(cursor["children"]) == 0:
        conv["leaves"].append(cursor["id"])

    if report["relation"] is None:
        # walked the whole clip with zero new nodes — either a full duplicate path
        # (identical) or a sub-path fully contained in the tree already (segment).
        if anchor is not None and anchor["id"] == conv["root"] and cursor["id"] in conv["leaves"] + [conv["root"]]:
            report["relation"] = "identical"
        else:
            report["relation"] = "segment"

    _merge_landed_well(conv, turns, path_node_ids)

    conv["clips"][clip_rel] = {
        "sha1": meta.get("sha1"), "clipped": clipped_date,
        "inbox_name": meta.get("inbox_name"), "relation": report["relation"],
        "path_node_ids": path_node_ids, "added_nodes": report["added_nodes"],
    }
    return report


def _capture_variant(conv, cursor, turns, i):
    """A child of `cursor` that turns[i] is a re-capture of: same role, and the
    clip's following turns (up to VARIANT_LOOKAHEAD) continue exactly beneath it.
    A real fork changes what comes after; a capture glitch doesn't."""
    ahead = turns[i + 1:i + 1 + VARIANT_LOOKAHEAD]
    if not ahead:
        return None
    nodes = conv["nodes"]
    for cid in cursor["children"]:
        if nodes[cid]["role"] != turns[i].role:
            continue
        node, ok = nodes[cid], True
        for t in ahead:
            nxt = next((c for c in node["children"] if nodes[c]["hash"] == t.hash), None)
            if nxt is None:
                ok = False
                break
            node = nodes[nxt]
        if ok:
            return cid
    return None


def _merge_signal(node, turn):
    if not turn.signal:
        return
    if turn.signal["explicit"]:
        node["signal"]["explicit"] = True
        node["signal"]["marker"] = "@obs-good"
        node["signal"]["score"] = 100
    if turn.signal["score"] > node["signal"]["score"]:
        node["signal"]["score"] = turn.signal["score"]
    for m in turn.signal["matched"]:
        if m not in node["signal"]["matched"]:
            node["signal"]["matched"].append(m)


def _merge_landed_well(conv, turns, path_node_ids):
    """Roll this clip's per-turn signal up into conv-level landed_well, mapping
    content-hash-based hits (from chat_signal.landed_well) onto actual tree node
    ids via the index-aligned path_node_ids. Dedupes by (praise_node, credited_node)."""
    if len(path_node_ids) != len(turns):
        return  # defensive: only true for the "unrelated" no-op path
    hits = chat_signal.landed_well(turns)
    existing = {(h["praise_node"], h["credited_node"]): h for h in conv["landed_well"]}
    hash_to_pos = {}
    for i, t in enumerate(turns):
        hash_to_pos.setdefault(t.hash, i)
    for hit in hits:
        pi = hash_to_pos.get(hit["praise_node"])
        ci = hash_to_pos.get(hit["credited_node"])
        if pi is None or ci is None:
            continue
        key = (path_node_ids[pi], path_node_ids[ci])
        if key in existing and existing[key]["score"] >= hit["score"]:
            continue
        existing[key] = {
            "praise_node": key[0], "credited_node": key[1],
            "score": hit["score"], "matched": hit["matched"], "explicit": hit["explicit"],
        }
    conv["landed_well"] = list(existing.values())


def _first_node_id(conv):
    for nid, n in conv["nodes"].items():
        if n["parent"] is None:
            return nid
    return next(iter(conv["nodes"]))

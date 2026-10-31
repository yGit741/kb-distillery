"""Rebuild conversation trees (meta/chats/) from every clip in raw/llm-chats/. Zero LLM.

One conversation per Gemini thread, however many times it was clipped: identical
re-clips fold away, longer clips extend, and diverging clips become branches
(chat_merge does the tree work; this module only drives it over the whole corpus).
Runnable fences (html/svg apps the model wrote) are extracted once per sha1 to
meta/chats/assets/<conv>/<sha8>.html and recorded on the node that holds them.

Dry run by default: everything lands under --out, nothing in meta/chats/ is touched.
"""
import glob
import hashlib
import json
import os
import shutil

from . import chat, chat_merge, chat_store
from .paths import ROOT
from kb.storage import for_kb
from kb.core.schema import RAW_CHATS

ASSETS = "assets"


def load_clip(clip_rel, root=ROOT):
    text = for_kb(root=root).get(clip_rel).decode("utf-8")
    fm, turns = chat.parse_clip(text)
    return fm or {}, turns, hashlib.sha1(text.encode("utf-8")).hexdigest()


def clip_paths(root=ROOT):
    prefix = f"raw/{RAW_CHATS}/"
    return sorted(k for k in for_kb(root=root).list(prefix) if k.endswith(".md") and "/" not in k[len(prefix):])


def _index(convs):
    idx = {"by_turn": {}, "by_clip": {}, "by_url": {}, "by_wiki": {}}
    for key, conv in convs.items():
        for node in conv["nodes"].values():
            idx["by_turn"].setdefault(node["hash"], []).append(key)
        for url in conv["source_urls"]:
            idx["by_url"][url] = key
    return idx


def build(clip_rels, root=ROOT):
    """Return ({conv_id: conv}, [report rows]). Pure: reads clips, writes nothing."""
    clips = []
    for rel in clip_rels:
        fm, turns, sha1 = load_clip(rel, root)
        if turns:
            clips.append((str(fm.get("clipped") or ""), rel, fm, turns, sha1))
    clips.sort(key=lambda c: (c[0], c[1]))

    convs, rows, n = {}, [], 0
    for clipped, rel, fm, turns, sha1 in clips:
        key, info = chat_merge.find_conversation(
            turns, source_url=fm.get("source"), index=_index(convs), load=convs.get)
        meta = {"clipped": clipped or None, "sha1": sha1, "inbox_name": os.path.basename(rel)}
        report = chat_merge.attach_clip(convs[key], rel, turns, meta) if key else None
        if report is None or report["relation"] == "unrelated":
            if report is not None:  # overlap matched but no anchor: keep the clip, start fresh
                del convs[key]["clips"][rel]
            n += 1
            key = f"tmp-{n}"
            provider = "claude" if str(fm.get("model") or "").startswith("claude") else "gemini"
            convs[key] = chat_merge.new_conversation(turns, fm, slug=os.path.basename(rel)[:-3],
                                                     provider=provider)
            report = chat_merge.attach_clip(convs[key], rel, turns, meta)
        if fm.get("source") and fm["source"] not in convs[key]["source_urls"]:
            convs[key]["source_urls"].append(fm["source"])
        rows.append({"clip": rel, "conv": key, "relation": report["relation"],
                     "added": report["added_nodes"], "turns": len(turns),
                     "runnable": sum(f.looks_runnable for t in turns for f in t.fences)})

    final = {}
    for key, conv in convs.items():
        base = "conv-" + conv["nodes"][conv["root"]]["hash"][:12]
        cid, k = base, 1
        while cid in final:
            cid, k = f"{base}-{k}", k + 1
        conv["id"] = cid
        conv["canonical_clip"] = canonical_clip(conv)
        conv["slug"] = os.path.basename(conv["canonical_clip"])[:-3]
        final[cid] = conv
        for row in rows:
            if row["conv"] == key:
                row["conv"] = cid
    return final, rows


def main_leaf(conv):
    """The leaf seen in the most clips, deepest on ties: the path the page leads with."""
    nodes = conv["nodes"]
    return max(conv["leaves"], key=lambda l: (len(nodes[l]["seen_in"]), nodes[l]["depth"], l))


def path_to(conv, node_id):
    path = []
    while node_id:
        path.append(node_id)
        node_id = conv["nodes"][node_id]["parent"]
    return path[::-1]


def canonical_clip(conv):
    """The clip that walks the main path furthest (raw: on the wiki page)."""
    main = set(path_to(conv, main_leaf(conv)))
    return max(conv["clips"], key=lambda c: (
        len(main & set(conv["clips"][c]["path_node_ids"])), c))


def fence_body(clip_lines, fence):
    """Lines strictly between the opening and closing fence (1-indexed, inclusive)."""
    return "\n".join(clip_lines[fence["start_line"]:fence["end_line"] - 1]) + "\n"


def extract_artifacts(conv, out_root, root=ROOT):
    """Write each runnable fence once (by sha1) and record it on its node. Returns [paths]."""
    written, by_sha, cache = [], {}, {}
    rel_dir = f"meta/chats/{ASSETS}/{conv['id']}"
    for node in conv["nodes"].values():
        clip = node["text_ref"]["clip"]
        for fence in node["code_fences"]:
            if not fence["looks_runnable"]:
                continue
            if clip not in cache:
                with open(os.path.join(root, clip), encoding="utf-8") as f:
                    cache[clip] = f.read().split("\n")
            body = fence_body(cache[clip], fence)
            kind = "svg" if body.lstrip().startswith("<svg") else "html"
            rel = f"{rel_dir}/{fence['sha1'][:8]}.{kind}"
            png = os.path.splitext(rel)[0] + ".png"
            fence["artifact"] = {
                "bytes": len(body.encode("utf-8")), "kind": kind, "node": node["id"], "path": rel,
                "png": png if os.path.isfile(os.path.join(root, png)) else None,
            }
            if fence["sha1"] in by_sha:
                continue
            by_sha[fence["sha1"]] = rel
            dest = os.path.join(out_root, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(body)
            written.append(rel)
    return written


def preserve_pngs(convs, root=ROOT):
    """Hand-made thumbnails live under the OLD conv id; point artifacts at them by sha."""
    pngs = {os.path.basename(p)[:8]: os.path.relpath(p, root).replace(os.sep, "/")
            for p in glob.glob(os.path.join(root, "meta", "chats", ASSETS, "*", "*.png"))}
    for conv in convs.values():
        for node in conv["nodes"].values():
            for fence in node["code_fences"]:
                art = fence.get("artifact")
                if art and not art["png"] and fence["sha1"][:8] in pngs:
                    art["png"] = pngs[fence["sha1"][:8]]


def run(out=None, apply=False, root=ROOT):
    """Dry run → everything under `out`. --apply → meta/chats/ replaced in place."""
    convs, rows = build(clip_paths(root), root)
    out_root = root if apply else out
    for conv in convs.values():
        extract_artifacts(conv, out_root, root)
    preserve_pngs(convs, root)
    if apply:
        stale = [p for p in glob.glob(os.path.join(chat_store.CHATS_ABS, "conv-*.json"))
                 if os.path.basename(p)[:-5] not in convs]
        for conv in convs.values():
            chat_store.save(conv)
        for p in stale:
            os.remove(p)
        _move_pngs(convs, root)
        chat_store.rebuild_index()
    else:
        os.makedirs(os.path.join(out, "meta", "chats"), exist_ok=True)
        for conv in convs.values():
            with open(os.path.join(out, "meta", "chats", conv["id"] + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump(conv, f, sort_keys=True, indent=2, ensure_ascii=False)
                f.write("\n")
    return convs, rows


def _move_pngs(convs, root):
    """After --apply, copy thumbnails into the new conv's asset dir and repoint them."""
    for conv in convs.values():
        for node in conv["nodes"].values():
            for fence in node["code_fences"]:
                art = fence.get("artifact")
                if not art or not art["png"]:
                    continue
                want = os.path.splitext(art["path"])[0] + ".png"
                if art["png"] != want:
                    shutil.copy2(os.path.join(root, art["png"]), os.path.join(root, want))
                    art["png"] = want
        chat_store.save(conv)


def tree_ascii(conv, label=None):
    """Outline of a conversation: one line per turn; `*` = main path, ⑂n = fork."""
    nodes, lines = conv["nodes"], []
    label = label or (lambda n: n["hash"])
    main = set(path_to(conv, main_leaf(conv)))

    def line(n):
        fork = f"  ⑂{len(n['children'])}" if len(n["children"]) > 1 else ""
        leaf = "  ◆" if not n["children"] else ""
        return (f"{'*' if n['id'] in main else ' '}{n['depth']:>3} "
                f"{'U' if n['role'] == 'user' else 'M'}  {label(n)}{fork}{leaf}")

    def walk(nid, first, rest):
        pre = first
        while True:
            n = nodes[nid]
            lines.append(pre + line(n))
            pre = rest
            if len(n["children"]) != 1:
                break
            nid = n["children"][0]
        kids = n["children"]
        for i, c in enumerate(kids):
            last = i == len(kids) - 1
            walk(c, rest + ("└─ " if last else "├─ "), rest + ("   " if last else "│  "))

    walk(conv["root"], "", "")
    return "\n".join(lines)

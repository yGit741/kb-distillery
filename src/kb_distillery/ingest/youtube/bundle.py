"""scrap-youtube: one standard bundle per video (0 LLM).

fetch → transcript sections → the 1 fps pass → anchors (+ a thumbnail each) → raw/inbox/video-<dir>/
    video.md        what an agent reads: metadata, description, chapters, comments, the transcript by chapter
                    with each section's anchors listed under it
    video.json      the same, structured, for the app (sections, anchors with reasons and scores)
    a-<seconds>.jpg one thumbnail per anchor, 640 px (gitignored like every raw image; raw/videos nests one level)
    info.json, transcript.vtt
Reading frames costs LLM tokens, so it belongs to a digest tier (kb_distillery.ingest.youtube.digest), not here.
"""
import glob
import json
import os
import re
import shutil
import sys

from ..paths import ROOT
from . import fetch as fetch_mod
from . import frames as fx
from . import readers
from .transcript import keep_comments, links, parse_vtt, sections, ts

ITEM = "video.md"           # the bundle's raw item (what a Source page's raw: points at)
DATA = "video.json"         # the same content, structured, for the app
THUMB_W = 640


def kebab(text, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:n].rstrip("-") or "video"


def existing(vid, root=ROOT):
    """Bundles (inbox or cataloged) of this YouTube id."""
    hits = []
    for pat in ("raw/inbox/video-*/info.json", "raw/videos/*/info.json"):
        for p in glob.glob(os.path.join(root, pat)):
            try:
                if json.load(open(p, encoding="utf-8")).get("id") == vid:
                    hits.append(os.path.relpath(os.path.dirname(p), root))
            except (OSError, ValueError):
                pass
    return hits


def dir_name(title, vid, root=ROOT):
    """A re-scrap (--force) keeps the folder name of this video's bundle, inbox or cataloged."""
    for hit in existing(vid, root):
        name = hit.split("/")[-1]
        return name[len("video-"):] if hit.startswith("raw/inbox/") else name
    base = kebab(title)
    taken = os.path.exists(os.path.join(root, "raw", "inbox", f"video-{base}")) or \
        os.path.exists(os.path.join(root, "raw", "videos", base))
    return base if not taken else f"{base}-{kebab(vid, 11)}"


def context(cues, t, before=60, after=20):
    return " ".join(x for s, x in cues if t - before <= s <= t + after)


def build_anchors(mp4, cues, chapters, folder, thumbs_dir):
    """The anchors of a video, each with a thumbnail written to thumbs_dir. Returns (anchors, stats)."""
    cv2 = fx._cv()
    a = fx.analyse(mp4, fetch_mod.ffmpeg_exe(), cache=os.path.join(folder, "analysis.npz"))
    mode = fx.mode_of(a)
    cap = cv2.VideoCapture(mp4)
    ocr = {}
    slide_words = None
    if mode == "slides":                                     # OCR every slide candidate: words score it
        slide_words = {}
        for c in fx.slide_candidates(a):
            img = fx.grab(cap, c["t"])
            lines = [x for x, conf in readers.ocr(img) if conf > 0.4] if img is not None else []
            ocr[c["t"]], slide_words[c["t"]] = lines, fx.words(lines)
    sig = fx.signals(a, mode, cues, chapters, slide_words)
    anchors = fx.cover(fx.merge(sig), a["delta"])
    os.makedirs(thumbs_dir, exist_ok=True)
    kind = "board" if mode == "board" else "slide"
    out = []
    for x in anchors:
        img = fx.grab(cap, x["t"])
        if img is None:
            continue
        pts, vis = fx.visual_score(img, kind)
        if x["t"] not in ocr:                                # every anchor: text on screen is the best cheap
            ocr[x["t"]] = [s for s, conf in readers.ocr(img) if conf > 0.4]   # sign it is worth reading
        words = len(fx.words(ocr[x["t"]]))
        score = x["score"] + pts + min(3, words // 8)
        th = img.copy()
        th.thumbnail((THUMB_W, THUMB_W))
        name = f"a-{x['t']:05d}.jpg"
        th.convert("RGB").save(os.path.join(thumbs_dir, name), quality=72)
        out.append({"t": x["t"], "thumb": name, "kind": kind, "score": score, "why": x["why"],
                    **vis, "flat": round(fx.flatness(img), 2), "ocr": ocr.get(x["t"], [])})
    fx.adjust(out, mode, chapters, len(a["delta"]))
    return out, {"mode": mode, "seconds": int(len(a["delta"])), "signals": len(sig), "anchors": len(out)}


def render_md(meta, secs, anchors, comments):
    url = meta["url"]
    fm = ["---", f"title: {json.dumps(meta['title'], ensure_ascii=False)}", f"url: {url}",
          f"channel: {json.dumps(meta.get('channel') or '', ensure_ascii=False)}",
          f"duration: {ts(meta['duration'])}", f"uploaded: {meta.get('uploaded') or ''}",
          f"transcript: {meta['subs_kind'] or 'none'}", f"anchors: {len(anchors)}", "---", ""]
    md = fm + [f"# {meta['title']}", "",
               "Transcript by chapter. Under each section, its anchors: timestamps where the screen likely shows "
               "something worth reading (score = how likely; thumbnails a-<seconds>.jpg). A digest tier reads the "
               "top ones; nothing here was read by an LLM.", ""]
    if meta.get("description"):
        md += ["## Description", "", meta["description"].strip(), ""]
    if meta.get("chapters"):
        md += ["## Chapters", ""] + [f"- [{ts(c['start'])}]({url}&t={int(c['start'])}s) {c['title']}"
                                     for c in meta["chapters"]] + [""]
    if comments:
        md += ["## Top comments", ""] + [f"- **{c['author']}** ({c['likes']} likes): " + c["text"].replace("\n", " ")
                                         for c in comments] + [""]
    if not secs:
        md += ["## Transcript", "", "_No English transcript was downloaded for this video._", ""]
        if anchors:
            md += ["## Anchors", ""] + [f"- [{ts(x['t'])}]({x['thumb']}) {x['kind']} {x['score']}" for x in anchors] + [""]
    home = section_of(secs)
    chapter = None
    for k, s in enumerate(secs):
        if chapter is None or s["chapter"] != chapter:
            chapter = s["chapter"]
            md += [f"## {chapter or 'Transcript'}", ""]
        md += [f"### [{ts(s['start'])}–{ts(s['end'])}]({url}&t={int(s['start'])}s)", "", s["text"], ""]
        mine = [x for x in anchors if home(x["t"]) == k]
        if mine:
            md += ["Anchors: " + " · ".join(f"[{ts(x['t'])}]({x['thumb']}) {x['kind']} {x['score']}" for x in mine), ""]
    return "\n".join(md).rstrip() + "\n"


def section_of(secs):
    """t → index of the last section starting at or before t (a frame before the first caption → 0)."""
    starts = [s["start"] for s in secs]
    return lambda t: max([i for i, a in enumerate(starts) if a <= t] or [0])


def scrap_youtube(url, force=False, root=ROOT):
    """→ raw/inbox/video-<dir>/ (relative path). Raises resolve.DuplicateBlocked when already scrapped."""
    from .. import resolve as resolve_mod
    vid = fetch_mod.video_id(url)
    hits = existing(vid, root)
    if hits and not force:
        print(f"FOUND youtube:{vid} → {hits[0]}")
        print("scrap blocked — use the existing bundle or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked([{"raw": hits[0], "reason": "youtube id"}])
    print(f"fetching {vid} …")
    f = fetch_mod.fetch(url, video=True)
    info = f.info
    duration = int(info.get("duration") or 0)
    cues = parse_vtt(open(f.subs, encoding="utf-8").read(), auto=f.subs_kind == "auto") if f.subs else []
    if not f.subs and fetch_mod.has_english(info):
        print("warning: YouTube lists English subtitles but none were downloaded (rate limit?) — "
              "rerun with --force later", file=sys.stderr)
    chapters = [{"title": c.get("title") or "", "start": c["start_time"], "end": c.get("end_time")}
                for c in info.get("chapters") or []]
    secs = sections(cues, info.get("chapters"), duration)

    name = dir_name(info.get("title"), vid, root)
    rel = f"raw/inbox/video-{name}"
    final = os.path.join(root, rel)
    dest = os.path.join(root, ".cache", "youtube-build", name)   # built here, moved into the inbox when whole
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    anchors, stats = [], {"mode": None, "anchors": 0}
    if f.mp4:
        print("finding anchors (1 fps pass) …")
        anchors, stats = build_anchors(f.mp4, cues, info.get("chapters"), f.folder, dest)   # raw/videos nests one level
    else:
        print("warning: no video file was downloaded — the bundle has no anchors", file=sys.stderr)
    stats["cues"] = len(cues)
    comments = keep_comments(info.get("comments"))
    meta = {"id": vid, "title": info.get("title") or vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "channel": info.get("channel") or info.get("uploader"), "duration": duration,
            "uploaded": info.get("upload_date") and f"{info['upload_date'][:4]}-{info['upload_date'][4:6]}-{info['upload_date'][6:]}",
            "description": info.get("description") or "", "chapters": chapters, "subs_kind": f.subs_kind}
    with open(os.path.join(dest, ITEM), "w", encoding="utf-8") as fh:
        fh.write(render_md(meta, secs, anchors, comments))
    data = {**meta, "links": links(meta["description"]), "comments": comments,
            "comment_count": info.get("comment_count"), "sections": secs, "anchors": anchors, "stats": stats}
    with open(os.path.join(dest, DATA), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(dest, "info.json"), "w", encoding="utf-8") as fh:
        json.dump(fetch_mod.slim_info(info), fh, ensure_ascii=False, indent=1)
    if f.subs:
        shutil.copyfile(f.subs, os.path.join(dest, "transcript.vtt"))
    if os.path.isdir(final):
        shutil.rmtree(final)                      # --force over this video's own inbox bundle
    os.makedirs(os.path.dirname(final), exist_ok=True)
    shutil.move(dest, final)
    print(f"scrap (youtube) → {rel}/ — {len(secs)} sections, {len(anchors)} anchors ({stats.get('mode')}), "
          f"transcript {f.subs_kind or 'none'}")
    return rel


def load(raw_path):
    return json.load(open(os.path.join(os.path.dirname(raw_path), DATA), encoding="utf-8"))


def abstract(raw_path, head_words=1200, tail_words=300):
    """What easy-digest reads for a video: metadata, description, chapters and the start and end of the
    transcript (a skim; frames are a full/deep digest's job)."""
    d = load(raw_path)
    words = " ".join(s["text"] for s in d.get("sections") or []).split()
    body = " ".join(words[:head_words])
    if len(words) > head_words + tail_words:
        body += " […] " + " ".join(words[-tail_words:])
    elif len(words) > head_words:
        body = " ".join(words)
    parts = [f"Title: {d['title']}", f"Channel: {d.get('channel') or ''}", f"URL: {d['url']}",
             f"Duration: {ts(d['duration'])}", "", "Description:", (d.get("description") or "")[:2000], ""]
    if d.get("chapters"):
        parts += ["Chapters:"] + [f"- {ts(c['start'])} {c['title']}" for c in d["chapters"]] + [""]
    parts += ["Transcript (start and end):", body]
    return "\n".join(parts) + "\n"

"""scrap-youtube: fetch → transcript sections → frames (per tier) → raw/inbox/video-<dir>/ bundle."""
import glob
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

from ..paths import ROOT
from . import fetch as fetch_mod
from . import frames as fx
from . import readers
from .transcript import keep_comments, links, parse_vtt, sections, ts

TIERS = ("transcript", "vibe", "frames")
ITEM = "video.md"           # the bundle's raw item (what a Source page's raw: points at)
DATA = "video.json"         # the same content, structured, for the app
PER_HOUR = 30               # frames tier budget
MAX_W = 1280


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
    base = kebab(title)
    taken = os.path.exists(os.path.join(root, "raw", "inbox", f"video-{base}")) or \
        os.path.exists(os.path.join(root, "raw", "videos", base))
    return base if not taken else f"{base}-{kebab(vid, 11)}"


def _context(cues, t, before=60, after=20):
    return " ".join(x for s, x in cues if t - before <= s <= t + after)


def _save(img, path):
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)))
    img.convert("RGB").save(path, quality=80)


def vibe_frames(mp4, duration):
    cv2 = fx._cv()
    cap = cv2.VideoCapture(mp4)
    scored = []
    for t in fx.vibe_times(duration):
        img = fx.grab(cap, t)
        if img is None:
            continue
        lines = readers.ocr(img)
        text = [x for x, c in lines if c > 0.4]
        scored.append({"t": int(t), "kind": "vibe", "img": img, "ocr": text, "score": fx.info_score(img, text),
                       "conf": round(sum(c for _, c in lines) / len(lines), 2) if lines else 0.0})
    return fx.pick_vibe(scored, duration)


def full_frames(fetched, secs, duration, per_hour=PER_HOUR):
    cv2 = fx._cv()
    a = fx.analyse(fetched.mp4, fetch_mod.ffmpeg_exe(), cache=os.path.join(fetched.folder, "analysis.npz"))
    mode = fx.mode_of(a)
    cap = cv2.VideoCapture(fetched.mp4)
    out = []
    if mode == "slides":
        cands = []
        for c in fx.slide_candidates(a):
            img = fx.grab(cap, c["t"])
            if img is None:
                continue
            lines = readers.ocr(img)
            text = [x for x, cf in lines if cf > 0.4]
            cands.append({**c, "img": img, "ocr": text, "words": fx.words(text),
                          "conf": round(sum(cf for _, cf in lines) / len(lines), 2) if lines else 0.0})
        for c in fx.dedup_slides(cands):
            c["score"] = len(c.pop("words")) * 10
            out.append(c)
    else:
        for c in fx.dedup_boards(fx.board_candidates(a), a["fr"]):
            img = fx.grab(cap, c["t"] + 0.5)
            if img is None:
                continue
            box = fx.board_crop_box(img)
            img = img.crop(box) if box else img
            lines = readers.ocr(img)
            out.append({**c, "img": img, "h": img.height, "score": c["ink"],
                        "ocr": [x for x, cf in lines if cf > 0.4],
                        "conf": round(sum(cf for _, cf in lines) / len(lines), 2) if lines else 0.0})
        out = fx.drop_wide(out)
    stats = {"mode": mode, "seconds": int(len(a["fr"])), "candidates": len(out)}
    return fx.budget(out, secs, per_hour, duration), stats


def render_md(meta, secs, frames, comments):
    url = meta["url"]
    fm = ["---", f"title: {json.dumps(meta['title'], ensure_ascii=False)}", f"url: {url}",
          f"channel: {json.dumps(meta.get('channel') or '', ensure_ascii=False)}",
          f"duration: {ts(meta['duration'])}", f"uploaded: {meta.get('uploaded') or ''}",
          f"transcript: {meta['subs_kind'] or 'none'}", f"tier: {meta['tier']}", f"frames: {len(frames)}", "---", ""]
    md = fm + [f"# {meta['title']}", "",
               "Transcript by chapter; each frame sits in the section where it was shown, with what was read "
               "from it. Open an image only when the text is not enough.", ""]
    if meta.get("description"):
        md += ["## Description", "", meta["description"].strip(), ""]
    if meta.get("chapters"):
        md += ["## Chapters", ""] + [f"- [{ts(c['start'])}]({url}&t={int(c['start'])}s) {c['title']}"
                                     for c in meta["chapters"]] + [""]
    if comments:
        md += ["## Top comments", ""] + [f"- **{c['author']}** ({c['likes']} likes): " + c["text"].replace("\n", " ")
                                         for c in comments] + [""]
    if not secs:
        md += ["## Transcript", "", "_No English transcript on YouTube for this video._", ""]
    chapter, fi = None, 0
    for s in secs:
        if s["chapter"] != chapter or chapter is None:
            chapter = s["chapter"]
            md += [f"## {chapter or 'Transcript'}", ""]
        md += [f"### [{ts(s['start'])}–{ts(s['end'])}]({url}&t={int(s['start'])}s)", "", s["text"], ""]
        while fi < len(frames) and frames[fi]["t"] < s["end"]:
            f = frames[fi]
            fi += 1
            md += [f"![{ts(f['t'])}]({f['file']}) *{ts(f['t'])} · {f['kind']}*", ""]
            if f.get("read", {}).get("text"):
                md += [f["read"]["text"], ""]
            elif f.get("ocr"):
                md += ["```text", *f["ocr"], "```", ""]
    while fi < len(frames):                                   # frames past the last caption
        f = frames[fi]
        fi += 1
        md += [f"![{ts(f['t'])}]({f['file']}) *{ts(f['t'])} · {f['kind']}*", ""]
    return "\n".join(md).rstrip() + "\n"


def scrap_youtube(url, tier="vibe", force=False, read=False, per_hour=PER_HOUR, model=readers.READ_MODEL,
                  root=ROOT):
    """→ raw/inbox/video-<dir>/ (relative path). Raises resolve.DuplicateBlocked when already scrapped."""
    from .. import resolve as resolve_mod
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    vid = fetch_mod.video_id(url)
    hits = existing(vid, root)
    if hits and not force:
        print(f"FOUND youtube:{vid} → {hits[0]}")
        print("scrap blocked — use the existing bundle or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked([{"raw": hits[0], "reason": "youtube id"}])
    print(f"fetching {vid} ({tier}) …")
    f = fetch_mod.fetch(url, video=tier != "transcript")
    info = f.info
    duration = int(info.get("duration") or 0)
    cues = parse_vtt(open(f.subs, encoding="utf-8").read()) if f.subs else []
    chapters = [{"title": c.get("title") or "", "start": c["start_time"], "end": c.get("end_time")}
                for c in info.get("chapters") or []]
    secs = sections(cues, info.get("chapters"), duration)
    stats = {"tier": tier, "cues": len(cues)}
    picked = []
    if tier == "vibe" and f.mp4:
        picked = vibe_frames(f.mp4, duration)
    elif tier == "frames" and f.mp4:
        picked, more = full_frames(f, secs, duration, per_hour)
        stats.update(more)
    picked.sort(key=lambda x: x["t"])

    name = dir_name(info.get("title"), vid, root)
    rel = f"raw/inbox/video-{name}"
    dest = os.path.join(root, rel)
    if os.path.isdir(dest):
        shutil.rmtree(dest)                       # --force over an uncataloged bundle
    os.makedirs(dest)
    for p in picked:
        p["file"] = f"frame-{int(p['t']):05d}.jpg"
        _save(p.pop("img"), os.path.join(dest, p["file"]))
    if read and picked:
        with ThreadPoolExecutor(4) as ex:
            reads = list(ex.map(lambda p: readers.claude_read(os.path.join(dest, p["file"]),
                                                              _context(cues, p["t"]), model), picked))
        for p, r in zip(picked, reads):
            p["read"] = r
        stats["read"] = {"frames": sum(1 for r in reads if r.get("text")),
                         "tokens_in": sum(r.get("tokens_in") or 0 for r in reads),
                         "tokens_out": sum(r.get("tokens_out") or 0 for r in reads),
                         "usd_cli": round(sum(r.get("usd") or 0 for r in reads), 3)}
    comments = keep_comments(info.get("comments"))
    meta = {"id": vid, "title": info.get("title") or vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "channel": info.get("channel") or info.get("uploader"), "duration": duration,
            "uploaded": info.get("upload_date") and f"{info['upload_date'][:4]}-{info['upload_date'][4:6]}-{info['upload_date'][6:]}",
            "description": info.get("description") or "", "chapters": chapters, "subs_kind": f.subs_kind, "tier": tier}
    frames_out = [{k: v for k, v in p.items() if k in ("t", "file", "kind", "ocr", "conf", "read", "end")}
                  for p in picked]
    stats["frames"] = len(frames_out)
    with open(os.path.join(dest, ITEM), "w", encoding="utf-8") as fh:
        fh.write(render_md(meta, secs, frames_out, comments))
    data = {**meta, "links": links(meta["description"]), "comments": comments,
            "comment_count": info.get("comment_count"), "sections": secs, "frames": frames_out, "stats": stats}
    with open(os.path.join(dest, DATA), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(dest, "info.json"), "w", encoding="utf-8") as fh:
        json.dump(fetch_mod.slim_info(info), fh, ensure_ascii=False, indent=1)
    if f.subs:
        shutil.copyfile(f.subs, os.path.join(dest, "transcript.vtt"))
    print(f"scrap (youtube, {tier}) → {rel}/ — {len(secs)} sections, {len(frames_out)} frames, "
          f"transcript {f.subs_kind or 'none'}")
    return rel


def abstract(raw_path, head_words=1200, tail_words=300):
    """What easy-digest reads for a video: metadata, description, chapters, frame text, and the start
    and end of the transcript (a skim, not the lecture)."""
    d = json.load(open(os.path.join(os.path.dirname(raw_path), DATA), encoding="utf-8"))
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
    for f in d.get("frames") or []:
        text = (f.get("read") or {}).get("text") or "\n".join(f.get("ocr") or [])
        if text:
            parts += [f"Frame {ts(f['t'])}:", text, ""]
    parts += ["Transcript (start and end):", body]
    return "\n".join(parts) + "\n"

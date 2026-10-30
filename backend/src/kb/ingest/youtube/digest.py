"""video-digest: the full and deep tiers of a video Source page (LLM: one Claude read per chosen frame).

    full  the top anchors at ~15 per hour, at least 2 min apart
    deep  ~30 per hour, at least 1 min apart (the agent then also writes Connections)
Anchors are picked by score, skipping near-duplicate thumbnails (a page shown twice) and anchors scoring
below 1. Each is re-grabbed at full resolution from the cached video (re-downloaded when missing), cropped
to the board on a blackboard lecture and read by Claude with the transcript around it as context.
The page gets a `## Frames` section (thumbnail embed + read per frame) and, when empty, a draft
`## Key equations` from the reads; the agent finishes the summary sections and runs `ops commit`.
"""
import json
import os
import re

from ..paths import ROOT, sha1_file
from . import bundle, fetch as fetch_mod, frames as fx, readers
from .transcript import ts

TIERS = {"full": (15, 120), "deep": (30, 60)}       # anchors per hour, minimum gap in seconds
MIN_K, MAX_K = 4, 60
DUP_BITS = 6                                        # dHash distance under which two thumbnails are one picture
CACHE = os.path.join(ROOT, "meta", ".ingest", "video")
_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)


def pick(anchors, duration, tier, root):
    """Top anchors by score with a time gap and no near-duplicate thumbnails, in time order."""
    rate, gap = TIERS[tier]
    k = max(MIN_K, min(MAX_K, round(rate * duration / 3600)))
    from PIL import Image
    chosen, hashes = [], []
    for x in sorted(anchors, key=lambda x: (-x["score"], x["t"])):
        if x["score"] < 1 or len(chosen) >= k:
            break
        if any(abs(x["t"] - c["t"]) < gap for c in chosen):
            continue
        h = None
        try:
            h = fx.dhash(Image.open(os.path.join(root, x["thumb_path"])))
        except OSError:
            pass
        if h is not None and any(fx.hamming(h, o) <= DUP_BITS for o in hashes):
            continue
        words = fx.words(x.get("ocr") or [])
        same = next((c for c in chosen if _same_words(words, fx.words(c.get("ocr") or []))), None)
        if same is not None:                       # the same page or slide again: keep its fuller state
            others = [c for c in chosen if c is not same]
            if len(words) > len(fx.words(same.get("ocr") or [])) and \
                    not any(abs(x["t"] - c["t"]) < gap for c in others):
                chosen[chosen.index(same)] = x
                if h is not None:
                    hashes.append(h)
            continue
        chosen.append(x)
        if h is not None:
            hashes.append(h)
    return sorted(chosen, key=lambda x: x["t"])


def _same_words(a, b, share=0.8):
    if len(a) < 6 or len(b) < 6:
        return False
    inter = len(a & b)
    return inter >= share * min(len(a), len(b))


def display_blocks(text):
    """`$$x$$` on one line is inline math to remark-math: give every display formula its own lines."""
    return _DISPLAY.sub(lambda m: "\n$$\n" + m.group(1).strip() + "\n$$\n", text).strip()


def frames_section(chosen, url):
    out = ["## Frames", "",
           "_Frames chosen from the video's anchors and read by Claude with the transcript around each "
           "(video-digest). Thumbnails link the raw bundle; [occluded] marks what the speaker hid._", ""]
    for x in chosen:
        out += [f"### [{ts(x['t'])}]({url}&t={x['t']}s) · {x['kind']}", "",
                f"![{ts(x['t'])}](../{x['thumb_path']})", "",                  # relative to wiki/, as Obsidian reads it
                display_blocks(x["read"].get("text") or "_(no read)_"), ""]
    return "\n".join(out).rstrip() + "\n"


def _eq_key(body):
    """Two reads of the same formula differ in spacing, \\geq vs \\ge, \\bar vs \\vec: compare without them."""
    k = re.sub(r"\\(?:quad|qquad|,|;|!|:|\s)|\\text\{[^}]*\}|\s+|~", "", body)
    k = k.replace("\\geq", "\\ge").replace("\\leq", "\\le").replace("\\vec", "\\bar").replace("\\overline", "\\bar")
    return re.sub(r"[{}]", "", k)


def equations(chosen, limit=14):
    seen, out = set(), []
    for x in chosen:
        for m in _DISPLAY.finditer(x["read"].get("text") or ""):
            body = " ".join(m.group(1).split())
            key = _eq_key(body)
            if len(key) > 6 and key not in seen:
                seen.add(key)
                out.append(f"$$\n{body}\n$$")
            if len(out) >= limit:
                return out
    return out


def put_section(text, heading, body, before=("## Takeaways for my thesis", "## Connections", "## Links out",
                                              "## My notes")):
    """Replace `heading`'s section, or insert it before whichever of `before` comes first in the page (so
    never inside or after `## My notes`), else at the end."""
    lines = body.rstrip() + "\n\n"
    m = re.search(rf"^{re.escape(heading)}\s*$.*?(?=^## |\Z)", text, re.M | re.S)
    if m:
        return text[:m.start()] + lines + text[m.end():]
    hits = [i for i in (text.find(f"\n{b}") for b in before) if i >= 0]
    if hits:
        i = min(hits)
        return text[:i + 1] + lines + text[i + 1:]
    return text.rstrip() + "\n\n" + lines


def frames_on_page(text):
    """How many read frames the page's ## Frames section already holds."""
    m = re.search(r"^## Frames\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return 0
    return sum(1 for blk in re.split(r"^### ", m.group(1), flags=re.M)[1:] if "_(no read)_" not in blk)


def section_empty(text, heading):
    m = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m is None or len(m.group(1).strip()) < 8


def video_digest(arg, tier="full", model=readers.READ_MODEL, workers=4, backend=None):
    """Read the chosen frames and write them onto the video page (depth full/deep). Returns the page path.
    `backend`: kb.llm's subscription / api / batch for the frame reads (all frames in one run)."""
    from kb.core import wikiio
    from .. import easy_digest as ed
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {sorted(TIERS)}")
    raw_rel = ed._resolve_raw(arg)
    if not raw_rel.startswith("raw/videos/") or not raw_rel.endswith(f"/{bundle.ITEM}"):
        raise ValueError(f"{raw_rel}: video-digest takes a cataloged bundle's raw/videos/<name>/video.md")
    folder_rel = os.path.dirname(raw_rel)
    d = bundle.load(os.path.join(ROOT, raw_rel))
    anchors = [{**x, "thumb_path": f"{folder_rel}/{x['thumb']}"} for x in d.get("anchors") or []]
    if not anchors:
        raise ValueError(f"{raw_rel} has no anchors — re-scrap it with this version (scrap-youtube --force)")
    chosen = pick(anchors, d["duration"], tier, ROOT)
    if not chosen:
        raise ValueError(f"{raw_rel}: no anchor scores 1 or more — nothing worth reading (easy-digest it instead)")
    print(f"{tier}: {len(chosen)} of {len(anchors)} anchors → reading …")

    work = os.path.join(CACHE, sha1_file(raw_rel))
    os.makedirs(work, exist_ok=True)
    mp4 = _video(d["url"])
    cv2 = fx._cv()
    cap = cv2.VideoCapture(mp4)
    paths = {}
    for x in chosen:
        img = fx.grab(cap, x["t"])
        if img is None:
            continue
        box = fx.board_crop_box(img) if x["kind"] == "board" else None
        (img.crop(box) if box else img).convert("RGB").save(p := os.path.join(work, f"f-{x['t']:05d}.jpg"), quality=88)
        paths[x["t"]] = p
    grabbed = [x for x in chosen if x["t"] in paths]
    reads = dict(zip((x["t"] for x in grabbed),
                     readers.claude_reads([(paths[x["t"]], _context(d, x["t"])) for x in grabbed], model=model,
                                          backend=backend, workers=workers)))
    for x in chosen:
        x["read"] = reads.get(x["t"], {"text": ""})
    ok = [x for x in chosen if x["read"].get("text")]
    stats = {"tier": tier, "anchors": len(anchors), "chosen": len(chosen), "read": len(ok),
             "tokens_in": sum(x["read"].get("tokens_in") or 0 for x in ok),
             "tokens_out": sum(x["read"].get("tokens_out") or 0 for x in ok),
             "usd": round(sum(x["read"].get("usd") or 0 for x in ok), 3),
             "backend": next((x["read"]["backend"] for x in chosen if x["read"].get("backend")), "")}
    with open(os.path.join(work, "reads.json"), "w", encoding="utf-8") as fh:
        json.dump({"stats": stats, "frames": [{k: x[k] for k in ("t", "kind", "score", "why", "thumb_path", "read")}
                                              for x in chosen]}, fh, ensure_ascii=False, indent=1)

    if not ok:
        errors = {x["read"].get("error") for x in chosen if x["read"].get("error")}
        raise ValueError(f"no frame could be read{f' ({sorted(errors)[0]})' if errors else ''} — subscription: is "
                         "`claude` logged in / within its usage limit? api/batch: is the key set and funded? "
                         "The page is unchanged; rerun later")
    page_type = "video"
    slug = os.path.basename(ed.existing_digest_for_raw(raw_rel) or "")[:-3] or \
        ed.unit_slug_for_raw(raw_rel, page_type)
    wiki_path = os.path.join(ROOT, "wiki", f"{slug}.md")
    text = open(wiki_path, encoding="utf-8").read() if os.path.isfile(wiki_path) else ed._new_page(page_type, slug, raw_rel)
    had = frames_on_page(text)
    if len(ok) < had:
        raise ValueError(f"only {len(ok)} of {len(chosen)} frames were read, the page already holds {had} — "
                         "kept the page as it is; rerun later (reads are in meta/.ingest/video/)")
    from kb.core.schema import DEPTH
    from kb.lint.lint import parse_frontmatter
    old = (parse_frontmatter(text) or {}).get("depth")
    depth = max([d_ for d_ in (old, tier) if d_ in DEPTH], key=DEPTH.index)   # never downgrade deep to full
    text = wikiio.set_key(text, "depth", depth, after="status")
    text = wikiio.set_key(text, "status", "digested")
    text = put_section(text, "## Frames", frames_section(chosen, d["url"]))
    eqs = equations(ok)
    if eqs and section_empty(text, "## Key equations"):
        text = put_section(text, "## Key equations",
                           "## Key equations\n\n_Draft from the frame reads — keep the central ones._\n\n" + "\n\n".join(eqs),
                           before=("## Frames",))
    wikiio.write_page(wiki_path, text)
    with open(os.path.join(work, "abstract.text"), "w", encoding="utf-8") as fh:
        fh.write(_full_text(d, chosen))
    from .. import course                      # a course lecture's Contents row shows its new depth
    hub, n, row = course.hub_row_for_raw(raw_rel)
    if hub:
        course.record_row(hub, row["raws"], slug, depth)
        print(f"ticked [[{hub}]] row {n} ({depth})")
    print(f"read {len(ok)}/{len(chosen)} frames · {stats['tokens_in']:,} tokens in, {stats['tokens_out']:,} out "
          f"({stats['backend']} ${stats['usd']})")
    print(f"updated {wiki_path} ({page_type}, depth: {depth}) — ## Frames written, ## Key equations drafted")
    print(f"Agent: read {os.path.join(work, 'abstract.text')} (transcript + reads), write Problem, Main result, "
          f"Key ideas, curate Key equations, Takeaways{', Connections ([[links]] into the wiki)' if tier == 'deep' else ''}; "
          "then pixi run lint and pixi run ops -- commit")
    return wiki_path


def _context(d, t, before=60, after=20):
    out = []
    for s in d.get("sections") or []:
        if s["end"] >= t - before and s["start"] <= t + after:
            out.append(s["text"])
    text = " ".join(out)
    return text[-2500:]


def _full_text(d, chosen):
    parts = [f"Title: {d['title']}", f"Channel: {d.get('channel') or ''}", f"URL: {d['url']}",
             f"Duration: {ts(d['duration'])}", "", "Description:", (d.get("description") or "")[:2000], ""]
    if d.get("chapters"):
        parts += ["Chapters:"] + [f"- {ts(c['start'])} {c['title']}" for c in d["chapters"]] + [""]
    parts += ["Transcript:"]
    for s in d.get("sections") or []:
        parts += [f"[{ts(s['start'])}] {s['text']}"]
    parts += ["", "Frame reads:"]
    for x in chosen:
        parts += [f"[{ts(x['t'])}] {x['read'].get('text') or ''}", ""]
    return "\n".join(parts) + "\n"


def _video(url):
    """The cached video file, downloading it again when the cache was cleared."""
    vid = fetch_mod.video_id(url)
    folder = os.path.join(fetch_mod.CACHE, vid)
    for ext in (".mp4", ".webm", ".mkv", ".mov"):
        p = os.path.join(folder, vid + ext)
        if os.path.isfile(p):
            return p
    f = fetch_mod.fetch(url, video=True, comments=False, subs=False)   # only the pixels are needed here
    if not f.mp4:
        raise ValueError(f"could not download the video {url}")
    return f.mp4

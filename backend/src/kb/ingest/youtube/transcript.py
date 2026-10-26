"""WebVTT → cues → sections (chapters when the video has them), plus the comment filter."""
import html
import re

SECTION_S = 180            # target length of a section inside a long chapter
_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{3}) -->")
_TAG = re.compile(r"<[^>]+>")
_STAMP = re.compile(r"\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b")
_URL = re.compile(r"https?://[^\s)>\]]+")


def ts(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_vtt(text, auto=None):
    """[(start_seconds, text)]. A manual track has one caption per block. Auto captions roll: each
    block repeats the previous line and adds a word-timed new one, so only new last lines are kept.
    `auto` None: guess from the word-timing tags."""
    auto = "<c>" in text if auto is None else auto
    cues, prev = [], ""
    for block in re.split(r"\n\s*\n", text):
        m = _TIME.search(block)
        if not m:
            continue
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        lines = [html.unescape(_TAG.sub("", l)).strip() for l in block.split("\n")
                 if l.strip() and "-->" not in l and not l.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))]
        lines = [l for l in lines if l]
        if not lines:
            continue
        line = lines[-1] if auto else " ".join(lines)
        if line != prev:
            cues.append((start, line))
            prev = line
    return cues


def sections(cues, chapters=None, duration=None, target=SECTION_S):
    """Chapters split into parts of about `target` seconds, cut at a sentence end (hard cut at 1.5×).
    No chapters: the whole video is one unnamed chapter."""
    if not cues:
        return []
    end = duration or cues[-1][0] + 1
    chapters = [c for c in (chapters or []) if c.get("start_time") is not None] or \
        [{"title": "", "start_time": 0, "end_time": end}]
    out = []
    for ci, ch in enumerate(chapters):
        lo = ch["start_time"] if ci else 0
        hi = ch.get("end_time") or end
        part = [c for c in cues if lo <= c[0] < hi]
        cur = []
        for i, (s, t) in enumerate(part):
            cur.append((s, t))
            last = i + 1 == len(part)
            span = s - cur[0][0]
            if last or (span >= target and re.search(r"[.?!][\"')\]]?$", t)) or span >= target * 1.5:
                out.append({"chapter": ch.get("title") or "", "start": cur[0][0],
                            "end": part[i + 1][0] if not last else hi, "text": " ".join(x for _, x in cur)})
                cur = []
    return out


def links(description):
    return list(dict.fromkeys(_URL.findall(description or "")))


def keep_comments(comments, n=12):
    """Top-level comments worth reading: a timestamp, a link, a question or a long one, by likes.
    Thank-you notes are what most-liked lecture comments are; those are dropped."""
    out = []
    for c in sorted((c for c in comments or [] if c.get("parent") in (None, "root")),
                    key=lambda c: -(c.get("like_count") or 0)):
        text = (c.get("text") or "").strip()
        stamps = _STAMP.findall(text)
        if stamps or _URL.search(text) or "?" in text or len(text) >= 240:
            out.append({"author": c.get("author") or "", "likes": c.get("like_count") or 0,
                        "text": text[:600], "stamps": stamps})
        if len(out) >= n:
            break
    return out


def seconds(stamp):
    parts = [int(x) for x in stamp.split(":")]
    s = 0
    for p in parts:
        s = s * 60 + p
    return s

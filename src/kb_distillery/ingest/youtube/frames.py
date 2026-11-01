"""Where the visuals of a video are (0 LLM, OpenCV): the 1 fps pass, the per-video mode and the anchors.

Ingest stores anchors — candidate timestamps worth a frame, each with its reasons and a score — plus a
thumbnail of each; a digest tier later reads the top ones (kb_distillery.ingest.youtube.digest). Recall first: an
anchor of little value is kept with a low score, never dropped. Signals:
  board     the fullest board before each erase or camera cut (chalk = thin bright strokes inside the dark,
            smooth, rectangular board; a large changed-pixel fraction is a camera move, not content)
  slides    the last frame before each screen change; OCR words score it, and a slide that builds up marks
            its fullest state
  cues      transcript phrases that point at the screen ("as you can see", "this equation", "let me draw")
  chapter   the first content of each chapter
  coverage  the most stable second of any gap longer than COVER_S without an anchor (animation, paper,
            screencast: whatever the detectors miss)
Parameters come from the PoC runs (Stanford CME295 slides, MIT 6.034 blackboard, ritvikmath, StatQuest); animation-led
videos (3Blue1Brown) were tried and left out of scope — a frame budget cannot digest them well.
"""
import os
import re
import subprocess

import numpy as np

W, H = 320, 180
SLIDE_DIFF = 4.0          # mean |Δgrey| (0-255) that counts as a slide change
STABLE_S = 4              # a screen must stay this long to be a candidate
CUT_FRAC = 0.30           # changed-pixel fraction that means the camera moved or cut
MIN_SHOT_S = 3
ERASE_RATIO, ERASE_HOLD_S = 0.6, 3
MIN_BOARD, MIN_INK = 0.15, 250
BOARD_SHARE = 0.3         # share of seconds with a board in view that makes a board lecture
BOARD_INK = 200           # median chalk pixels on those seconds: below it the "board" is a table or a backdrop
WORDS_SAME = 0.85         # OCR word containment that makes two slides one
INK_SAME = 0.70           # chalk containment that makes two board frames one state
COVER_S = 90              # longest stretch without an anchor before coverage adds one
MERGE_S = 8               # signals this close are one anchor
_WORD = re.compile(r"[a-z0-9]{2,}")
CUES = re.compile(r"\b(as you can see|this equation|this formula|let me (?:write|draw|put|show)|"
                  r"this (?:picture|diagram|graph|plot|slide|board|figure|curve)|"
                  r"look at (?:this|that|the)|i'?ll draw|draw (?:a|the|this)|on the board|next slide|"
                  r"you can see)\b", re.I)


def _cv():
    import cv2
    return cv2


# --- the 1 fps pass -----------------------------------------------------------------------------

def board_mask(g):
    """Chalkboard = dark AND smooth once chalk is median-filtered away, in big rectangular blobs
    (an audience or a black table is textured or ragged)."""
    cv2 = _cv()
    m = cv2.medianBlur(g, 7).astype(np.float32)
    mu = cv2.blur(m, (9, 9))
    sd = np.sqrt(np.maximum(cv2.blur(m * m, (9, 9)) - mu * mu, 0))
    raw = ((m < 75) & (sd < 7)).astype(np.uint8)
    raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(raw)
    keep = np.zeros_like(raw)
    for i in range(1, n):
        area, bw, bh = st[i, cv2.CC_STAT_AREA], st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]
        if area >= 0.02 * g.size and area >= 0.6 * bw * bh:
            keep[lab == i] = 1
    return cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))


def ink_map(g, mask):
    cv2 = _cv()
    th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, np.ones((9, 9), np.uint8))
    return (th > 30) & (cv2.erode(mask, np.ones((5, 5), np.uint8)) > 0)


def _features(chunk):
    """Board coverage and chalk pixels of a block of grey frames (runs in a worker process)."""
    out = []
    for g in chunk:
        m = board_mask(g)
        out.append((float(m.mean()), int(ink_map(g, m).sum())))
    return out


def analyse(mp4, ffmpeg, cache=None, workers=None):
    """Per second: grey frame, board coverage, chalk pixels, changed-pixel fraction, mean |Δ|."""
    if cache and os.path.isfile(cache):
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    p = subprocess.run([ffmpeg, "-v", "error", "-i", mp4, "-vf", f"fps=1,scale={W}:{H},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, H, W)
    chunks = [fr[i:i + 120] for i in range(0, len(fr), 120)]
    if workers == 1 or len(chunks) < 2:
        feats = [f for c in chunks for f in _features(c)]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
            feats = [f for part in ex.map(_features, chunks) for f in part]
    board = np.array([f[0] for f in feats], float)
    ink = np.array([f[1] for f in feats], np.int64)
    change, delta = np.ones(len(fr)), np.full(len(fr), 255.0)
    for i in range(1, len(fr)):                         # one frame pair at a time: memory stays flat
        d = np.abs(fr[i].astype(np.int16) - fr[i - 1])
        change[i], delta[i] = (d > 25).mean(), d.mean()
    out = {"fr": fr, "board": board, "ink": ink, "change": change, "delta": delta}
    if cache:
        np.savez(cache, **out)
    return out


def mode_of(a):
    """board: a dark board in view most of the time AND chalk on it (a black table under a paper page, as in
    ritvikmath, is dark and smooth but carries no chalk: median 4 px vs 1100–2000 on MIT, Manim)."""
    on = a["board"] > MIN_BOARD
    if float(on.mean()) <= BOARD_SHARE:
        return "slides"
    return "board" if float(np.median(a["ink"][on])) >= BOARD_INK else "slides"


# --- candidates ---------------------------------------------------------------------------------

def slide_candidates(a):
    """The last second before each change of a screen that stayed STABLE_S seconds."""
    out, start = [], 0
    delta = a["delta"]
    for t in range(1, len(delta) + 1):
        if t == len(delta) or delta[t] > SLIDE_DIFF:
            if t - 1 - start >= STABLE_S:
                out.append({"t": t - 1, "kind": "slide"})
            start = t
    return out


def board_candidates(a):
    board, ink, change = a["board"], a["ink"], a["change"]
    shots, start = [], 0
    for t in range(1, len(change) + 1):
        if t == len(change) or change[t] > CUT_FRAC:
            if t - start >= MIN_SHOT_S:
                shots.append((start, t))
            start = t + 1
    out = []
    for a0, b0 in shots:
        period, peak, low = a0, 0, 0
        for t in range(a0, b0 + 1):
            erased = False
            if t < b0 and peak and ink[t] < ERASE_RATIO * peak:
                low += 1
                erased = low >= ERASE_HOLD_S
            elif t < b0:
                low = 0
            if t == b0 or erased:
                seg = range(period, t - (ERASE_HOLD_S - 1 if erased else 0))
                if len(seg):
                    best = max(seg, key=lambda i: ink[i])
                    if board[best] >= MIN_BOARD and ink[best] >= MIN_INK:
                        out.append({"t": int(best), "kind": "board", "ink": int(ink[best]),
                                    "end": "erase" if erased else "cut"})
                period, peak, low = t, 0, 0
            else:
                peak = max(peak, ink[t])
    return out


# --- dedup --------------------------------------------------------------------------------------

def words(lines):
    return set(_WORD.findall(" ".join(lines).lower()))


def dedup_slides(cands):
    """Candidates carry `words`; later/fuller states of the same slide replace earlier ones."""
    kept = []
    for c in sorted(cands, key=lambda c: c["t"]):
        w = c["words"]
        if len(w) < 4:
            continue                                  # speaker-only shot
        hit = None
        for k in kept[-3:]:
            inter = len(w & k["words"])
            if inter >= WORDS_SAME * len(w) or inter >= WORDS_SAME * len(k["words"]):
                hit = k
                break
        if hit is None:
            kept.append(c)
        elif len(w) >= len(hit["words"]):
            hit.update(c)
    return kept


def _orb_view(ga, gb):
    """Homography from view a to view b, or None when not the same view (scale ~1)."""
    cv2 = _cv()
    orb = cv2.ORB_create(1500)
    ka, da = orb.detectAndCompute(ga, None)
    kb, db = orb.detectAndCompute(gb, None)
    if da is None or db is None or len(ka) < 20 or len(kb) < 20:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < 25:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if hm is None or inl.sum() < 25:
        return None
    scale = float(np.sqrt(abs(np.linalg.det(hm[:2, :2]))))
    return hm if 0.8 < scale < 1.25 else None


def _contained(ink_a, ink_b, hm):
    cv2 = _cv()
    wa = cv2.warpPerspective(ink_a.astype(np.uint8), hm, ink_b.shape[::-1]) > 0
    if not wa.sum():
        return 0.0
    near_b = cv2.dilate(ink_b.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return float((wa & near_b).sum() / wa.sum())


def dedup_boards(cands, fr):
    """The board states no later frame of the same view contains (a zoomed view is a separate close-up)."""
    cv2 = _cv()
    kept = []
    for c in sorted(cands, key=lambda c: c["t"]):
        g = cv2.resize(fr[c["t"]], (W * 2, H * 2))
        ink = cv2.resize(ink_map(fr[c["t"]], board_mask(fr[c["t"]])).astype(np.uint8), (W * 2, H * 2)) > 0
        cur = {**c, "_g": g, "_ink": ink}
        drop = False
        for k in [k for k in kept if c["t"] - k["t"] <= 300]:
            hm = _orb_view(k["_g"], g)
            if hm is None:
                continue
            if _contained(k["_ink"], ink, hm) > INK_SAME:
                kept.remove(k)                                       # cur extends k
            elif _contained(ink, k["_ink"], np.linalg.inv(hm)) > INK_SAME:
                drop = True                                          # cur is a subset of k
                break
        if not drop:
            kept.append(cur)
    for k in kept:
        k.pop("_g"), k.pop("_ink")
    return kept


# --- anchors ------------------------------------------------------------------------------------

def signals(a, mode, cues, chapters, slide_words=None):
    """Raw anchor signals [{t, why, score}] before merging (slide_words: {t: OCR word set})."""
    out = []
    if mode == "board":
        cands = board_candidates(a)
        fullest = {c["t"] for c in dedup_boards(cands, a["fr"])}
        out += [{"t": c["t"], "why": [f"board-{c['end']}"], "score": 3 if c["t"] in fullest else 1} for c in cands]
    else:
        cands = slide_candidates(a)
        if slide_words is not None:
            fullest = {c["t"] for c in dedup_slides([{**c, "words": slide_words.get(c["t"], set())} for c in cands])}
        else:
            fullest = {c["t"] for c in cands}
        out += [{"t": c["t"], "why": ["slide-change"], "score": 3 if c["t"] in fullest else 1} for c in cands]
    n = len(a["delta"])
    for s, text in cues:
        m = CUES.search(text)
        if m and s + 8 < n:
            out.append({"t": int(s) + 8, "why": [f"cue: {m.group(0).lower()}"], "score": 1})
    for c in chapters or []:
        t = int(c.get("start_time", c.get("start", 0)) or 0) + 20
        if t < n:
            out.append({"t": t, "why": [f"chapter: {c.get('title') or ''}"], "score": 1})
    return out


def merge(sig):
    """Signals within MERGE_S seconds are one anchor: reasons join, scores add, the stronger time wins."""
    out = []
    for x in sorted(sig, key=lambda x: x["t"]):
        if out and x["t"] - out[-1]["t"] <= MERGE_S:
            y = out[-1]
            y["why"] = y["why"] + [w for w in x["why"] if w not in y["why"]]
            if x["score"] > y.get("_best", 0):
                y["t"], y["_best"] = x["t"], x["score"]
            y["score"] += x["score"]
        else:
            out.append({"t": x["t"], "why": list(x["why"]), "score": x["score"], "_best": x["score"]})
    for y in out:
        y.pop("_best")
    return out


def cover(anchors, delta, cover_s=COVER_S):
    """Add the most stable second of every gap longer than cover_s, until none is left."""
    n = len(delta)
    ts = sorted(x["t"] for x in anchors)
    added = []
    edges = [0] + ts + [max(n - 1, 0)]
    for lo, hi in zip(edges, edges[1:]):
        while hi - lo > cover_s:
            a0, b0 = lo + 10, min(hi - 10, lo + cover_s)
            if b0 <= a0:
                break
            t = int(a0 + np.argmin(delta[a0:b0]))
            added.append({"t": t, "why": ["coverage"], "score": 0})
            lo = t
    return sorted(anchors + added, key=lambda x: x["t"])


def visual_score(img, kind):
    """Points for what a frame shows (chalk on a board, edges elsewhere); a blank frame loses points."""
    cv2 = _cv()
    g = cv2.resize(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY), (W, H))
    m = board_mask(g)
    chalk = int(ink_map(g, m).sum())
    if kind == "board":
        pts = min(3, chalk // 800) - (2 if m.mean() < 0.3 else 0)
    else:
        pts = min(3, int(float((cv2.Canny(g, 80, 160) > 0).mean()) * 60))
    if g.std() < 12:
        pts -= 3                                           # near-uniform: a fade, a black or white screen
    return pts, {"board": round(float(m.mean()), 2), "chalk": chalk}


def flatness(img):
    """Share of the frame that is flat (local std < 3): a slide is mostly plain background, a camera shot of
    the room or the speaker is not (CME295: slides 0.56–0.67, room shots 0.35–0.40)."""
    cv2 = _cv()
    g = cv2.resize(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY), (W, H)).astype(np.float32)
    mu = cv2.blur(g, (7, 7))
    sd = np.sqrt(np.maximum(cv2.blur(g * g, (7, 7)) - mu * mu, 0))
    return float((sd < 3).mean())


SKIP_CHAPTER = re.compile(r"\b(sponsor|sponsored|ad|ads|advert|patreon|merch|talent|thanks|thank you|credits|"
                          r"outro|subscribe|support (?:the|this) channel)\b", re.I)


def adjust(anchors, mode, chapters, duration):
    """Video-level score corrections once every anchor is measured: camera shots inside a slide lecture, and
    sponsor / credits stretches (a chapter named so, or the last 3% of the video)."""
    if mode == "slides" and anchors:
        flats = [x["flat"] for x in anchors]
        if float(np.percentile(flats, 90)) >= 0.7:                 # it has clean slides: the rest are room shots
            for x in anchors:
                if x["flat"] < 0.5:
                    x["score"] -= 3
                    x["why"] = x["why"] + ["camera shot"]
    spans = [(c.get("start_time", 0), c.get("end_time") or duration) for c in chapters or []
             if SKIP_CHAPTER.search(c.get("title") or "")]
    for x in anchors:
        if any(a <= x["t"] < b for a, b in spans) or (duration and x["t"] > 0.97 * duration):
            x["score"] -= 4
            x["why"] = x["why"] + ["sponsor/credits"]
    return anchors


def dhash(img, size=8):
    from PIL import Image
    px = np.asarray(img.convert("L").resize((size + 1, size), Image.BILINEAR), np.int16)
    return int("".join("1" if b else "0" for b in (px[:, 1:] > px[:, :-1]).flatten()), 2)


def hamming(a, b):
    return bin(a ^ b).count("1")


# --- crops and frames ---------------------------------------------------------------------------

def board_crop_box(img):
    """Bounding box of the board region of a full-size PIL frame (1st–99th percentile, +6 px)."""
    cv2 = _cv()
    g = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    m = board_mask(cv2.resize(g, (W, H)))
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    sx, sy = img.width / W, img.height / H
    x0, x1 = np.percentile(xs, [1, 99])
    y0, y1 = np.percentile(ys, [1, 99])
    return (max(0, int((x0 - 6) * sx)), max(0, int((y0 - 6) * sy)),
            min(img.width, int((x1 + 6) * sx)), min(img.height, int((y1 + 6) * sy)))


def grab(cap, t):
    from PIL import Image
    cv2 = _cv()
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
    ok, f = cap.read()
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) if ok else None

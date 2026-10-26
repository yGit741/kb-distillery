"""Which frames of a video are worth keeping (0 LLM, OpenCV).

Two modes, chosen per video from a 1 fps pass (the router; per-segment routing is a follow-up):
  slides  the last frame before each screen change, deduplicated on OCR words: a slide that builds
          up keeps its fullest state, templated slides that look alike stay apart
  board   chalk = thin bright strokes inside the dark, smooth, rectangular board region (the lecturer
          is a big blob, not chalk); a large changed-pixel fraction is a camera cut / pan / zoom, not
          content; per still shot and erase period the frame with the most chalk is kept; two frames of
          the same view whose chalk is contained one in the other are the same board state (fuller wins);
          a zoomed view of the same board is a close-up and is kept
`vibe` skips the 1 fps pass: 24 evenly spaced samples, the most informative one per third of the video.
Parameters come from the PoC runs (Stanford CME295 slides, MIT 6.034 blackboard).
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
WORDS_SAME = 0.85         # OCR word containment that makes two slides one
INK_SAME = 0.70           # chalk containment that makes two board frames one state
WIDE_H = 300              # a board crop lower than this is a wide overview strip
_WORD = re.compile(r"[a-z0-9]{2,}")


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


def analyse(mp4, ffmpeg, cache=None):
    """Per second: grey frame, board coverage, chalk pixels, changed-pixel fraction, mean |Δ|."""
    if cache and os.path.isfile(cache):
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    p = subprocess.run([ffmpeg, "-v", "error", "-i", mp4, "-vf", f"fps=1,scale={W}:{H},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, H, W)
    board = np.zeros(len(fr)); ink = np.zeros(len(fr), np.int64)
    change = np.ones(len(fr)); delta = np.full(len(fr), 255.0)
    for i, g in enumerate(fr):
        m = board_mask(g)
        board[i], ink[i] = m.mean(), ink_map(g, m).sum()
        if i:
            d = np.abs(g.astype(np.int16) - fr[i - 1])
            change[i], delta[i] = (d > 25).mean(), d.mean()
    out = {"fr": fr, "board": board, "ink": ink, "change": change, "delta": delta}
    if cache:
        np.savez(cache, **out)
    return out


def mode_of(a):
    return "board" if float((a["board"] > MIN_BOARD).mean()) > BOARD_SHARE else "slides"


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


# --- crops, budget, vibe ------------------------------------------------------------------------

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


def drop_wide(frames, window=120):
    """A wide overview strip is redundant when a close-up of the board is kept nearby."""
    close = [f["t"] for f in frames if f.get("kind") == "board" and f.get("h", WIDE_H) >= WIDE_H]
    return [f for f in frames if not (f.get("kind") == "board" and f.get("h", WIDE_H) < WIDE_H
                                      and any(abs(f["t"] - t) <= window for t in close))]


def budget(frames, sections, per_hour, duration):
    """At most `per_hour` frames, shared over sections by length, the highest-scoring ones first. A frame
    belongs to the last section starting at or before it (one before the first caption to the first);
    no sections (no transcript) means one window over the whole video."""
    cap = max(1, round(per_hour * duration / 3600))
    if len(frames) <= cap:
        return frames
    wins = [(s["start"], s["end"]) for s in sections] or [(0, duration or 1)]
    home = lambda t: max([i for i, (a, _) in enumerate(wins) if a <= t] or [0])
    groups = {}
    for f in frames:
        groups.setdefault(home(f["t"]), []).append(f)
    picked = []
    for i, mine in groups.items():
        a, b = wins[i]
        n = max(1, round(cap * (b - a) / max(duration, 1)))
        picked += sorted(mine, key=lambda f: -f.get("score", 0))[:n]
    if len(picked) > cap:                                   # many short sections: best `cap` overall
        picked = sorted(picked, key=lambda f: -f.get("score", 0))[:cap]
    elif len(picked) < cap:                                 # spare room: next best anywhere
        rest = sorted((f for f in frames if f not in picked), key=lambda f: -f.get("score", 0))
        picked += rest[:cap - len(picked)]
    return sorted(picked, key=lambda f: f["t"])


def grab(cap, t):
    from PIL import Image
    cv2 = _cv()
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
    ok, f = cap.read()
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) if ok else None


def info_score(img, ocr_lines):
    """How much a frame says: OCR words, or chalk on a board."""
    cv2 = _cv()
    g = cv2.resize(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY), (W, H))
    m = board_mask(g)
    return max(len(words(ocr_lines)) * 10, int(ink_map(g, m).sum()) // 20)


def vibe_times(duration, samples=24):
    lo, hi = duration * 0.05, duration * 0.95
    return [lo + (hi - lo) * i / (samples - 1) for i in range(samples)]


def pick_vibe(scored, duration, n=3):
    """The best-scoring sample of each third of the video (fewer when a third shows nothing)."""
    out = []
    for k in range(n):
        lo, hi = duration * k / n, duration * (k + 1) / n
        third = [s for s in scored if lo <= s["t"] < hi and s["score"] > 0]
        if third:
            out.append(max(third, key=lambda s: s["score"]))
    return out

"""Parse Gemini (and future LLM) chat clips into turns. Zero LLM, stdlib only."""
import hashlib
import os
import re
import sys

from kb_distillery.lint.lint import parse_frontmatter

# Provider -> (user marker, model marker). Extensible to chatgpt/claude later.
CHAT_MARKERS = {
    "gemini": ("**You**", "**Gemini**"),
    "claude": ("**You**", "**Claude**"),   # dashboard Chat tab exports (src/kb_distillery/services/chat.py)
}

_ALL_MARKERS = set()
for _u, _m in CHAT_MARKERS.values():
    _ALL_MARKERS.add(_u)
    _ALL_MARKERS.add(_m)

_MARKER_RE = re.compile(
    r"^(" + "|".join(re.escape(m) for m in sorted(_ALL_MARKERS, key=len, reverse=True)) + r")\s*$"
)
_FENCE_RE = re.compile(r"^(```|~~~)")
_TRAILING_SEP_RE = re.compile(r"\n-{3,}\s*$")
_OBS_GOOD_RE = re.compile(r"@obs-good\b")
_BIDI_RE = re.compile(r"[​-‏‪-‮﻿]")

_ROLE_BY_MARKER = {}
for _provider, (_u, _m) in CHAT_MARKERS.items():
    _ROLE_BY_MARKER[_u] = "user"
    _ROLE_BY_MARKER[_m] = "model"


class Fence:
    def __init__(self, lang, start_line, end_line, sha1, looks_runnable):
        self.lang = lang
        self.start_line = start_line
        self.end_line = end_line
        self.sha1 = sha1
        self.looks_runnable = looks_runnable

    def to_dict(self):
        return {
            "lang": self.lang,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "sha1": self.sha1,
            "looks_runnable": self.looks_runnable,
        }


class Turn:
    def __init__(self, role, text, start_line, end_line):
        self.role = role
        self.text = text
        self.start_line = start_line
        self.end_line = end_line
        self.fences = []
        self.norm = None
        self.hash = None
        self.chars = len(text)
        self.math = {"inline": 0, "display": 0, "delims": "none"}
        self.signal = None
        self.inline_visuals = len(GEMINI_VISUAL_RE.findall(text))

    def to_text_ref(self, clip_rel):
        return {"clip": clip_rel, "start_line": self.start_line, "end_line": self.end_line}


RUNNABLE_LANGS = {"html", "svg"}
# Gemini renders a code block inline through a per-page-load sandbox URL
# (<hash>.scf.usercontent.goog/svg-code-block/shim.html). The URL changes on every
# clip and carries no code, so it is masked before hashing and counted instead.
GEMINI_VISUAL_RE = re.compile(r'<iframe\b[^>]*\bsrc="https://[^"]*\.usercontent\.goog/[^"]*"[^>]*>(?:\s*</iframe>)?', re.I)
_RUNNABLE_RE = re.compile(r"<!DOCTYPE html|<html|<svg|<canvas", re.I)
_MATH_DOLLAR_RE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$(?!\$)", re.S)
_MATH_DISPLAY_DOLLAR_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
_MATH_PAREN_RE = re.compile(r"(?<!\\)\\\((.+?)\\\)", re.S)
_MATH_BRACKET_RE = re.compile(r"(?<!\\)\\\[(.+?)\\\]", re.S)


def is_chat(text):
    """True if text (or its head) contains at least one user marker and one model marker
    on their own line, outside any fence."""
    seen_user = False
    seen_model = False
    fence_open = None
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        fm = _FENCE_RE.match(stripped)
        if fm:
            marker = fm.group(1)
            if fence_open is None:
                fence_open = marker
            elif marker == fence_open:
                fence_open = None
            continue
        if fence_open is not None:
            continue
        m = _MARKER_RE.match(raw_line)
        if m:
            role = _ROLE_BY_MARKER[m.group(1)]
            if role == "user":
                seen_user = True
            else:
                seen_model = True
            if seen_user and seen_model:
                return True
    return False


def split_frontmatter(text):
    """Return (frontmatter_dict_or_None, body, body_start_line).
    body_start_line is 0-indexed line number where body begins.
    """
    if not text.startswith("---"):
        return None, text, 0
    end = text.find("\n---", 3)
    if end == -1:
        return None, text, 0
    fm = parse_frontmatter(text)
    if fm:
        for k, v in list(fm.items()):
            if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                fm[k] = v[1:-1]
    rest = text[end + 4:]
    # Skip the newline right after the closing '---'
    if rest.startswith("\n"):
        rest = rest[1:]
        consumed_line_end = end + 5
    else:
        consumed_line_end = end + 4
    body_start_line = text[:consumed_line_end].count("\n")
    return fm, rest, body_start_line


def _fence_sha1(lines):
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()[:12]


def parse_turns(text):
    """Parse chat markers into a list of Turn objects. Fence-aware: markers inside
    a fenced code block are body text, not turn boundaries."""
    fm, body, base_line = split_frontmatter(text)
    lines = body.split("\n")

    # Pass 1: find marker line indices, respecting fence state.
    boundaries = []  # (line_idx, role)
    fence_open = None
    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        fm_match = _FENCE_RE.match(stripped)
        if fm_match:
            marker = fm_match.group(1)
            if fence_open is None:
                fence_open = marker
            elif marker == fence_open:
                fence_open = None
            continue
        if fence_open is not None:
            continue
        m = _MARKER_RE.match(raw_line)
        if m:
            boundaries.append((i, _ROLE_BY_MARKER[m.group(1)]))

    if not boundaries:
        return []

    turns = []
    for idx, (line_idx, role) in enumerate(boundaries):
        body_start = line_idx + 1
        body_end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        turn_lines = lines[body_start:body_end]

        # Strip a trailing lone '---' separator line (Web Clipper convention),
        # only if it's outside a fence and the last non-blank line.
        j = len(turn_lines) - 1
        while j >= 0 and turn_lines[j].strip() == "":
            j -= 1
        if j >= 0 and turn_lines[j].strip() == "---":
            # confirm it's not inside an odd number of fence toggles up to j
            fence_count = sum(1 for k in range(j) if _FENCE_RE.match(turn_lines[k].strip()))
            if fence_count % 2 == 0:
                turn_lines = turn_lines[:j]

        turn_text = "\n".join(turn_lines).strip("\n")
        turn = Turn(role, turn_text, base_line + body_start + 1, base_line + body_end)
        _extract_fences(turn, turn_lines)
        _count_math(turn, turn_lines)
        turns.append(turn)

    return turns


def _extract_fences(turn, turn_lines):
    fence_open = None
    fence_lang = None
    fence_start = None
    fence_body = []
    for i, line in enumerate(turn_lines):
        stripped = line.strip()
        m = _FENCE_RE.match(stripped)
        if m:
            marker = m.group(1)
            if fence_open is None:
                fence_open = marker
                fence_lang = stripped[len(marker):].strip() or None
                fence_start = i
                fence_body = []
            elif marker == fence_open:
                body_text = "\n".join(fence_body)
                turn.fences.append(Fence(
                    lang=fence_lang,
                    start_line=turn.start_line + fence_start,
                    end_line=turn.start_line + i,
                    sha1=_fence_sha1(fence_body),
                    looks_runnable=(fence_lang or "").lower() in RUNNABLE_LANGS
                    or bool(_RUNNABLE_RE.search(body_text)),
                ))
                fence_open = None
            continue
        if fence_open is not None:
            fence_body.append(line)


def _count_math(turn, turn_lines):
    """Count math occurrences outside fences. Cheap heuristic: strip fence bodies first."""
    kept = []
    fence_open = None
    for line in turn_lines:
        stripped = line.strip()
        m = _FENCE_RE.match(stripped)
        if m:
            marker = m.group(1)
            if fence_open is None:
                fence_open = marker
            elif marker == fence_open:
                fence_open = None
            continue
        if fence_open is None:
            kept.append(line)
    text = "\n".join(kept)
    display_dollar = len(_MATH_DISPLAY_DOLLAR_RE.findall(text))
    text_wo_display = _MATH_DISPLAY_DOLLAR_RE.sub("", text)
    inline_dollar = len(_MATH_DOLLAR_RE.findall(text_wo_display))
    display_bracket = len(_MATH_BRACKET_RE.findall(text))
    inline_paren = len(_MATH_PAREN_RE.findall(text))

    turn.math["display"] = display_dollar + display_bracket
    turn.math["inline"] = inline_dollar + inline_paren
    has_dollar = (display_dollar + inline_dollar) > 0
    has_paren = (display_bracket + inline_paren) > 0
    if has_dollar and has_paren:
        turn.math["delims"] = "mixed"
    elif has_dollar:
        turn.math["delims"] = "dollar"
    elif has_paren:
        turn.math["delims"] = "latex-paren"
    else:
        turn.math["delims"] = "none"


def normalize_turn(turn):
    """Whitespace-collapsed, bidi-stripped, @obs-good-stripped, fence-substituted text
    for hashing. Marker stripped BEFORE hashing so adding it later doesn't fork the tree."""
    text = turn.text
    text = _OBS_GOOD_RE.sub("", text)
    text = _BIDI_RE.sub("", text)
    text = GEMINI_VISUAL_RE.sub("⟪ gemini-visual ⟫", text)

    # Replace each fence's body with a stable token so an unchanged answer with a
    # re-generated (but identical) code block still hashes the same, and a changed
    # one hashes differently.
    if turn.fences:
        lines = text.split("\n")
        # Re-derive fence line spans relative to turn.text (they were computed
        # relative to turn.start_line during extraction); recompute locally instead
        # for robustness against any earlier normalization.
        out_lines = []
        fence_open = None
        fence_idx = 0
        skip_body = False
        for line in lines:
            stripped = line.strip()
            m = _FENCE_RE.match(stripped)
            if m:
                marker = m.group(1)
                if fence_open is None:
                    fence_open = marker
                    out_lines.append(line)
                    skip_body = True
                elif marker == fence_open:
                    sha8 = turn.fences[fence_idx].sha1[:8] if fence_idx < len(turn.fences) else "?"
                    out_lines.append("⟪ fence:%s ⟫" % sha8)
                    out_lines.append(line)
                    fence_idx += 1
                    fence_open = None
                    skip_body = False
                continue
            if skip_body:
                continue
            out_lines.append(line)
        text = "\n".join(out_lines)

    text = re.sub(r"\s+", " ", text).strip()
    turn.norm = text
    return text


def turn_hash(norm):
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def parse_clip(text):
    """Full parse: returns (frontmatter, turns) with norm/hash filled in on each turn."""
    fm, _, _ = split_frontmatter(text)
    turns = parse_turns(text)
    for t in turns:
        normalize_turn(t)
        t.hash = turn_hash(t.norm)
    return fm, turns

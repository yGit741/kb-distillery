"""Normalize math delimiters to Obsidian's native $/$$ form. Stdlib only, 3.9-compatible.

Obsidian's built-in renderer understands $...$ / $$...$$ only — no math plugin
is installed. Older wiki pages and some scraped sources use \\(...\\) / \\[...\\]
(MathJax-style), which render as literal broken text. This module converts
between them without touching fenced code, inline code, or anything already
in dollar form.
"""
import re

_FENCE_RE = re.compile(r"^(```|~~~)", re.M)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

_DISPLAY_BRACKET_RE = re.compile(r"(?<!\\)\\\[(.+?)\\\]", re.S)
_INLINE_PAREN_RE = re.compile(r"(?<!\\)\\\((.+?)\\\)", re.S)
_LATEX_DOLLAR_RE = re.compile(r"\$latex\s+(.+?)\$", re.S | re.I)
_EQUATION_ENV_RE = re.compile(
    r"\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}", re.S
)

_NUL = "\x00"


def protected_spans(text):
    """Return sorted, merged (start, end) ranges that must not be rewritten:
    fenced code blocks (``` or ~~~), <script>/<style> blocks, and inline `code`.
    """
    spans = []

    # Fenced blocks: toggle on any line starting with ``` or ~~~.
    lines = text.split("\n")
    offset = 0
    fence_open = None
    fence_start = None
    for line in lines:
        stripped = line.lstrip()
        m = _FENCE_RE.match(stripped)
        if m:
            marker = m.group(1)
            if fence_open is None:
                fence_open = marker
                fence_start = offset
            elif marker == fence_open:
                spans.append((fence_start, offset + len(line)))
                fence_open = None
                fence_start = None
        offset += len(line) + 1  # +1 for the \n joined back
    if fence_open is not None:
        spans.append((fence_start, len(text)))

    for m in _SCRIPT_STYLE_RE.finditer(text):
        spans.append((m.start(), m.end()))

    for m in _INLINE_CODE_RE.finditer(text):
        spans.append((m.start(), m.end()))

    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _in_span(pos, spans):
    for s, e in spans:
        if s <= pos < e:
            return True
        if pos < s:
            break
    return False


def _rewrite_outside_spans(text, pattern, replace_fn, spans, stats_key, stats):
    """Apply `pattern` -> `replace_fn` only to matches fully outside `spans`."""
    out = []
    last = 0
    for m in pattern.finditer(text):
        if _in_span(m.start(), spans) or _in_span(m.end() - 1, spans):
            continue
        out.append(text[last:m.start()])
        out.append(replace_fn(m))
        stats[stats_key] = stats.get(stats_key, 0) + 1
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def has_legacy_math(text):
    """True if text contains \\(...\\), \\[...\\], or $latex ...$ outside protected spans."""
    spans = protected_spans(text)
    for pattern in (_DISPLAY_BRACKET_RE, _INLINE_PAREN_RE, _LATEX_DOLLAR_RE, _EQUATION_ENV_RE):
        for m in pattern.finditer(text):
            if not _in_span(m.start(), spans) and not _in_span(m.end() - 1, spans):
                return True
    return False


def normalize_math(text):
    """Rewrite legacy math delimiters to $.../$$...$$, skipping protected spans.

    Returns (new_text, stats) where stats has keys "display", "inline", "skipped_fenced".
    Idempotent: normalize_math(normalize_math(t)[0])[0] == normalize_math(t)[0].
    """
    stats = {"display": 0, "inline": 0, "skipped_fenced": 0}
    spans = protected_spans(text)
    skipped = 0
    for pattern in (_DISPLAY_BRACKET_RE, _INLINE_PAREN_RE, _LATEX_DOLLAR_RE, _EQUATION_ENV_RE):
        for m in pattern.finditer(text):
            if _in_span(m.start(), spans) or _in_span(m.end() - 1, spans):
                skipped += 1
    stats["skipped_fenced"] = skipped

    text = _rewrite_outside_spans(
        text, _DISPLAY_BRACKET_RE,
        lambda m: "$$" + m.group(1) + "$$",
        spans, "display", stats,
    )
    # Recompute spans is unnecessary: replacements are same-or-shorter length shifts
    # handled by re-deriving spans fresh each pass (protected content never changes shape
    # relative to itself; fence/code positions before this pattern's matches are untouched
    # because matches never overlap protected spans by construction).
    spans = protected_spans(text)
    text = _rewrite_outside_spans(
        text, _EQUATION_ENV_RE,
        lambda m: "$$" + m.group(1) + "$$",
        spans, "display", stats,
    )
    spans = protected_spans(text)
    text = _rewrite_outside_spans(
        text, _INLINE_PAREN_RE,
        lambda m: "$" + m.group(1) + "$",
        spans, "inline", stats,
    )
    spans = protected_spans(text)
    text = _rewrite_outside_spans(
        text, _LATEX_DOLLAR_RE,
        lambda m: "$" + m.group(1) + "$",
        spans, "inline", stats,
    )
    return text, stats

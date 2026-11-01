"""Deepen a page in place without losing what it already says about itself.

`draft` renders a paper-shaped page; for a source that already has a page (an easy blog post, say) the new
body replaces the old one but the frontmatter is merged: every field the page has stays, `depth` and `status`
come from the new draft, an empty field takes the draft's value, `related` is the union, and fields only the draft has are
added when they are not empty."""
import re

_KEY = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$")
EMPTY = {"", "[]", '""', "''", "null", "~"}
OVERWRITE = ("depth", "status")
KEEP = ("type", "layer", "raw", "related")             # never replaced by the draft (related is merged)
HUB_KEYS = ("series", "course")       # a page that names its blog/source does not also take a hub key


def split(text):
    """(frontmatter text without the fences, body) — ('', text) when there is no frontmatter."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    return text[4:end], text[end + 5:]


def parse(fm):
    """Ordered [(key, [lines])]: a key's lines are its own line plus any indented / list continuation."""
    out = []
    for line in fm.splitlines():
        m = _KEY.match(line)
        if m:
            out.append((m.group(1), [line]))
        elif out and line.strip():
            out[-1][1].append(line)
    return out


def _value(lines):
    m = _KEY.match(lines[0])
    return m.group(2).strip() if m else ""


def _empty(lines):
    return len(lines) == 1 and _value(lines) in EMPTY


def _items(value):
    if value.startswith("[") and value.endswith("]"):
        return [x.strip() for x in value[1:-1].split(",") if x.strip()]
    return None


def merge_frontmatter(existing_text, new_text):
    """The new page text with the existing page's frontmatter merged in (see the module docstring)."""
    ex_fm, _ = split(existing_text.replace("\r\n", "\n"))
    nw_fm, body = split(new_text)
    if not ex_fm:
        return new_text
    ex, nw = parse(ex_fm), dict(parse(nw_fm))
    have = {k for k, _ in ex}
    merged = []
    for key, lines in ex:
        new = nw.get(key)
        if new is not None and key in OVERWRITE:
            lines = new
        elif new is not None and key not in KEEP and _empty(lines) and not _empty(new):
            lines = new                                   # an empty field takes what the draft found
        elif new is not None and key == "related" and len(lines) == 1:
            old_items, new_items = _items(_value(lines)), _items(_value(new))
            if old_items is not None and new_items:
                union = list(dict.fromkeys([*old_items, *new_items]))
                lines = [f"related: [{', '.join(union)}]"]
        merged.append((key, lines))
    for key, lines in parse(nw_fm):
        if key in have or _empty(lines):
            continue
        if key in HUB_KEYS and ("blog" in have or "source" in have):
            continue
        merged.append((key, lines))
    head = "\n".join(line for _, lines in merged for line in lines)
    return f"---\n{head}\n---\n{body}"

"""The `description:` field (was `summary:` before schema 1.5): one English "what it is + main point" line per page,
and its staleness hash. `generated: {by}` says who wrote it: `human:<id>` (never rewritten by a tool) or
`summarize/<model>`.

`summary_from` stores `summary_hash(text)` of the page the summary was written from. The hash covers only
the parts that carry the page's point — the H1, the `**Problem:**` / `**Main result:**` lead lines and
the `## Key claims` section — so link, typo and Connections edits never mark a summary stale.
"""
import hashlib
import re

from kb_distillery.vault.links import PAGE_LINK

SUMMARY_MIN = 80
SUMMARY_MAX = 320
EXEMPT_TYPES = {"course"}
DIGESTED = {"easy", "full", "deep"}

_LEAD = re.compile(r"^\*\*(?:Problem|Main result):\*\*.*$", re.M)
_H1 = re.compile(r"^# .+$", re.M)
_HEBREW = re.compile(r"[֐-׿]")


def body_of(text):
    """The page without its frontmatter."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def section(body, heading):
    """The text under `## heading` up to the next `## `, or ''."""
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m.group(1).strip() if m else ""


def _point_text(body):
    """The body minus fenced code and the user/link sections, where H1 and lead lines can't count."""
    body = re.sub(r"^```.*?^```", "", body, flags=re.M | re.S)
    for h in ("My notes", "Links out"):
        body = re.sub(rf"^## {re.escape(h)}\s*$.*?(?=^## |\Z)", "", body, flags=re.M | re.S)
    return body


def summary_hash(text):
    """Short sha256 of the parts of a page a summary depends on (whitespace-normalised)."""
    body = _point_text(body_of(text))
    parts = _H1.findall(body)[:1] + _LEAD.findall(body) + [section(body, "Key claims")]
    norm = "\n".join(" ".join(p.split()) for p in parts if p)
    return hashlib.sha256(norm.encode()).hexdigest()[:12]


PRODUCER = "summarize"


def with_offset(ts):
    """An ISO 8601 datetime with a UTC offset: `ts` as given when it has one, a naive `ts` read as this machine's local
    time (what `time.strftime` wrote), None when it is not a datetime."""
    import datetime
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.astimezone()).isoformat(timespec="seconds")


def now_stamp():
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def tool_actor(model):
    """`generated.by` of a summary a tool wrote."""
    return f"{PRODUCER}/{model}"


def hand_written(fm):
    """Did the user write this page's description? (`generated.by` is a `human:<id>` actor: tools never overwrite it.)"""
    g = fm.get("generated")
    return isinstance(g, dict) and str(g.get("by") or "").startswith("human:")


def unquote(v):
    v = (v or "").strip() if isinstance(v, str) else ""
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v


def problems(summary):
    """Why a summary is not acceptable ([] = fine). Lint (schema 1.3) enforces the same list."""
    s = summary or ""
    out = []
    if not SUMMARY_MIN <= len(s) <= SUMMARY_MAX:
        out.append(f"length {len(s)} not in {SUMMARY_MIN}-{SUMMARY_MAX}")
    if "\n" in s:
        out.append("contains a newline")
    if "#" in s or '"' in s:
        out.append('contains # or " (breaks the flat frontmatter parser)')
    if "\\" in s or "[[" in s or "]]" in s:
        out.append("contains a backslash or a wikilink")
    if PAGE_LINK.search(s):
        out.append("contains a page link")
    if _HEBREW.search(s):
        out.append("not English (Hebrew letters)")
    return out


def needs_summary(fm):
    """Does this page's frontmatter call for a summary at all?

    Sources need one once digested (`depth` easy/full/deep; a `listed` stub has nothing to summarise);
    concept and collection pages carry no depth and always need one — except courses."""
    if fm.get("type") in EXEMPT_TYPES:
        return False
    return fm.get("depth") in DIGESTED if fm.get("depth") else True

"""Trust tiers: classify a hunk into one class and say which tier of the kb that class belongs to.

Classes: `links`, `format`, `typos`, `claims`, `structure`, `new_page` and the explicit ops `tombstone`, `split` (`merge` and
`rename` are reserved for producers not built yet). Tiers come from the kb's `[proposals]` table in kb.toml (keys `auto_apply`, `review`, `explicit`); a missing
key falls back to the base kit's `defaults/proposals.toml`. Classification is deterministic and uses no model.
"""
from __future__ import annotations

import os
import re

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover  (python < 3.11)
    tomllib = None           # type: ignore[assignment]

TIERS = ("auto_apply", "review", "explicit")
CLASSES = ("links", "format", "typos", "claims", "structure", "new_page", "tombstone", "merge", "split", "rename")
DEFAULTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kits", "base", "defaults",
                             "proposals.toml")

_LINK = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
_LIST_MARK = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", re.M)
_WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)
_NUMBER = re.compile(r"[-+]?\d[\d.,]*%?")
MIN_TYPO_WORD = 5        # shorter words flip meaning too easily (not/now, is/it) to count as a typo
NEGATIONS = frozenset({"never", "none", "nothing", "nobody", "cannot", "without", "unlike", "false"})


def _load(path):
    if tomllib is None or not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as f:
            table = tomllib.load(f).get("proposals")
    except (OSError, ValueError):
        return {}
    return table if isinstance(table, dict) else {}


def _clean(value):
    if not isinstance(value, list):
        return None
    return [str(v) for v in value if isinstance(v, str)]


def tiers(root: str) -> dict:
    """{auto_apply, review, explicit, source}; source is "kb.toml" when the kb sets at least one list, else "default"."""
    base = _load(DEFAULTS_FILE)
    own = _load(os.path.join(root, "kb.toml")) if root else {}
    out, source = {}, "default"
    for key in TIERS:
        mine = _clean(own.get(key))
        if mine is not None:
            source = "kb.toml"
        out[key] = mine if mine is not None else (_clean(base.get(key)) or [])
    out["source"] = source
    return out


def tier_of(klass: str, cfg: dict) -> str:
    """The tier a class sits in; a class no list names is reviewed, and `explicit` wins over the other lists."""
    if klass in cfg["explicit"]:
        return "explicit"
    if klass in cfg["auto_apply"]:
        return "auto_apply"
    return "review"


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _skeleton(text: str) -> str:
    """Only the letters and digits left once list markers, heading marks, whitespace and punctuation are gone."""
    text = _LIST_MARK.sub("", text)
    return "".join(ch for ch in text if ch.isalnum())


def _is_frontmatter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def _headings(text: str) -> list[str]:
    return [re.sub(r"^#{1,6}[ \t]+", "", ln).strip() for ln in text.splitlines() if re.match(r"^#{1,6}[ \t]", ln)]


def _is_typo(before: str, after: str) -> bool:
    a, b = _WORD.findall(before), _WORD.findall(after)
    if len(a) != len(b) or not a:
        return False
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    if len(diff) != 1:
        return False
    x, y = diff[0]
    if any(c.isdigit() for c in x + y):
        return False
    x, y = x.lower(), y.lower()
    if x in NEGATIONS or y in NEGATIONS or max(len(x), len(y)) < MIN_TYPO_WORD:
        return False
    return _distance(x, y) <= (2 if max(len(x), len(y)) >= 8 else 1)


def _numbers(text: str) -> list[str]:
    return _NUMBER.findall(text)


def classify_text(before: str, after: str) -> str:
    """The class of an edit to the prose of a page from its before/after text."""
    if _is_frontmatter(before) or _is_frontmatter(after):
        return "structure"
    if sorted(_headings(before)) != sorted(_headings(after)):
        return "structure"
    if _numbers(before) != _numbers(after):
        return "claims"           # a changed number is a changed claim, whatever else moved
    labels_b, labels_a = _LINK.sub(r"\1", before), _LINK.sub(r"\1", after)   # links reduced to their label text
    if before != after and labels_b == labels_a:
        return "links"            # a link added, retargeted or unwrapped; the words the reader sees are the same
    if _skeleton(before) == _skeleton(after):
        return "format"
    if _skeleton(labels_b) == _skeleton(labels_a):
        return "links"
    if _is_typo(before, after):
        return "typos"
    return "claims"


def classify_hunk(h: dict) -> str:
    """One class for a hunk, by its op first and its text second."""
    op = h.get("op")
    if op == "create_page":
        return "new_page"
    if op == "tombstone_page":
        return "tombstone"
    if op == "move_block":
        return "split"
    if op in ("set_frontmatter", "rewrite_link"):
        return "structure"
    return classify_text(h.get("before") or "", h.get("after") or "")

"""Report document model — plain dataclasses that serialize to JSON.

A `Doc` is a status (ok | warn | error), a headline and a list of `Section`s; each section holds
blocks. Every block carries a `kind` so renderers (and the dashboard's JS) can dispatch on it.
Statuses are always one of STATUSES; renderers map them to colours and glyphs.
"""
import dataclasses

STATUSES = ("ok", "warn", "error", "info")
RANK = {"error": 0, "warn": 1, "info": 2, "ok": 3}


def worst(*statuses):
    """The most severe of the given statuses ("ok" when none)."""
    found = [s for s in statuses if s in RANK]
    return min(found, key=RANK.__getitem__) if found else "ok"


@dataclasses.dataclass
class Banner:
    status: str
    title: str
    subtitle: str = ""
    kind: str = "banner"


@dataclasses.dataclass
class Stat:
    label: str
    value: str
    status: str = ""             # "" = neutral
    hint: str = ""


@dataclasses.dataclass
class Stats:
    items: list
    kind: str = "stats"


@dataclasses.dataclass
class Table:
    columns: list
    rows: list                   # list of lists of str
    caption: str = ""
    kind: str = "table"


@dataclasses.dataclass
class Card:
    title: str
    status: str = "ok"
    state: str = ""              # short chip text, e.g. "stale"
    facts: list = dataclasses.field(default_factory=list)   # [[label, value], …]
    notes: list = dataclasses.field(default_factory=list)   # extra lines (e.g. attached findings)
    fix: str = ""                # the one command that moves it forward
    link: str = ""
    id: str = ""


@dataclasses.dataclass
class Cards:
    items: list
    empty: str = "nothing here"
    kind: str = "cards"


@dataclasses.dataclass
class Item:
    status: str
    label: str
    detail: str
    fix: str = ""
    more: str = ""               # long text, collapsed by default (dashboard) / omitted (mail)


@dataclasses.dataclass
class Findings:
    items: list
    empty: str = "nothing to fix"
    kind: str = "findings"


@dataclasses.dataclass
class Text:
    text: str
    muted: bool = False
    kind: str = "text"


@dataclasses.dataclass
class Code:
    text: str
    label: str = ""
    kind: str = "code"


@dataclasses.dataclass
class Section:
    title: str
    blocks: list
    note: str = ""
    id: str = ""


@dataclasses.dataclass
class Doc:
    title: str
    status: str
    headline: str
    sections: list = dataclasses.field(default_factory=list)
    footer: list = dataclasses.field(default_factory=list)  # short lines
    generated: str = ""
    links: list = dataclasses.field(default_factory=list)   # [[label, url], …] shown in the footer

    def as_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d):
        """Inverse of as_dict() — rebuild a Doc from its JSON form (cached or logged reports)."""
        def block(b):
            b = dict(b)
            items = ITEM_TYPES.get(b["kind"])
            if items:
                b["items"] = [items(**i) for i in b["items"]]
            return BLOCK_TYPES[b["kind"]](**b)

        sections = [Section(**{**s, "blocks": [block(b) for b in s["blocks"]]}) for s in d.get("sections", [])]
        return cls(**{**d, "sections": sections})


BLOCK_TYPES = {"banner": Banner, "stats": Stats, "table": Table, "cards": Cards, "findings": Findings,
               "text": Text, "code": Code}
ITEM_TYPES = {"stats": Stat, "cards": Card, "findings": Item}

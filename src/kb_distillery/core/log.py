"""The one writer of wiki/log.md (the KB's activity timeline), an OKF v0.2 reserved file of the bundle root.

Every knowledge step is recorded through `append`; nothing else writes the file.
OKF shape: no frontmatter, `# Log`, then one `## YYYY-MM-DD` heading per day, newest day first, and under it the day's
entries, newest first. One entry is `### <op> | <summary>` plus ` ← ` and the backticked targets when there are any,
and optionally body lines below it. `parse` / `render` are the only places that know this layout.

`append` is idempotent: an entry already under its day (same op, summary and targets) is never written twice, so a
retried step cannot double-log. The date goes through `date_heading` only.
"""
import datetime
import os
import re

from kb_distillery.core.schema import LOG_REL as _LOG_REL

LOG_REL = os.path.join(*_LOG_REL.split("/"))
LOG_HEADER = "# Log\n"
DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$")
ENTRY = re.compile(r"^### (.+?)\s*$")


def _as_date(when):
    if when is None:
        return datetime.date.today()
    if isinstance(when, datetime.datetime):
        return when.date()
    if isinstance(when, datetime.date):
        return when
    return datetime.date.fromisoformat(str(when)[:10])


def date_heading(when=None):
    """The date part of a day heading; the single place the date format lives."""
    return _as_date(when).isoformat()


def entry(op, summary, targets=(), when=None):
    """One log entry heading, without the blank line around it. `when` is accepted for symmetry (the day heading holds it)."""
    line = f"### {op} | {summary}"
    if targets:
        line += " ← " + ", ".join(f"`{t}`" for t in targets)
    return line + "\n"


def parse(text):
    """[(date, [entry block, ...])] in file order; a block is the entry's lines (heading first) without the trailing
    blank lines. Anything before the first day heading (title, intro) is not part of the timeline."""
    days, cur_day, cur = [], None, None
    for line in text.split("\n"):
        m = DAY.match(line)
        if m:
            cur_day, cur = [m.group(1), []], None
            days.append(cur_day)
        elif cur_day is not None:
            if ENTRY.match(line):
                cur = [line]
                cur_day[1].append(cur)
            elif cur is not None:
                cur.append(line)
    for _d, blocks in days:
        for b in blocks:
            while b and not b[-1].strip():
                b.pop()
    return days


def render(days):
    """The file text for [(date, [block, ...])]; days are written newest first, entries as given."""
    out = [LOG_HEADER.rstrip("\n")]
    for date, blocks in days:
        if not blocks:
            continue
        out += ["", f"## {date}"]
        for b in blocks:
            out += ["", *b]
    return "\n".join(out) + "\n"


def latest(text, skip_targeted=False):
    """(date, heading text after `### `) of the newest entry; `skip_targeted` ignores entries carrying a ` ← ` target."""
    for date, blocks in parse(text):
        for b in blocks:
            title = ENTRY.match(b[0]).group(1)
            if not (skip_targeted and "←" in title):
                return date, title
    return None


def append(root, op, summary, targets=(), when=None):
    """Add one entry to <root>/wiki/log.md (created when missing), at the top of its day. Returns True when written,
    False when the identical entry is already there."""
    if isinstance(targets, str):
        targets = (targets,)
    date = date_heading(when)
    head = entry(op, summary, tuple(targets), when).rstrip("\n")
    path = os.path.join(root, LOG_REL)
    try:
        with open(path, encoding="utf-8") as f:
            days = parse(f.read())
    except FileNotFoundError:
        days = []
    day = next((d for d in days if d[0] == date), None)
    if day is not None and any(b[0] == head for b in day[1]):
        return False
    if day is None:
        day = [date, []]
        days.append(day)
        days.sort(key=lambda d: d[0], reverse=True)          # stable: equal dates keep their order
    day[1].insert(0, [head])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(days))
    return True

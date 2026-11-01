"""The one writer of meta/log.md (the KB's activity timeline).

Every knowledge step appends one entry through `append`; nothing else writes the file.
Entry format (kept byte-for-byte): a blank line, then
`## [YYYY-MM-DD] <op> | <summary>` plus ` ← ` and the backticked targets when there are any.

`append` is idempotent: an entry already in the file (same op, summary, targets and date) is
never written twice, so a retried step cannot double-log. The date goes through `date_heading`
only, so a later change of the heading style is a change in that one function.
"""
import datetime
import os

LOG_REL = os.path.join("meta", "log.md")
LOG_HEADER = "# Log\n"


def _as_date(when):
    if when is None:
        return datetime.date.today()
    if isinstance(when, datetime.datetime):
        return when.date()
    if isinstance(when, datetime.date):
        return when
    return datetime.date.fromisoformat(str(when)[:10])


def date_heading(when=None):
    """The date part of an entry heading; the single place the date format lives."""
    return f"[{_as_date(when).isoformat()}]"


def entry(op, summary, targets=(), when=None):
    """One log entry, without the leading blank line."""
    line = f"## {date_heading(when)} {op} | {summary}"
    if targets:
        line += " ← " + ", ".join(f"`{t}`" for t in targets)
    return line + "\n"


def append(root, op, summary, targets=(), when=None):
    """Append one entry to <root>/meta/log.md (created when missing). Returns True when written,
    False when the identical entry is already there."""
    if isinstance(targets, str):
        targets = (targets,)
    text = entry(op, summary, tuple(targets), when)
    path = os.path.join(root, LOG_REL)
    try:
        with open(path, encoding="utf-8") as f:
            current = f.read()
    except FileNotFoundError:
        current = None
    if current is not None and text.rstrip("\n") in current.splitlines():
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if current is None:
            f.write(LOG_HEADER)
        elif not current.endswith("\n"):
            f.write("\n")
        f.write("\n" + text)
    return True

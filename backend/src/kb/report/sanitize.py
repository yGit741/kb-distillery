"""Text cleaners for anything that goes into a report block.

Tool output (wrangler, git, pytest) arrives with ANSI colours, banners and absolute paths; a
report wants one readable line. `summarize_error` keeps the lead ("wrangler deploy exited 1")
and the line that actually says what broke ("fetch failed").
"""
import os
import re

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
BARE_SGR = re.compile(r"\[(?:\d{1,3};)*\d{1,3}m")          # SGR codes whose ESC was lost in transit
NOISE = [re.compile(p, re.I) for p in (
    r"newer version of wrangler", r"update available", r"consider checking whether upgrading",
    r"^[\s─━\-=_~·.]+$", r"⛅", r"logs were written to", r"please create an issue",
    r"^🪵", r"^\s*at\s+\S+\s+\(", r"^npm (warn|notice)",
)]
ERRORISH = re.compile(r"\[ERROR\]|✘|\berror\b|\bfailed\b|\bfatal\b|exception", re.I)
MARKERS = re.compile(r"^\s*(?:✘|✗|×)?\s*(?:\[ERROR\]|ERROR:?|error:)\s*", re.I)


def strip_ansi(text):
    return BARE_SGR.sub("", ANSI.sub("", text or ""))


def truncate(text, limit=160):
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_path(text, root=None, home=None):
    """Absolute vault / home paths inside `text` → vault-relative (`.claude/worktrees/x`) / `~/…`."""
    if not text:
        return text or ""
    home = home if home is not None else os.path.expanduser("~")
    for r in {os.path.realpath(root), root} if root else ():
        r = r.rstrip("/")
        if r and r != "/":
            text = text.replace(r + "/", "").replace(r, ".")
    if home and home != "/":
        text = text.replace(home.rstrip("/") + "/", "~/")
    return text


def meaningful_lines(text):
    out = []
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if line and not any(p.search(line) for p in NOISE):
            out.append(line)
    return out


def summarize_error(text, limit=160):
    """One line: `<lead before the first colon>: <last error-marked line>`, or the first meaningful line."""
    lines = meaningful_lines(text)
    if not lines:
        return ""
    lead = lines[0]
    if lead.startswith("Traceback"):              # a Python traceback: the exception is the last line
        return truncate(lines[-1], limit)
    marked = [MARKERS.sub("", line).strip() for line in lines[1:] if ERRORISH.search(line)]
    marked = [m for m in marked if m]
    if marked:
        head = lead.split(":", 1)[0].strip() if ":" in lead else lead
        return truncate(f"{head}: {marked[-1]}", limit)
    return truncate(lead, limit)


def clean_block(text, root=None, max_lines=40):
    """Multi-line tool output for a Code block: no ANSI, no noise, short paths, last `max_lines`."""
    lines = [short_path(line, root) for line in meaningful_lines(text)]
    return "\n".join(lines[-max_lines:])

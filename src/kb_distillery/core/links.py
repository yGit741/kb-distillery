"""The one place that knows how a page link is written.

Today pages link with wikilinks (`[[slug]]`, `[[slug|label]]`, `[[slug#heading]]`).
Every reader used to carry its own copy of the regex; they import it from here.

`to_llm` is what a prompt or a reader sees, `to_disk` is what a writer stores. They
are the identity until the on-disk link form changes (OKF PR8): that switch then
happens in these two functions only, and no caller changes.
"""
import re

# Target slug only: `[[slug` up to `|`, `#`, `]` or an escaped pipe. Use with findall/search.
WIKILINK_TARGET = re.compile(r"\[\[([^\]|#\\]+)")

# Whole link with groups (slug, label). A `#heading` part is allowed and dropped.
WIKILINK = re.compile(r"\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]")


def targets(text: str) -> list[str]:
    """Stripped link targets of `text`, in order, duplicates kept."""
    return [m.strip() for m in WIKILINK_TARGET.findall(text or "")]


def to_llm(text: str) -> str:
    """Page text as shown to a model or a reader."""
    return text


def to_disk(text: str) -> str:
    """Text as a writer stores it in a page."""
    return text

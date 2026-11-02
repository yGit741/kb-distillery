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


# -- page paths in frontmatter (`related`, `sources[].resource`) ---------------------------------------------------
PAGE_SUFFIX = ".md"


def page_path(slug: str) -> str:
    """How frontmatter names the wiki page `slug`. Nothing else may build this string."""
    return f"{slug}{PAGE_SUFFIX}"


def page_slug(ref) -> str | None:
    """Inverse of `page_path`: the slug a frontmatter page reference names, else None (a URL, a `think:` descriptor,
    a path with folders). A bare slug is accepted too, so a not yet migrated field still reads."""
    ref = str(ref or "").strip().strip("\"'")
    if not ref or "/" in ref or ":" in ref or ref.startswith("."):
        return None
    return ref[:-len(PAGE_SUFFIX)] if ref.endswith(PAGE_SUFFIX) else ref


def resolve_slug(name, slugs, aliases=None, mentions=None) -> str | None:
    """The current wiki slug a name refers to, else None. Order: an exact slug, a page's `aliases:` (an old slug),
    then a `meta/aliases.tsv` mention (lower-cased, may hold spaces)."""
    name = str(name or "").strip()
    if not name:
        return None
    if name in slugs:
        return name
    old = (aliases or {}).get(name)
    if old in slugs:
        return old
    hit = (mentions or {}).get(name.lower())
    return hit if hit in slugs else None


def alias_map(pages) -> dict:
    """{old slug: current slug} from `pages` = {slug: frontmatter dict} (the `aliases:` lists)."""
    out = {}
    for slug, fm in pages.items():
        raw = fm.get("aliases") or []
        for a in [raw] if isinstance(raw, str) else raw:
            a = str(a).strip().strip("\"' ")
            if a and a != slug:
                out.setdefault(a, slug)
    return out


def mention_map(path) -> dict:
    """{mention.lower(): slug} from a `meta/aliases.tsv` (two tab-separated columns, `#` comments)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                parts = line.split("\t")
                if line.startswith("#") or len(parts) < 2 or not parts[0].strip():
                    continue
                out.setdefault(parts[0].strip().lower(), parts[1].strip())
    except OSError:
        pass
    return out


def refs(value) -> list[str]:
    """Slugs named by a frontmatter list of page references (`related`)."""
    if value in (None, ""):
        return []
    items = [value] if isinstance(value, (str, dict)) else list(value)
    return [s for s in (page_slug(i) for i in items if isinstance(i, str)) if s]


def source_slugs(value) -> list[str]:
    """Slugs of the wiki pages named by `sources` entries (objects with a `resource`, or legacy bare slugs)."""
    if value in (None, ""):
        return []
    items = [value] if isinstance(value, (str, dict)) else list(value)
    out = []
    for item in items:
        res = item.get("resource") if isinstance(item, dict) else item
        slug = page_slug(res) if isinstance(res, str) else None
        if slug:
            out.append(slug)
    return out

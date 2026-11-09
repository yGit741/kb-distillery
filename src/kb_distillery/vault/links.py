"""The one place that knows how a page link is written.

On disk a page links to another page with a standard relative markdown link, `[Title](slug.md)` (Open Knowledge
Format v0.2; `wiki/` is the bundle root and pages are flat), with `#anchor` for a heading: `[label](slug.md#heading)`.
Wikilinks (`[[slug]]`, `[[slug|label]]`, `[[slug#heading]]`) survive in exactly two places: the user's own
`## My notes` section (never rewritten) and a few extension fields. Every reader imports its regex from here and
`targets()` reads both forms, so nothing double-counts or loses an edge.

`link()` is how a writer spells a link, `to_disk()` turns the wikilinks a model or an old template wrote into the
on-disk form, `convert()` is the engine both the migration and `to_disk()` share. `to_llm` is the identity: a model
reads the same markdown a person reads.
"""
import re
from functools import lru_cache

# -- the legacy wikilink form (My notes, extension fields, model output) ---------------------------------------------
# Target slug only: `[[slug` up to `|`, `#`, `]` or an escaped pipe. Use with findall/search.
WIKILINK_TARGET = re.compile(r"\[\[([^\]|#\\]+)")

# Whole link with groups (slug, label). A `#heading` part is allowed and dropped.
WIKILINK = re.compile(r"\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]")

# Any `[[...]]` or `![[...]]` on one line, inner text unparsed (convert() splits it).
WIKILINK_ANY = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")

# -- the on-disk form: [label](slug.md) or [label](slug.md#anchor) ------------------------------------------------------
# label: any text, `[`, `]` and `\` escaped. slug: a flat page name (no folder, no scheme). Groups: label, slug, anchor.
PAGE_LINK = re.compile(r"(?<!!)\[((?:[^\[\]\\\n]|\\.)*)\]\(([^()<>\s/:#]+?)\.md(?:#([^()\s]*))?\)")

# A row of a generated index: PAGE_LINK, from the root index (`slug.md`) or a section index (`../slug.md`, `../../slug.md`).
INDEX_LINK = re.compile(r"(?<!!)\[((?:[^\[\]\\\n]|\\.)*)\]\((?:\.\./)*([^()<>\s/:#]+?)\.md(?:#([^()\s]*))?\)")
_LINK_TARGET = re.compile(r"\[\[([^\]|#\\]+)|(?<!!)\[(?:[^\[\]\\\n]|\\.)*\]\(([^()<>\s/:#]+?)\.md[)#]")


_COMMENT = re.compile(r"<!--.*?-->", re.S)


@lru_cache(maxsize=2048)
def _targets(text: str) -> tuple[str, ...]:
    return tuple((m.group(1) or m.group(2)).strip() for m in _LINK_TARGET.finditer(_COMMENT.sub("", text)))


def targets(text: str) -> list[str]:
    """Stripped slugs `text` links to, in order, duplicates kept: markdown page links and (My notes) wikilinks. An
    HTML comment is not read (a template's `<!-- [Title](slug.md) -->` hint links nothing). Pure in `text`, so the
    scan is memoised (a graph build asks for the same page text several times); every call gets a fresh list."""
    return list(_targets(text or ""))


def wikilink_targets(text: str) -> list[str]:
    """Stripped targets of the wikilinks only."""
    return [m.strip() for m in WIKILINK_TARGET.findall(_COMMENT.sub("", text or ""))]


def escape_label(label: str) -> str:
    """Link text that reads as the literal `label`: backslash and square brackets escaped."""
    return re.sub(r"([\\\[\]])", r"\\\1", str(label))


def link(slug: str, label=None, anchor: str | None = None, up: int = 0) -> str:
    """`[label](slug.md#anchor)`: how a writer links a page. `label` defaults to the slug, `anchor` is a heading text
    (turned into its GitHub-style anchor) or an anchor already. `up` is for a generated section index that sits `up`
    folders below the bundle root (`wiki/paper/index.md` links `../slug.md`); a page never sets it."""
    frag = "#" + slugify(anchor) if anchor else ""
    return f"[{escape_label(' '.join(str(label if label is not None else slug).split()))}]({page_path(slug, up)}{frag})"


def page_link(slug: str, titles=None, label=None, up: int = 0) -> str:
    """A link to `slug` whose text is `label`, else the page's title as the app shows it (`titles` = {slug: title}),
    else the slug."""
    shown = label or shown_title(titles.get(slug, "") if isinstance(titles, dict) else "") or slug
    return link(slug, shown, up=up)


def link_parts(m) -> tuple[str, str, str]:
    """(unescaped label, slug, anchor) of a PAGE_LINK match."""
    return re.sub(r"\\(.)", r"\1", m.group(1)), m.group(2), m.group(3) or ""


def slugify(heading: str) -> str:
    """GitHub-style anchor of a heading (`Why it works` -> `why-it-works`)."""
    s = re.sub(r"[^\w\s-]", "", str(heading).strip().lower())
    return re.sub(r"\s", "-", s)


_TITLE = re.compile(r"^#\s+(.+)$", re.M)


def title_of(text: str, slug: str) -> str:
    """The title the app shows for a page (what a bare link to it displays): its first `# ` line after the front
    matter, else the slug with spaces. Page links to it use this as their text. Same rule as graph.snapshot._title."""
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    m = _TITLE.search(body)
    return m.group(1).strip() if m else slug.replace("-", " ")


def shown_title(title: str) -> str:
    """A title as the app shows it as link text: `[`, `]` and `|` become spaces (the reader's own rule)."""
    return " ".join(re.sub(r"[\[\]|]", " ", title or "").split())


def read_title(wiki_dir: str, slug: str) -> str:
    """The shown title of wiki_dir/<slug>.md; the slug when the page is missing."""
    import os
    try:
        with open(os.path.join(wiki_dir, f"{slug}.md"), encoding="utf-8") as f:
            return shown_title(title_of(f.read(), slug)) or slug
    except OSError:
        return slug


def read_titles(wiki_dir: str) -> dict:
    """{slug: shown title} of every flat page below `wiki_dir` (excalidraw drawings left out)."""
    import os
    from kb_distillery.vault.schema import is_page_file
    return {fn[:-3]: read_title(wiki_dir, fn[:-3]) for fn in sorted(os.listdir(wiki_dir))
            if is_page_file(fn) and "excalidraw" not in fn}


def plain(text: str) -> str:
    """`text` with each page link and wikilink reduced to its label (a bare wikilink to its slug)."""
    text = PAGE_LINK.sub(lambda m: link_parts(m)[0], text or "")
    return WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)


def to_llm(text: str) -> str:
    """Page text as shown to a model or a reader: the markdown a person reads (identity)."""
    return text


# -- regions a link rewrite must not touch --------------------------------------------------------------------------------
_PROTECTED = re.compile(
    r"(?P<fence>^[ \t]{0,3}(?P<f>`{3,}|~{3,})[^\n]*\n(?:.*?\n)?[ \t]{0,3}(?P=f)[ \t]*$|^[ \t]{0,3}(?:`{3,}|~{3,})[^\n]*\n.*\Z)"
    r"|(?P<code>(?P<t>`+)(?:(?!\n[ \t]*\n).)+?(?<!`)(?P=t)(?!`))"
    r"|(?P<comment><!--.*?-->)"
    r"|(?P<dmath>\$\$.+?\$\$)"
    r"|(?P<imath>(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d))",
    re.M | re.S)
_NOTES_HEAD = re.compile(r"^## My notes[ \t]*$", re.M)
_NEXT_H2 = re.compile(r"^## ", re.M)


def notes_spans(body: str) -> list[tuple[int, int]]:
    """(start, end) of every `## My notes` section of a body: its heading up to the next `## ` or the end. The
    user's own text: nothing in it is ever rewritten."""
    out = []
    for m in _NOTES_HEAD.finditer(body):
        nxt = _NEXT_H2.search(body, m.end())
        out.append((m.start(), nxt.start() if nxt else len(body)))
    return out


def protected_spans(body: str) -> list[tuple[int, int]]:
    """Sorted, merged (start, end) of the regions of `body` that are not prose: `## My notes`, fenced and inline
    code, math, HTML comments (the reader drops them). A `[[x]]` there is not a link (the reader never renders one)."""
    spans = notes_spans(body)
    spans += [m.span() for m in _PROTECTED.finditer(body)]
    return _merge(spans)


def _merge(spans):
    merged: list[list[int]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


# `[see [[x]]](https://…)`: a wikilink inside the text of a markdown link. The reader never makes it a link (it does
# not rewrite inside links) and a page link inside a link would nest, so convert() leaves the whole link alone.
_NESTED = re.compile(r"(?<!!)\[(?:[^\[\]\n]|\[\[[^\]\n]*\]\])*\[\[[^\]\n]*\]\](?:[^\[\]\n]|\[\[[^\]\n]*\]\])*\]\([^)\s]*\)")


def prose(body: str) -> str:
    """`body` with the protected regions blanked out (same length), for scanning links in the prose only."""
    out, last = [], 0
    for a, b in protected_spans(body):
        out.append(body[last:a])
        out.append(re.sub(r"[^\n]", " ", body[a:b]))
        last = b
    out.append(body[last:])
    return "".join(out)


def body_of(text: str) -> str:
    """A page without its front matter."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:] if end != -1 else text


def leftover_wikilinks(body: str) -> list[str]:
    """Raw `[[...]]` / `![[...]]` left in the prose of a body (not in My notes, code or math)."""
    return [m.group(0) for m in WIKILINK_ANY.finditer(prose(body))]


# -- converting wikilinks -----------------------------------------------------------------------------------------------
class Resolver:
    """What `convert()` needs to know about a vault: which slugs exist, their titles (as the app shows them), and how
    a name resolves (slug, `aliases:`, `meta/aliases.tsv`). `assets` maps a file name to its path from the page."""

    def __init__(self, slugs, titles=None, aliases=None, mentions=None, assets=None, headings=None):
        self.slugs, self.titles = set(slugs), titles or {}
        self.aliases, self.mentions, self.assets = aliases or {}, mentions or {}, assets or {}
        self.headings = headings or {}

    def slug(self, name):
        return resolve_slug(name, self.slugs, self.aliases, self.mentions)

    def title(self, name):
        """The title the app shows for a bare wikilink to `name`: only an exact slug has one."""
        t = self.titles.get(name) if name in self.slugs else None
        return shown_title(t) or None


def _convert_one(m, rs: Resolver, report):
    embed, inner = m.group(1), m.group(2)
    parts = re.split(r"\\?\|", inner, maxsplit=1)
    target, label = parts[0], (parts[1] if len(parts) > 1 else "")
    name, hash_, anchor = target.partition("#")
    name, label, anchor = name.strip(), label.strip(), anchor.strip()
    if embed:
        path = rs.assets.get(name)
        if path is None:
            report["embed_unresolved"].append(m.group(0))
            return m.group(0)
        return f"![{name}]({path})"
    if not name:
        report["empty"].append(m.group(0))
        return m.group(0)
    slug = rs.slug(name)
    if slug is None:
        report["unresolved"].append(m.group(0))
        return m.group(0)
    if hash_ and anchor and rs.headings and slugify(anchor) not in rs.headings.get(slug, {slugify(anchor)}):
        report["anchor_unresolved"].append(m.group(0))
        return m.group(0)
    shown = label or rs.title(name) or name
    report["converted"] += 1
    if slug != name:
        report["via_alias"] += 1
    frag = anchor if hash_ and anchor else None
    out = link(slug, shown, frag)
    size = lambda x: len(x.encode("utf-8"))
    for key, val in (("bytes_wikilink", m.group(0)), ("bytes_new", out), ("bytes_slug_form", link(slug, label or slug, frag))):
        report[key] = report.get(key, 0) + size(val)           # the cost of each form (the migration reports it)
    return out


def convert(body: str, rs: Resolver, report=None) -> str:
    """`body` with every wikilink in its prose written as `[shown text](slug.md)`. The shown text is what the app
    displays for the wikilink today: its label, else the page title (only for an exact slug), else the name as
    written. A link that does not resolve is left as it is and listed in `report['unresolved']`. My notes, code and
    math are copied byte for byte."""
    report = report if report is not None else new_report()
    out, last = [], 0
    spans = _merge(protected_spans(body) + [m.span() for m in _NESTED.finditer(body)])
    for a, b in spans + [(len(body), len(body))]:
        seg = body[last:a]
        out.append(WIKILINK_ANY.sub(lambda m: _convert_one(m, rs, report), seg))
        out.append(body[a:b])
        last = b
    return "".join(out)


def new_report() -> dict:
    return {"converted": 0, "via_alias": 0, "unresolved": [], "embed_unresolved": [], "anchor_unresolved": [], "empty": []}


def to_disk(text: str, titles=None, slugs=None) -> str:
    """Text as a writer stores it in a page: wikilinks a model or an old template wrote become page links. `titles`
    ({slug: title}) gives the shown text of a bare `[[slug]]`; `slugs` defaults to its keys. A name that is not a
    known page stays a wikilink (lint then reports it)."""
    titles = titles or {}
    rs = Resolver(slugs if slugs is not None else titles.keys(), titles)
    return convert(text, rs)


# -- page paths in frontmatter (`related`, `sources[].resource`) ---------------------------------------------------
PAGE_SUFFIX = ".md"


def page_path(slug: str, up: int = 0) -> str:
    """How frontmatter names the wiki page `slug`. Nothing else may build this string. `up` prefixes `../` for a link
    written from a section index below the bundle root."""
    return f"{'../' * up}{slug}{PAGE_SUFFIX}"


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

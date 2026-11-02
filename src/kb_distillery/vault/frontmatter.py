"""The one frontmatter reader for wiki pages (OKF-shaped since schema 1.5).

Flat `key: value` and `key: [a, b]` lines stay plain strings and lists, as before. Three shapes OKF needs on top:
a flow mapping (`generated: {by: x, at: y}`), a list of mappings (`sources: [{resource: a.md}]`), and the same as a
block (`key:` then indented `- ...` lines). Those go through YAML's BaseLoader, so every scalar stays a string: a date
is never turned into a `date` object, `no` never into a bool.
"""
import re

_COMMENT = re.compile(r"\s#.*$")
_QUOTED = re.compile(r'^("(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\')')


def to_lf(text):
    """(text with LF line ends, whether it was CRLF). A page with both CRLF and bare LF ends is ambiguous: ValueError."""
    if "\r\n" not in text:
        return text, False
    if "\n" in text.replace("\r\n", ""):
        raise ValueError("mixed CRLF and LF line ends")
    return text.replace("\r\n", "\n"), True


def from_lf(text, crlf):
    return text.replace("\n", "\r\n") if crlf else text


def restore_eols(orig, new_lf):
    """`new_lf` (LF text derived from `orig`) with every line end taken from the same line of `orig`, so CRLF, LF and
    mixed pages all come back as they were. ValueError when the line count changed (the ends could not be kept)."""
    ends = re.findall(r"\r?\n", orig)
    if "\r\n" not in orig:
        return new_lf
    parts = new_lf.split("\n")
    if len(parts) - 1 != len(ends):
        raise ValueError("line count changed")
    return "".join(p + (ends[i] if i < len(ends) else "") for i, p in enumerate(parts))


def mixed_line_ends(paths_texts):
    """The paths among (path, text) pairs whose text mixes CRLF and bare LF line ends."""
    out = []
    for path, text in paths_texts:
        try:
            to_lf(text)
        except ValueError:
            out.append(path)
    return out


def split_block(text):
    """(inner frontmatter text, body) or (None, text) when `text` has no fenced block."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end], text[end + 4:]


def _strip_comment(v):
    """`value  # note` -> `value`; a quoted value is taken whole, so a `#` inside quotes survives."""
    v = v.strip()
    m = _QUOTED.match(v)
    if m:
        return m.group(1)
    return _COMMENT.sub("", v).rstrip()


def _yaml(text):
    import yaml
    try:
        return yaml.load(text, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return None


# Keys whose indented block (`key:` then `- item` lines) is read; any other block is left to its own reader
# (`relations:` goes through graph/relations.py), so the flat reader sees it as empty exactly as before.
BLOCK_KEYS = frozenset({"sources", "related", "generated", "aliases"})


def _continues(line):
    return line.startswith((" ", "\t")) or line.startswith("- ") or line.rstrip() == "-"


def parse(text):
    """(frontmatter dict, body), or (None, text) when the page has no frontmatter block."""
    inner, body = split_block(text)
    if inner is None:
        return None, text
    lines = inner.splitlines()
    fm, i = {}, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line or _continues(line):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), _strip_comment(v)
        if v == "" and k in BLOCK_KEYS:
            block = []
            while i < len(lines) and (_continues(lines[i]) or not lines[i].strip()):
                block.append(lines[i])
                i += 1
            parsed = _yaml(f"{k}:\n" + "\n".join(block)) if any(b.strip() for b in block) else None
            fm[k] = parsed[k] if isinstance(parsed, dict) and k in parsed else ""
        elif v == "":
            fm[k] = ""                      # other keys: an indented block stays invisible to this flat reader
        elif v.startswith("[") and v.endswith("]") and "{" not in v:
            fm[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        elif v[0] in "[{":
            parsed = _yaml(f"{k}: {v}")
            fm[k] = parsed[k] if isinstance(parsed, dict) and k in parsed else v
        else:
            fm[k] = v
    return fm, body


def unquote(v):
    v = v.strip() if isinstance(v, str) else ""
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return re.sub(r'\\(["\\])', r"\1", v[1:-1])
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == "'" else v


def generated(fm):
    """`generated: {by, at}` as a dict ({} when absent or malformed)."""
    g = fm.get("generated")
    return g if isinstance(g, dict) else {}


def url_resource(fm):
    """The http(s) `url` of a Source-layer page: the resource it was digested from. It is not repeated in `sources`;
    '' for any other page or a url that is not http(s)."""
    url = unquote(str(fm.get("url") or ""))
    return url if fm.get("layer") == "source" and _HTTP.match(url) else ""


def resources(fm):
    """The `sources[].resource` strings of a page, in order (a legacy bare string entry counts as its own resource).
    A Source page without `sources` has its own `url` (the one resource `sources` would only repeat)."""
    srcs = fm.get("sources")
    if srcs in (None, ""):
        return [url_resource(fm)] if url_resource(fm) else []
    out = []
    for e in [srcs] if isinstance(srcs, (str, dict)) else srcs:
        r = e.get("resource") if isinstance(e, dict) else e
        if isinstance(r, str) and r.strip():
            out.append(r.strip())
    return out


def page_title(fm, text, slug=""):
    """The title of a page, the one rule everything shares: its `title:` when it has one (kept only when it differs
    from the first heading), else its first `# ` heading, else `slug`."""
    return unquote(fm.get("title")) or first_heading(text) or slug


def effective(fm, text):
    """`fm` with the fields the page leaves out because they are derived filled back in (`title` = first heading,
    `sources` = the Source page's own url), for what the app shows."""
    out = dict(fm)
    if not unquote(out.get("title")) and first_heading(text):
        out["title"] = quote(first_heading(text))      # as a written `title:` reads, so the panel looks as it did
    if out.get("sources") in (None, "") and url_resource(out):
        out["sources"] = [{"resource": url_resource(out)}]
    return out


def display(key, value):
    """A frontmatter value as the app shows it (a string, or a list of strings): `related` and `sources` by slug (a url
    stays a url), `generated` as `by @ at`, a midnight `created` as the date. Every other value is plain text."""
    from kb_distillery.vault import links
    if key == "related":
        return [links.page_slug(r) or str(r) for r in (value if isinstance(value, list) else [value])]
    if key == "sources":
        return [links.page_slug(r) or r for r in resources({"sources": value})]
    if key == "generated" and isinstance(value, dict):
        return f"{value.get('by', '')} @ {value['at']}" if value.get("at") else str(value.get("by", ""))
    if key == "created" and isinstance(value, str) and value.endswith("T00:00:00Z"):
        return value[:10]
    return value if isinstance(value, list) else str(value)


def quote(s):
    """A YAML double-quoted scalar for `s`."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


_H1 = re.compile(r"^# +(.+?)\s*#*\s*$", re.M)
_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)


def first_heading(text):
    """The page's first `# ` heading outside fenced code (frontmatter ignored), wikilinks reduced to their label;
    '' when it has none. This is what `title:` holds."""
    body = split_block(text)[1] if text.startswith("---") else text
    m = _H1.search(_FENCE.sub("", body))
    if not m:
        return ""
    from kb_distillery.vault import links
    return " ".join(links.plain(m.group(1)).split())


# -- writing the OKF shapes ----------------------------------------------------------------------------------------
_PLAIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./:+@%~-]*$")      # `?`, `=`, `&` … are legal in YAML but not in a flow collection
_HTTP = re.compile(r"^https?://\S+$")


def scalar(s):
    """`s` as a YAML scalar that also survives inside a flow collection: plain when safe, else double-quoted."""
    return s if _PLAIN.match(s) else quote(s)


def sources_line(resources):
    """`sources: [{resource: a.md}, {resource: https://…}]`"""
    return "sources: [" + ", ".join("{resource: " + scalar(r) + "}" for r in resources) + "]"


def related_line(paths):
    """`related: [a.md, b.md]` (page paths: vault.links.page_path)."""
    return "related: [" + ", ".join(scalar(p) for p in paths) + "]"


def fill_title(text):
    """Drop a template's `title: {{title_yaml}}` line: a page's title is its first heading, written only when it differs."""
    return re.sub(r"^title: \{\{title_yaml\}\}\n", "", text, flags=re.M).replace("{{title_yaml}}", "")


def title_line(title, heading=None):
    """`title: "…"` for a page whose H1 is `heading` (default: `title` itself); '' when it equals the first heading,
    which is what a reader falls back to."""
    title = " ".join(str(title).split())
    h = first_heading("# " + (title if heading is None else str(heading)))
    return "" if title == h else "title: " + quote(title)

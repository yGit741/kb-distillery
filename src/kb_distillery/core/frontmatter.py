"""The one frontmatter reader for wiki pages (OKF-shaped since schema 1.5).

Flat `key: value` and `key: [a, b]` lines stay plain strings and lists, as before. Three shapes OKF needs on top:
a flow mapping (`generated: {by: x, at: y}`), a list of mappings (`sources: [{resource: a.md}]`), and the same as a
block (`key:` then indented `- ...` lines). Those go through YAML's BaseLoader, so every scalar stays a string: a date
is never turned into a `date` object, `no` never into a bool.
"""
import re

_COMMENT = re.compile(r"\s#.*$")
_QUOTED = re.compile(r'^("(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\')')


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


def resources(fm):
    """The `sources[].resource` strings of a page, in order (a legacy bare string entry counts as its own resource)."""
    srcs = fm.get("sources")
    if srcs in (None, ""):
        return []
    out = []
    for e in [srcs] if isinstance(srcs, (str, dict)) else srcs:
        r = e.get("resource") if isinstance(e, dict) else e
        if isinstance(r, str) and r.strip():
            out.append(r.strip())
    return out


def display(key, value):
    """A frontmatter value as the app shows it (a string, or a list of strings): `related` and `sources` by slug (a url
    stays a url), `generated` as `by @ at`, a midnight `created` as the date. Every other value is plain text."""
    from kb_distillery.core import links
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
    from kb_distillery.core import links
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
    """`related: [a.md, b.md]` (page paths: core.links.page_path)."""
    return "related: [" + ", ".join(scalar(p) for p in paths) + "]"


def url_sources(url):
    """The `sources:` line of a Source-layer page: its own http(s) `url` is the resource it was digested from.
    '' when the page has no such url (a `raw:` path is never a resource)."""
    url = str(url or "").strip()
    return sources_line([url]) if _HTTP.match(url) else ""


def fill_title(text):
    """Fill a template's `{{title_yaml}}` with its own first heading, quoted: the page's `title:` is its H1."""
    if "{{title_yaml}}" not in text:
        return text
    return text.replace("{{title_yaml}}", quote(first_heading(text.replace("{{title_yaml}}", '""'))))


def title_line(title):
    return "title: " + quote(" ".join(str(title).split()))

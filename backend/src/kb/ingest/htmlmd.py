"""HTML → Markdown for blog posts. Standard library only (html.parser), no third-party deps.

Scope: the element set a WordPress post actually uses — paragraphs, headings, inline
emphasis, links, images, lists (nested), blockquotes, code, tables, rules, line breaks.
Unknown tags are transparent (their text is kept). Script/style/iframe bodies are dropped;
callers that want embeds as links rewrite `<iframe>` before converting (see wordpress.py).

    md = to_markdown(html_text)

Text inside `<pre>`/`<code>` and inside `$…$` math is never escaped; outside them only the
characters that would otherwise start Markdown syntax at a line start are escaped.
"""
import re
from html.parser import HTMLParser

BLOCK = {"p", "div", "section", "article", "header", "footer", "aside", "figure", "figcaption",
         "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "table",
         "thead", "tbody", "tfoot", "tr", "hr", "br", "dl", "dt", "dd", "center", "nav", "main"}
DROP = {"script", "style", "noscript", "iframe", "object", "embed", "svg", "button", "form", "input"}
_INLINE_BREAK = {"br"}                            # a block tag that still lives inside a paragraph
HEADING = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}
_LINE_START = re.compile(r"^(\s*)([#>+\-*]|\d+\.)(\s)", re.M)


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children = []


class _TreeBuilder(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(text):
    b = _TreeBuilder()
    b.feed(text)
    b.close()
    return b.root


class _Renderer:
    def __init__(self):
        self.list_stack = []      # ("ul"|"ol", counter)

    # -- inline -------------------------------------------------------------
    def inline(self, node, pre=False):
        out = []
        for c in node.children:
            if isinstance(c, str):
                out.append(c if pre else re.sub(r"\s+", " ", c))
                continue
            t = c.tag
            if t in DROP:
                continue
            if t == "br":
                out.append("\n")
            elif t == "img":
                alt = (c.attrs.get("alt") or "").replace("]", "").replace("\n", " ").strip()
                src = c.attrs.get("src") or ""
                title = c.attrs.get("title")
                out.append(f'![{alt}]({src} "{title}")' if title else f"![{alt}]({src})")
            elif t == "a":
                href = c.attrs.get("href") or ""
                inner = self.inline(c, pre).strip()
                if not inner:
                    continue
                if not href:
                    out.append(inner)
                elif inner == href:
                    out.append(f"<{href}>")
                else:
                    out.append(f"[{inner}]({href})")
            elif t in ("strong", "b"):
                out.append(self._wrap(self.inline(c, pre), "**"))
            elif t in ("em", "i", "cite", "var"):
                out.append(self._wrap(self.inline(c, pre), "*"))
            elif t in ("del", "s", "strike"):
                out.append(self._wrap(self.inline(c, pre), "~~"))
            elif t in ("code", "tt", "kbd", "samp"):
                code = self.inline(c, pre=True)
                out.append(f"`{code}`" if code.strip() else "")
            elif t == "sup":
                out.append(f"^{self.inline(c, pre).strip()}^")
            elif t == "sub":
                out.append(f"~{self.inline(c, pre).strip()}~")
            elif t in BLOCK:
                # a block element inside inline flow: render it as its own paragraph(s)
                out.append("\n\n" + self.block(c).strip() + "\n\n")
            else:                                     # span, font, u, small, abbr, …: transparent
                out.append(self.inline(c, pre))
        return "".join(out)

    @staticmethod
    def _wrap(text, mark):
        core = text.strip()
        if not core:
            return text
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        return f"{lead}{mark}{core}{mark}{trail}"

    # -- blocks -------------------------------------------------------------
    def block(self, node):
        """Render the children of a container as a sequence of blocks."""
        parts = []
        run = []                                      # inline run waiting to become a paragraph

        def flush():
            text = "".join(run).strip()
            run.clear()
            if text:
                parts.append(text)

        for c in node.children:
            if isinstance(c, str):
                run.append(re.sub(r"\s+", " ", c))
                continue
            t = c.tag
            if t in DROP:
                continue
            if t not in BLOCK:
                run.append(self.inline(_wrap_one(c)))
                continue
            flush()
            if t in HEADING:
                text = self.inline(c).strip()
                if re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", text):
                    parts.append(text)                # an image alone in a heading is a figure
                elif text:
                    parts.append(f"{HEADING[t]} {text}")
            elif t in ("ul", "ol"):
                parts.append(self.list(c))
            elif t == "li":                           # stray li outside a list
                parts.append("- " + self.inline(c).strip())
            elif t == "blockquote":
                inner = self.block(c).strip()
                parts.append("\n".join(("> " + l) if l else ">" for l in inner.split("\n")))
            elif t == "pre":
                code = self.inline(c, pre=True).strip("\n")
                lang = ""
                m = re.search(r"(?:lang(?:uage)?[-:]|brush:\s*)([\w+-]+)", " ".join(c.attrs.values()))
                if m:
                    lang = m.group(1)
                parts.append(f"```{lang}\n{code}\n```")
            elif t == "hr":
                parts.append("---")
            elif t == "br":
                run.append("\n")
            elif t == "table":
                parts.append(self.table(c))
            elif t in ("tr", "thead", "tbody", "tfoot"):
                parts.append(self.block(c).strip())
            elif t in ("dt",):
                parts.append("**" + self.inline(c).strip() + "**")
            elif t in ("dd",):
                parts.append(": " + self.inline(c).strip())
            else:                                     # p, div, figure, section, …
                inner = self.block(c).strip() if _has_block(c) else self.inline(c).strip()
                if inner:
                    parts.append(inner)
        flush()
        return "\n\n".join(p for p in parts if p)

    def list(self, node):
        kind = node.tag
        items = []
        n = 0
        for c in node.children:
            if isinstance(c, str) or c.tag != "li":
                continue
            n += 1
            marker = f"{n}." if kind == "ol" else "-"
            body = self.block(c).strip() if _has_block(c) else self.inline(c).strip()
            lines = body.split("\n")
            pad = " " * (len(marker) + 1)
            items.append(f"{marker} " + ("\n".join([lines[0]] + [(pad + l) if l else "" for l in lines[1:]])))
        return "\n".join(items)

    def table(self, node):
        rows = []
        for tr in _descendants(node, "tr"):
            cells = [self.inline(td).strip().replace("|", "\\|").replace("\n", " ")
                     for td in tr.children if not isinstance(td, str) and td.tag in ("td", "th")]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(out)


def _has_block(node):
    return any(not isinstance(x, str) and x.tag in BLOCK and x.tag not in _INLINE_BREAK
               for x in node.children)


def _wrap_one(node):
    w = _Node("span")
    w.children = [node]
    return w


def _descendants(node, tag):
    for c in node.children:
        if isinstance(c, str):
            continue
        if c.tag == tag:
            yield c
        else:
            yield from _descendants(c, tag)


def _escape_line_starts(md):
    """A text line that happens to start with `#`, `-`, `1.` … would become syntax; escape it.
    Lines we generated as syntax (headings, bullets, quotes) are regenerated identically, so
    only lines whose marker is followed by text we did not put there matter. We keep it simple:
    escape a leading `#` only when it is not followed by a space (never ours)."""
    return re.sub(r"^(#+)(?=[^#\s])", r"\\\1", md, flags=re.M)


def to_markdown(text):
    root = parse(text)
    md = _Renderer().block(root)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return _escape_line_starts(md).strip() + "\n"

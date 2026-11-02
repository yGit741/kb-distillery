"""Render a raw blog post (.md clip) as one `type: blog-post` wiki page. Zero LLM.

The page carries an English title over the original-language one, a link to the
original post, the Blog Post Summary and Key concepts (written at digest time; empty
in a fresh stub), and the full post body — so the post is readable inside the vault.
Hebrew posts render right-to-left. The wiki slug is the raw file's stem.
"""
import json
import os
import re

from kb_distillery.core import frontmatter, links
from .paths import ROOT

BLOGS = {
    # tag on the raw .md → (display name, home URL, language)
    "source/blog-not-exact": ("לא מדויק", "https://gadial.net", "he"),
}
RTL = {"he", "ar", "fa"}
_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def blog_of(fm_text):
    """The BLOGS entry whose tag appears in the raw post's frontmatter, or None."""
    for tag, info in BLOGS.items():
        if re.search(rf"(^|[\s,\[]){re.escape(tag)}([\s,\]]|$)", fm_text, re.M):
            return tag, info
    return None


def split(text):
    """(frontmatter text, title, body) of a raw post."""
    m = _FM_RE.match(text)
    fm = m.group(1) if m else ""
    body = text[m.end():] if m else text
    title = re.search(r'^title:\s*"?(.*?)"?\s*$', fm, re.M)
    return fm, (title.group(1) if title else ""), body.strip("\n")


_XY_BLOCK = re.compile(r"(?:\\begin\{aligned\}\s*)?\\xymatrix\{(.*?)(?:\\end\{aligned\}|(?=\$\$))", re.S)
_ARROW_SYM = {"u": r"\Big\uparrow", "d": r"\Big\downarrow", "r": r"\longrightarrow", "l": r"\longleftarrow",
              "ur": r"\nearrow", "dr": r"\searrow", "ul": r"\nwarrow", "dl": r"\swarrow"}


def _xy_body(raw):
    """Drop the closing brace(s) of \\xymatrix{…} — and any unbalanced `}` a hand-typed
    diagram carries — so rows and cells can be split cleanly."""
    out, depth = [], 0
    for ch in raw:
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
        out.append(ch)
    return "".join(out).strip()


def _xy_arrows(cell):
    """(object text, [(direction, label), …]) for one cell. Labels are `^x`, `_x`, `^{…}`
    with nested braces allowed — a regex can't balance those, so scan."""
    obj, arrows, i = [], [], 0
    while i < len(cell):
        m = re.compile(r"\\ar\[([udlr]+)\]").match(cell, i)
        if not m:
            obj.append(cell[i])
            i += 1
            continue
        i, labels = m.end(), []
        while i < len(cell) and cell[i] in "^_":
            i += 1
            if i < len(cell) and cell[i] == "{":
                depth, start = 0, i
                while i < len(cell):
                    depth += {"{": 1, "}": -1}.get(cell[i], 0)
                    i += 1
                    if depth == 0:
                        break
                labels.append(cell[start + 1:i - 1])
            else:
                tok = re.compile(r"\\[A-Za-z]+|.").match(cell, i)
                labels.append(tok.group(0))
                i = tok.end()
        arrows.append((m.group(1), " ".join(labels)))
    return "".join(obj).strip(), arrows


def xymatrix_to_array(body):
    """xy-pic `\\xymatrix` (KaTeX and MathJax can't draw it) → an `array` on a doubled grid:
    objects on even cells, each arrow's symbol and label at the midpoint of its run."""
    rows = [r.split("&") for r in re.split(r"\\\\", _xy_body(body))]
    width = max(len(r) for r in rows)
    grid = [["" for _ in range(2 * width - 1)] for _ in range(2 * len(rows) - 1)]
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            obj, arrows = _xy_arrows(cell)
            for d, label in arrows:
                di = d.count("d") - d.count("u")
                dj = d.count("r") - d.count("l")
                key = ("u" if di < 0 else "d" if di > 0 else "") + ("r" if dj > 0 else "l" if dj < 0 else "")
                sym = _ARROW_SYM[key]
                if key in ("u", "d"):
                    sym += rf"{{\scriptstyle {label}}}" if label else ""
                elif key in ("r", "l"):
                    sym = (r"\xrightarrow" if key == "r" else r"\xleftarrow") + f"{{{label}}}"
                elif label:
                    sym += f"^{{{label}}}"
                grid[2 * i + di][2 * j + dj] = sym
            grid[2 * i][2 * j] = obj
    cols = "c" * len(grid[0])
    return (rf"\begin{{array}}{{{cols}}}" + " \\\\ ".join(" & ".join(r) for r in grid)
            + r"\end{array}")


_INLINE_MATH = re.compile(r"(?<!\$)\$([^$\n]{2,400}?)\$(?!\$)")


def _brace_balance(tex):
    """(lowest prefix balance, final balance) of `{`/`}` in a formula; escaped braces are ignored."""
    bal = low = 0
    for ch in re.sub(r"\\[{}]", "  ", tex):
        bal += (ch == "{") - (ch == "}")
        low = min(low, bal)
    return low, bal


def fix_braces(body):
    r"""Repair inline formulas an old scraper cut: it dropped the outer `{` `}` of a formula that
    started with `{` and ended with `}` (`${\cal D}_x U^{-1}$` became `$\cal D}_x U^{-1$`; fixed at
    the source in wordpress._math_md). Prefix-balance rule: a prefix that closes more than it opened
    needs that many `{` in front, and what is left open at the end needs as many `}` after. Anything
    else is left alone -- see unbalanced_formulas()."""
    def fix(m):
        low, bal = _brace_balance(m.group(1))
        need, trail = -low, bal - low
        if need == 0 or trail < 0:
            return m.group(0)
        return "$" + "{" * need + m.group(1) + "}" * trail + "$"
    return _INLINE_MATH.sub(fix, body)


def unbalanced_formulas(body):
    """Inline formulas whose braces still do not balance: (formula, context) pairs."""
    out = []
    for m in _INLINE_MATH.finditer(body):
        low, bal = _brace_balance(m.group(1))
        if low or bal:
            out.append((m.group(0), body[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")))
    return out


def fix_math(body):
    """Rewrite TeX the in-vault renderers can't draw. Raw files stay untouched."""
    return fix_braces(_XY_BLOCK.sub(lambda m: xymatrix_to_array(m.group(1)), body))


def render(raw_rel, title_en=None, url=None, summary="", key_concepts=(), root=ROOT):
    with open(os.path.join(root, raw_rel), encoding="utf-8") as f:
        fm, title_orig, body = split(f.read())
    body = fix_math(body)
    found = blog_of(fm)
    name, home, lang = found[1] if found else ("blog", "", "en")
    title = title_en or title_orig or os.path.basename(raw_rel)[:-3]
    q = lambda s: json.dumps(s, ensure_ascii=False)
    rtl = lang in RTL
    link = url or home
    head = ["---", "type: blog-post", "layer: source", f"title: {q(title)}", "maturity: to-read", "status: draft",
            "depth: listed"]
    if title_orig and title_orig != title:
        head.append(f"aliases: [{q(title_orig)}]")
    head += [f"blog: {q(name)}", f"lang: {lang}"]
    if url:
        head.append(f"url: {url}")
        if frontmatter.url_sources(url):
            head.append(frontmatter.url_sources(url))
    head.append(f"raw: {raw_rel}")
    related = [f"source-{x}" for x in re.findall(r"subject/([a-z0-9-]+)", fm)
               if os.path.isfile(os.path.join(root, "wiki", f"source-{x}.md"))]
    if related:
        head.append(frontmatter.related_line([links.page_path(x) for x in related]))
    head += ["---", "", f"# {title}", ""]
    if title_orig and title_orig != title:
        head += [f'<div dir="rtl"><strong>{title_orig}</strong></div>' if rtl
                 else f"*{title_orig}*", ""]
    origin = f'<span dir="rtl">[{title_orig}]({link})</span>' if rtl and title_orig else f"[{title}]({link})"
    head += [f"> [!abstract] Blog post · [{name}]({home}) · {'Hebrew' if lang == 'he' else lang}",
             f"> Read the original: {origin}", ""]
    concepts = "\n".join(f"- {k}" for k in key_concepts)
    sections = ["## Blog Post Summary", "", summary, "", "## Key concepts", "", concepts, "", "## Post", ""]
    post = [f'<div dir="rtl">', "", body, "", "</div>"] if rtl else [body]
    text = "\n".join(head + sections + post) + "\n"
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def wiki_slug(raw_rel):
    return os.path.basename(raw_rel)[:-3]

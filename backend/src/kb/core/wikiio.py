"""One way to write wiki pages without losing knowledge. Stdlib only.

* `split_page(text)` → (front matter incl. both `---` fences, body). The body is every byte after
  the closing fence; a page without front matter is all body.
* `write_front_matter(path, fm)` replaces only the front matter, atomically, and raises
  `BodyChanged` if the body bytes would differ afterwards (an `fm` that is not one fenced block).
* `edit_front_matter(text, fn)` / `set_key(text, key, value)`: the same, on a string.
* `preserve_my_notes(old, new)`: the reserved `## My notes` section is the user's — whatever a
  generator renders, the old page's section survives verbatim and stays last.
* `write_page(path, new_text)`: atomic write of a whole page that keeps `## My notes` of the page
  already on disk. Every writer that regenerates or patches an existing page goes through it.
"""
import os
import re
import tempfile

MY_NOTES = "## My notes"
_MY_NOTES_RE = re.compile(r"^## My notes[ \t]*$", re.M)
_KEY_RE = r"^{key}:[^\n]*$"


class BodyChanged(RuntimeError):
    """A front-matter write would have changed the page body."""


def split_page(text):
    """(front matter incl. fences, body). Same split as backend/src/kb/ops/invariants.split_page."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 3)
    if end != -1:
        return text[:end + 5], text[end + 5:]
    if text.endswith("\n---"):
        return text, ""
    return "", text


def _check_fm(fm):
    if not (fm.startswith("---\n") and fm.endswith("\n---\n")) or "\n---\n" in fm[3:-4]:
        raise BodyChanged("front matter must be one block fenced by `---` lines")


def edit_front_matter(text, fn):
    """`fn(front matter without fences) -> new front matter`; the body is kept byte for byte."""
    fm, body = split_page(text)
    if not fm:
        raise BodyChanged("page has no front matter")
    inner = fm[4:-5] if fm.endswith("\n---\n") else fm[4:-4]
    new_fm = "---\n" + fn(inner).strip("\n") + "\n---\n"
    _check_fm(new_fm)
    out = new_fm + body
    if split_page(out)[1] != body:
        raise BodyChanged("front matter edit would change the body")
    return out


def set_key(text, key, value, after=None):
    """Set one flat `key: value` in the front matter (replace, else insert after `after`'s line,
    else append). Only the front matter is touched."""
    line = f"{key}: {value}"

    def fn(inner):
        pat = re.compile(_KEY_RE.format(key=re.escape(key)), re.M)
        if pat.search(inner):
            return pat.sub(lambda _m: line, inner, count=1)
        if after:
            anchor = re.compile(_KEY_RE.format(key=re.escape(after)), re.M).search(inner)
            if anchor:
                return inner[:anchor.end()] + "\n" + line + inner[anchor.end():]
        return inner.rstrip("\n") + "\n" + line
    return edit_front_matter(text, fn)


def _atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".wikiio-", suffix=".md", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def write_front_matter(path, fm):
    """Replace the front matter of `path` with `fm` (a fenced block, or its inner lines as a
    string/list). Atomic; raises BodyChanged instead of writing if the body would change."""
    with open(path, encoding="utf-8", newline="") as f:
        old = f.read()
    if isinstance(fm, (list, tuple)):
        fm = "\n".join(fm)
    if not fm.startswith("---\n"):
        fm = "---\n" + fm.strip("\n") + "\n---\n"
    _check_fm(fm)
    _old_fm, body = split_page(old)
    new = fm + body
    if split_page(new)[1] != body:
        raise BodyChanged(f"{path}: front matter write would change the body")
    if new != old:
        _atomic_write(path, new)
    return new != old


def _notes_span(body):
    """(start, end) of the `## My notes` section in a body: its heading up to the next `## `
    heading or the end of the page; None when there is none. The last one wins."""
    hits = list(_MY_NOTES_RE.finditer(body))
    if not hits:
        return None
    start = hits[-1].start()
    nxt = re.compile(r"^## ", re.M).search(body, hits[-1].end())
    return start, (nxt.start() if nxt else len(body))


def my_notes(text):
    """The `## My notes` section (heading through its last line), or ''."""
    body = split_page(text)[1]
    span = _notes_span(body)
    return body[span[0]:span[1]].rstrip("\n") + "\n" if span else ""


def strip_my_notes(text):
    """The page without its `## My notes` section (everything else byte for byte)."""
    fm, body = split_page(text)
    span = _notes_span(body)
    if not span:
        return text
    return fm + body[:span[0]] + body[span[1]:]


def preserve_my_notes(old, new):
    """`new` with the old page's `## My notes` section restored, verbatim and last. When the old
    page has none, `new` is returned unchanged."""
    notes = my_notes(old or "")
    if not notes:
        return new
    base = strip_my_notes(new).rstrip("\n")
    return (base + "\n\n" if base else "") + notes


def edit_body(text, fn):
    """Apply `fn` to the page without its `## My notes`, then put the notes back last."""
    return preserve_my_notes(text, fn(strip_my_notes(text)))


def write_page(path, new_text):
    """Write a whole page atomically, keeping the `## My notes` of the page already there."""
    old = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:
            old = f.read()
        new_text = preserve_my_notes(old, new_text)
    if new_text != old:
        _atomic_write(path, new_text)
    return new_text


def check_my_notes(text):
    """Lint messages for the reserved section: at most one, and it must be the last `## ` heading."""
    body = split_page(text)[1]
    hits = [m.start() for m in _MY_NOTES_RE.finditer(body)]
    out = []
    if len(hits) > 1:
        out.append(f"{len(hits)} `{MY_NOTES}` sections — keep one")
    if hits and re.search(r"^## ", body[hits[-1] + len(MY_NOTES):], re.M):
        out.append(f"`{MY_NOTES}` must be the last section (tools keep it last; move it to the end)")
    return out

"""Doc → aligned plain text (the multipart fallback, the launchd log and the CLI)."""
import textwrap

WIDTH = 78
GLYPH = {"ok": "✓", "warn": "!", "error": "✗", "info": "i", "": "·"}


def _wrap(text, indent, width=WIDTH):
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent,
                         break_long_words=True, break_on_hyphens=False) if text else ""


def _banner(b):
    lines = [f"{GLYPH.get(b.status, '')} {b.title}"]
    if b.subtitle:
        lines.append(_wrap(b.subtitle, "  "))
    return lines


def _stats(s):
    width = max((len(st.label) for st in s.items), default=0)
    return [f"  {st.label.ljust(width)}  {st.value}" + (f"  ({st.hint})" if st.hint else "") for st in s.items]


def _table(t):
    rows = [list(map(str, t.columns))] + [list(map(str, r)) for r in t.rows] if t.columns else [list(map(str, r)) for r in t.rows]
    if not rows:
        return []
    widths = [min(max(len(r[i]) for r in rows if i < len(r)), 40) for i in range(max(map(len, rows)))]
    out = [t.caption] if t.caption else []
    for n, r in enumerate(rows):
        cells = [(c if len(c) <= widths[i] or i == len(r) - 1 else c[: widths[i] - 1] + "…").ljust(widths[i])
                 for i, c in enumerate(r)]
        out.append("  " + "  ".join(cells).rstrip())
        if n == 0 and t.columns:
            out.append("  " + "  ".join("-" * w for w in widths))
    return out


def _cards(cs):
    if not cs.items:
        return [f"  {cs.empty}"]
    out = []
    for c in cs.items:
        out.append(f"  {GLYPH.get(c.status, '')} {c.title}" + (f"  [{c.state}]" if c.state else ""))
        if c.facts:
            out.append(_wrap(" · ".join(f"{k} {v}" for k, v in c.facts), "      "))
        out.extend(_wrap(f"• {n}", "      ") for n in c.notes)
        if c.fix:
            cmd, _, comment = c.fix.partition("   # ")
            out.append(f"      → {cmd.strip()}" + (f"\n        ({comment.strip()})" if comment else ""))
    return out


def _findings(fs):
    if not fs.items:
        return [f"  {fs.empty}"]
    out = []
    for f in fs.items:
        out.append(_wrap(f"{GLYPH.get(f.status, '')} {f.label}: {f.detail}", "  "))
        if f.fix:
            out.append(f"      → {f.fix}")
    return out


def _text(t):
    return [_wrap(t.text, "  ")]


def _code(c):
    return ([f"  {c.label}"] if c.label else []) + ["    " + line for line in c.text.splitlines()]


RENDER = {"banner": _banner, "stats": _stats, "table": _table, "cards": _cards, "findings": _findings,
          "text": _text, "code": _code}


def render(doc):
    head = doc.title.upper()
    lines = [f"{head}{doc.generated.rjust(WIDTH - len(head))}" if doc.generated else head, "=" * WIDTH]
    for s in doc.sections:
        if s.title:
            lines += ["", s.title.upper() + (f"  · {s.note}" if s.note else ""), "-" * min(WIDTH, len(s.title) + 2)]
        for b in s.blocks:
            lines += RENDER[b.kind](b)
    lines += ["", "-" * WIDTH] + list(doc.footer) + [f"{label}: {url}" for label, url in doc.links]
    return "\n".join(lines).rstrip() + "\n"

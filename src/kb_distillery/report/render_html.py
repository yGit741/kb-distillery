"""Doc → email-safe HTML: table layout, inline styles only, one 600 px column.

Mail clients drop <style> blocks and modern CSS, so every element carries its own style.
Colours are mid-tones that stay readable when Gmail / Apple Mail apply their dark mode.
`render(doc)` is a full document; `render_body(doc)` is the inner column (for previews).
"""
import html

from . import model

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
INK, MUTED, LINE, PAGE, PANEL, SOFT = "#18181b", "#6b7280", "#e4e4e7", "#f4f4f5", "#ffffff", "#f8fafc"
COLOR = {"ok": "#15803d", "warn": "#b45309", "error": "#b91c1c", "info": "#1d4ed8", "": "#52525b"}
TINT = {"ok": "#f0fdf4", "warn": "#fffbeb", "error": "#fef2f2", "info": "#eff6ff", "": "#f4f4f5"}
GLYPH = {"ok": "✓", "warn": "!", "error": "✗", "info": "i", "": "·"}


def e(text):
    return html.escape(str(text if text is not None else ""), quote=True)


def chip(text, status=""):
    if not text:
        return ""
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;'
            f'font-weight:600;letter-spacing:.02em;color:{COLOR.get(status, COLOR[""])};'
            f'background:{TINT.get(status, TINT[""])};border:1px solid {COLOR.get(status, COLOR[""])}33">{e(text)}</span>')


def split_command(text):
    """"cmd   # or: other" → ("cmd", "or: other") — the comment is shown as a muted hint."""
    cmd, _, comment = (text or "").partition("   # ")
    return cmd.strip(), comment.strip()


def command(text):
    if not text:
        return ""
    cmd, comment = split_command(text)
    hint = f'<div style="margin-top:3px;font-size:11px;color:{MUTED}">{e(comment)}</div>' if comment else ""
    return (f'<div style="margin-top:8px;font-family:{MONO};font-size:12px;line-height:1.45;color:{INK};'
            f'background:{PAGE};border:1px solid {LINE};border-radius:6px;padding:6px 9px;'
            f'word-break:break-all;white-space:pre-wrap">$ {e(cmd)}</div>{hint}')


def _banner(b):
    c = COLOR.get(b.status, COLOR[""])
    sub = f'<div style="margin-top:4px;font-size:13px;color:{MUTED}">{e(b.subtitle)}</div>' if b.subtitle else ""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;'
            f'background:{TINT.get(b.status, TINT[""])};border:1px solid {c}40;border-left:5px solid {c};border-radius:10px">'
            f'<tr><td style="padding:14px 16px">'
            f'<div style="font-size:20px;font-weight:700;color:{c}">{e(GLYPH.get(b.status, ""))} {e(b.title)}</div>'
            f'{sub}</td></tr></table>')


def _stats(s):
    cells = []
    for st in s.items:
        c = COLOR.get(st.status, INK) if st.status else INK
        hint = f'<div style="font-size:11px;color:{MUTED};margin-top:2px">{e(st.hint)}</div>' if st.hint else ""
        cells.append(f'<td valign="top" style="padding:10px 12px;border:1px solid {LINE};border-radius:8px;background:{PANEL}">'
                     f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:{MUTED}">{e(st.label)}</div>'
                     f'<div style="font-size:20px;font-weight:700;color:{c};margin-top:2px">{e(st.value)}</div>{hint}</td>')
    rows, per = [], len(cells) if len(cells) <= 4 else 3
    for i in range(0, len(cells), per):
        chunk = cells[i:i + per] + ['<td></td>'] * (per - len(cells[i:i + per]))
        rows.append("<tr>" + "".join(chunk) + "</tr>")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="6" '
            f'style="border-collapse:separate;table-layout:fixed;margin:0 -6px">{"".join(rows)}</table>')


def _table(t):
    head = "".join(f'<th align="left" style="padding:6px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;'
                   f'color:{MUTED};border-bottom:1px solid {LINE}">{e(c)}</th>' for c in t.columns)
    body = "".join("<tr>" + "".join(f'<td valign="top" style="padding:6px 8px;font-size:13px;color:{INK};'
                                     f'border-bottom:1px solid {LINE}{";white-space:nowrap" if i < len(row) - 1 else ""}">'
                                     f'{e(v)}</td>' for i, v in enumerate(row)) + "</tr>"
                   for row in t.rows)
    cap = f'<div style="font-size:12px;color:{MUTED};margin-bottom:4px">{e(t.caption)}</div>' if t.caption else ""
    return (f'{cap}<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse">{"<tr>" + head + "</tr>" if t.columns else ""}{body}</table>')


def _card(c):
    color = COLOR.get(c.status, COLOR[""])
    title = e(c.title)
    if c.link:
        title = f'<a href="{e(c.link)}" style="color:{INK};text-decoration:none">{title}</a>'
    facts = " · ".join(f'<span style="color:{MUTED}">{e(k)}</span> {e(v)}' for k, v in c.facts)
    facts = f'<div style="margin-top:4px;font-size:12px;color:{INK}">{facts}</div>' if facts else ""
    notes = "".join(f'<div style="margin-top:4px;font-size:12px;color:{color}">• {e(n)}</div>' for n in c.notes)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;'
            f'margin:0 0 8px;background:{PANEL};border:1px solid {LINE};border-left:4px solid {color};border-radius:8px">'
            f'<tr><td style="padding:10px 12px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:14px;font-weight:600;color:{INK}">{title}</td>'
            f'<td align="right" style="white-space:nowrap">{chip(c.state, c.status)}</td></tr></table>'
            f'{facts}{notes}{command(c.fix)}</td></tr></table>')


def _cards(cs):
    if not cs.items:
        return _text(model.Text(cs.empty, muted=True))
    return "".join(_card(c) for c in cs.items)


def _findings(fs):
    if not fs.items:
        return _text(model.Text(fs.empty, muted=True))
    out = []
    for f in fs.items:
        c = COLOR.get(f.status, COLOR[""])
        out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 8px;'
                   f'border-collapse:separate;background:{PANEL};border:1px solid {LINE};border-radius:8px"><tr>'
                   f'<td width="28" valign="top" style="padding:10px 0 10px 12px;font-size:15px;font-weight:700;color:{c}">'
                   f'{e(GLYPH.get(f.status, ""))}</td><td style="padding:10px 12px 10px 4px">'
                   f'<div style="font-size:13px;color:{INK}"><b style="color:{c}">{e(f.label)}</b> — {e(f.detail)}</div>'
                   f'{command(f.fix)}</td></tr></table>')
    return "".join(out)


def _text(t):
    return f'<p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:{MUTED if t.muted else INK}">{e(t.text)}</p>'


def _code(c):
    label = f'<div style="font-size:11px;color:{MUTED};margin-bottom:4px">{e(c.label)}</div>' if c.label else ""
    return (f'{label}<pre style="margin:0;font-family:{MONO};font-size:11px;line-height:1.45;color:{INK};'
            f'background:{SOFT};border:1px solid {LINE};border-radius:6px;padding:8px 10px;'
            f'white-space:pre-wrap;word-break:break-all">{e(c.text)}</pre>')


RENDER = {"banner": _banner, "stats": _stats, "table": _table, "cards": _cards, "findings": _findings,
          "text": _text, "code": _code}


def block(b):
    return RENDER[b.kind](b)


def _section(s):
    note = f'<span style="font-weight:400;color:{MUTED};text-transform:none;letter-spacing:0"> · {e(s.note)}</span>' if s.note else ""
    title = (f'<div style="margin:22px 0 8px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;'
             f'color:{MUTED}">{e(s.title)}{note}</div>') if s.title else '<div style="height:14px"></div>'
    return title + "".join(block(b) for b in s.blocks)


def render_body(doc):
    footer = " · ".join(e(line) for line in doc.footer)
    links = " · ".join(f'<a href="{e(u)}" style="color:{COLOR["info"]}">{e(label)}</a>' for label, u in doc.links)
    return (f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;'
            f'background:{PANEL};border:1px solid {LINE};border-radius:14px">'
            f'<tr><td style="padding:20px 22px 8px">'
            f'<div style="font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{MUTED}">'
            f'{e(doc.title)}<span style="float:right;font-weight:400;letter-spacing:0;text-transform:none">{e(doc.generated)}</span></div>'
            f'</td></tr><tr><td style="padding:4px 22px 20px">{"".join(_section(s) for s in doc.sections)}</td></tr>'
            f'<tr><td style="padding:12px 22px 18px;border-top:1px solid {LINE};font-size:11px;line-height:1.6;color:{MUTED}">'
            f'{links}{"<br>" if links and footer else ""}{footer}</td></tr></table>')


def render(doc):
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta name=\"color-scheme\" content=\"light only\"><meta name=\"supported-color-schemes\" content=\"light\">"
            f"<title>{e(doc.headline)}</title></head>"
            f'<body style="margin:0;padding:0;background:{PAGE};font-family:{FONT};-webkit-text-size-adjust:100%">'
            f'<div style="display:none;max-height:0;overflow:hidden">{e(doc.headline)}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE}">'
            f'<tr><td align="center" style="padding:20px 10px">{render_body(doc)}</td></tr></table></body></html>')

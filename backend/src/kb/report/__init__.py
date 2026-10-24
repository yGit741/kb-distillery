"""Generic report building blocks: a `Doc` of sections and blocks, rendered to email-safe HTML,
aligned plain text or JSON (for the dashboard). Nothing here knows about hygiene or git —
the nightly report (`backend/src/kb/ops/nightly_report.py`) is one user; any future log report is another.

    from report import model as m, render_html, render_text
    doc = m.Doc("Nightly report", "ok", "All clear", sections=[m.Section("Threads", [m.Cards([...])])])
    render_html.render(doc), render_text.render(doc), doc.as_dict()
"""

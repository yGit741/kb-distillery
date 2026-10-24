"""Books become a hub page plus parts (schema 0.8).

A >=60-page PDF gets one `type: book` hub (slug = PDF basename) with an Overview and a
Partition table; each digested chapter range is a `type: part` page. The one book
digested under the old rules (O'Donnell, Analysis of Boolean Functions) moves from
`source-analysis-of-boolean-functions` to the hub `2014-analysis-of-boolean-functions`.

Idempotent: rewrites any remaining links to the old source page and removes it once
the hub exists. The hub/part pages themselves ship in the same PR.
"""
import os
import re

PRODUCES = (0, 8)
RENAMES = {"source-analysis-of-boolean-functions": "2014-analysis-of-boolean-functions"}


def apply(root):
    wiki = os.path.join(root, "wiki")
    for old, new in RENAMES.items():
        pattern = re.compile(r"\[\[" + re.escape(old) + r"(\|[^\]]*)?\]\]")
        for name in os.listdir(wiki):
            if not name.endswith(".md"):
                continue
            path = os.path.join(wiki, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            updated = pattern.sub(lambda m: f"[[{new}{m.group(1) or ''}]]", text)
            if updated != text:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(updated)
        old_page, new_page = (os.path.join(wiki, f"{s}.md") for s in (old, new))
        if os.path.exists(old_page) and os.path.exists(new_page):
            os.remove(old_page)

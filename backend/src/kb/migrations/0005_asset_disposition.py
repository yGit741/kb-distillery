"""Figures downloaded with a web clip become `asset:<clip>` corpus rows (schema 0.11).

`raw/images/<clip stem>-NN.<ext>` whose `raw/web-clips/<clip stem>.md` exists is part of that
clip, like an ink overlay is part of its PDF: lint binds it as `asset:raw/web-clips/<clip>.md`,
it never counts as backlog and never joins a hub on its own. `scrap-wordpress` writes clips and
figures in exactly this shape.

Nothing in the vault used the name pattern before this schema, so apply() only re-derives the
disposition for any such row that is still `queued` (idempotent: lint does the same on every run).
"""
import os
import re

PRODUCES = (0, 11)
ASSET_NAME = re.compile(r"^(?P<clip>.+)-\d{2,3}\.(png|jpe?g|gif|webp)$", re.I)
MANIFEST = os.path.join("meta", "corpus.tsv")


def apply(root):
    path = os.path.join(root, MANIFEST)
    if not os.path.isfile(path):
        return
    lines = open(path, encoding="utf-8").read().split("\n")
    changed = 0
    for i, line in enumerate(lines):
        parts = line.split("\t")
        if len(parts) < 4 or not parts[0].startswith("raw/images/") or parts[3] != "queued":
            continue
        m = ASSET_NAME.match(os.path.basename(parts[0]))
        if not m:
            continue
        clip = f"raw/web-clips/{m.group('clip')}.md"
        if os.path.isfile(os.path.join(root, clip)):
            parts[3] = f"asset:{clip}"
            lines[i] = "\t".join(parts)
            changed += 1
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

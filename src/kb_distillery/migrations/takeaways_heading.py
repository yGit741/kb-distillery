"""Rename a kb's takeaways section heading to the one its kit names (kb_distillery.config.pages).

Before kits named it, every page skeleton wrote `## Takeaways for my thesis`. A kb on the `research` kit keeps that
heading (nothing to do); any other kb now reads `## Takeaways`, so its older pages are renamed here. Only that exact
heading line in wiki/*.md changes; think/ is the owner's and is never touched. Idempotent.

Not a numbered schema migration (`ops migrate` never runs it): the owner runs it once per kb that needs it.

    distill kb takeaways [--kb <id|path>]           dry run: list the pages that would change
    distill kb takeaways --apply                    rewrite them
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import pages as page_conventions

LEGACY = "Takeaways for my thesis"


def plan(root: str, heading: str) -> list[str]:
    """The wiki pages (relative paths) that carry the legacy heading, when it differs from `heading`."""
    if heading == LEGACY:
        return []
    wiki = os.path.join(root, "wiki")
    pattern = re.compile(rf"^## {re.escape(LEGACY)}[ \t]*\r?$", re.M)
    out = []
    for dirpath, dirs, files in os.walk(wiki):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if fn.endswith(".md"):
                path = os.path.join(dirpath, fn)
                with open(path, encoding="utf-8", newline="") as f:
                    if pattern.search(f.read()):
                        out.append(os.path.relpath(path, root))
    return out


def apply(root: str, heading: str) -> list[str]:
    """Rewrite the legacy heading line to `## <heading>` in every planned page; returns them."""
    pattern = re.compile(rf"^## {re.escape(LEGACY)}([ \t]*\r?)$", re.M)
    changed = plan(root, heading)
    for rel in changed:
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(pattern.sub(lambda m: f"## {heading}{m.group(1)}", text))
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="distill kb takeaways", description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="rewrite the pages (default: dry run, writes nothing)")
    args = ap.parse_args(argv)
    cfg = kbconfig.current()
    if cfg is None:
        print("error: no knowledge base selected (pass --kb <id|path> or set KB)", file=sys.stderr)
        return 2
    heading = page_conventions.takeaways_heading(cfg)
    pages = (apply if args.apply else plan)(cfg.root, heading)
    verb = "renamed" if args.apply else "would rename"
    print(f"{cfg.id}: takeaways heading is {heading!r}; {verb} {len(pages)} page(s) from {LEGACY!r}")
    for rel in pages:
        print(f"  {rel}")
    if pages and not args.apply:
        print("dry run: nothing written (pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

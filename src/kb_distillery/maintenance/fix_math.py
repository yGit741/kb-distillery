#!/usr/bin/env python3
"""One-shot math-delimiter fix: \\(..\\)/\\[..\\] -> $../$$..$$ across wiki/.

Dry-run by default (prints a unified diff per page); pass --apply to write.
"""
import argparse
import difflib
import glob
import os
import sys

from kb_distillery.core.mathnorm import normalize_math, has_legacy_math

from kb_distillery.paths import vault_root
ROOT = vault_root()
WIKI = os.path.join(ROOT, "wiki")


def affected_pages(paths=None):
    if paths:
        return [p for p in paths if os.path.isfile(os.path.join(ROOT, p))]
    out = []
    for f in sorted(glob.glob(os.path.join(WIKI, "*.md"))):
        rel = os.path.relpath(f, ROOT)
        text = open(f, encoding="utf-8").read()
        if has_legacy_math(text):
            out.append(rel)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Normalize legacy math delimiters in wiki/")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry-run diff)")
    p.add_argument("--paths", nargs="+", help="limit to these wiki-relative paths")
    args = p.parse_args(argv)

    pages = affected_pages(args.paths)
    if not pages:
        print("no pages need fixing")
        return 0

    total_stats = {"display": 0, "inline": 0}
    for rel in pages:
        full = os.path.join(ROOT, rel)
        text = open(full, encoding="utf-8").read()
        new_text, stats = normalize_math(text)
        if new_text == text:
            continue
        total_stats["display"] += stats["display"]
        total_stats["inline"] += stats["inline"]
        if args.apply:
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_text)
            print(f"fixed  {rel}  (+{stats['display']} display, +{stats['inline']} inline)")
        else:
            print(f"\n--- {rel} ---")
            diff = difflib.unified_diff(
                text.splitlines(), new_text.splitlines(),
                lineterm="", fromfile=rel, tofile=rel,
            )
            for line in diff:
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                    print(line)

    print(f"\n{len(pages)} page(s), {total_stats['display']} display + {total_stats['inline']} inline conversions"
          f" {'applied' if args.apply else '(dry-run — pass --apply to write)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

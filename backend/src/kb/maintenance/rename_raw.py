#!/usr/bin/env python3
"""Rename raw/ files per meta/raw-renames.tsv without breaking references.
Dry-run by default; pass --apply to execute. Idempotent: rows already moved are skipped.

On --apply:
  - moves each file old_path -> new_path
  - .md files get frontmatter: title/aliases (original name, keeps Obsidian search working),
    original_name (provenance), tags (for filtering, e.g. tag:#source/blog-not-exact)
  - meta/corpus.tsv rows are carried to the new path (disposition/slug kept, so lint does not re-queue)
  - references in wiki/, think/ and index.md are rewritten (full path, and `basename`/`stem` in backticks)
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

from kb.paths import THINK_PATH, vault_root
ROOT = vault_root()
MAP = os.path.join(ROOT, "meta", "raw-renames.tsv")
MANIFEST = os.path.join(ROOT, "meta", "corpus.tsv")
NEW_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.(md|pdf)$")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def load_map():
    rows = []
    with open(MAP, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("old_path\t"):
                continue
            old, new, tags = (line.split("\t") + [""])[:3]
            rows.append((nfc(old), nfc(new), [t for t in tags.split(",") if t]))
    return rows


def validate(rows):
    """(errors, stale). A row whose old and new paths are both gone is stale — applied long ago
    and moved again by a later migration — and must not block today's rename: it is reported
    and skipped, never an error."""
    errors, stale, seen = [], [], set()
    for old, new, _ in rows:
        name = os.path.basename(new)
        if not NEW_NAME.match(name):
            errors.append(f"bad new name (want lowercase ascii kebab): {new}")
        if new in seen:
            errors.append(f"duplicate target: {new}")
        seen.add(new)
        old_ok = os.path.exists(os.path.join(ROOT, old))
        new_ok = os.path.exists(os.path.join(ROOT, new))
        if old_ok and new_ok:
            errors.append(f"target already exists: {new}")
        if not old_ok and not new_ok:
            stale.append(old)
    return errors, stale


def frontmatter(old, tags):
    stem = os.path.splitext(os.path.basename(old))[0]
    q = lambda s: json.dumps(s, ensure_ascii=False)
    return ("---\n"
            f"title: {q(stem)}\n"
            f"aliases: [{q(stem)}]\n"
            f"original_name: {q(os.path.basename(old))}\n"
            f"tags: [{', '.join(tags)}]\n"
            "---\n\n")


def rewrite_text(text, rows):
    for old, new, _ in rows:
        text = text.replace(old, new)
        old_base, new_base = os.path.basename(old), os.path.basename(new)
        old_stem = os.path.splitext(old_base)[0]
        text = text.replace(f"`{old_base}`", f"`{new_base}`")
        text = text.replace(f"`{old_stem}`", f"`{new_base}`")
    return text


def ref_files():
    for p in ("wiki/**/*.md", "index.md"):
        yield from glob.glob(os.path.join(ROOT, p), recursive=True)
    yield from glob.glob(os.path.join(THINK_PATH, "**", "*.md"), recursive=True)   # the shared think space


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = load_map()
    errors, stale = validate(rows)
    for old in stale:
        print(f"stale row (neither path on disk, skipped): {old}")
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    todo = [r for r in rows if os.path.exists(os.path.join(ROOT, r[0]))]
    verb = "move" if args.apply else "would move"
    print(f"{len(rows)} mapped, {len(todo)} to move, {len(rows) - len(todo)} already done")

    for old, new, tags in todo:
        print(f"{verb}: {old} -> {os.path.basename(new)}")
        if not args.apply:
            continue
        src, dst = os.path.join(ROOT, old), os.path.join(ROOT, new)
        os.rename(src, dst)
        if dst.endswith(".md"):
            with open(dst, encoding="utf-8") as f:
                body = f.read()
            if not body.startswith("---\n"):
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(frontmatter(old, tags) + body)

    # corpus.tsv — carry rows to new paths (lint keys rows by path only)
    with open(MANIFEST, encoding="utf-8") as f:
        lines = f.read().split("\n")
    path_map = {old: new for old, new, _ in rows}
    carried = 0
    for i, line in enumerate(lines):
        parts = line.split("\t")
        if len(parts) > 1 and nfc(parts[0]) in path_map:
            parts[0] = path_map[nfc(parts[0])]
            lines[i] = "\t".join(parts)
            carried += 1
    print(f"corpus.tsv: {'carried' if args.apply else 'would carry'} {carried} rows")
    if args.apply and carried:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # references
    for path in ref_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        new_text = rewrite_text(nfc(text), rows)
        if new_text != nfc(text):
            print(f"{'rewrote' if args.apply else 'would rewrite'} refs: {os.path.relpath(path, ROOT)}")
            if args.apply:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_text)

    if not args.apply:
        print("\nDry run. Re-run with --apply to execute, then `python3 -m kb.lint.lint --health`.")


if __name__ == "__main__":
    main()

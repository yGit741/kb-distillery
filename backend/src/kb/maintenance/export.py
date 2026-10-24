#!/usr/bin/env python3
"""Export KB text bundle for sharing with external LLMs.

Writes gitignored archives under .exported/:

    python3 -m kb.maintenance.export
    python3 -m kb.maintenance.export --list
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

from kb.paths import vault_root
ROOT = vault_root()
EXPORT_DIR = os.path.join(ROOT, ".exported")
PREFIX = "yonatan-thesis-kb"

SKIP_DIR_NAMES = {
    ".git",
    ".pixi",
    ".obsidian",
    ".cursor",
    ".claude",
    "copilot",
    "_quarantine",
    ".exported",
    "__pycache__",
    "node_modules",
}

SKIP_PATH_PREFIXES = (
    "meta/.ingest/",
    "meta/.distill/",
    "meta/.semfind/",
)

BINARY_SUFFIXES = {
    ".pdf",
    ".epub",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
    ".ds_store",
}

TEXT_ROOT_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "index.md",
)

TEXT_META_FILES = (
    "meta/corpus.tsv",
    "meta/coherence-warnings.tsv",
    "meta/log.md",
    "skills/README.md",
    # the docs AGENTS.md routes to
    "meta/docs/page-model.md",
    "meta/docs/raw-and-corpus.md",
    "meta/docs/collections.md",
    "meta/docs/lifecycle.md",
    "meta/docs/dev.md",
    "meta/docs/workflows.md",
    "meta/docs/semantic-lint.md",
)

TEXT_GLOBS = (
    "wiki",
    "think",
)


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _archive_name(stamp: str | None = None) -> str:
    return f"{PREFIX}-{stamp or _now_stamp()}.zip"


def _should_skip(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    for prefix in SKIP_PATH_PREFIXES:
        if rel.startswith(prefix):
            return True
    base = os.path.basename(rel)
    if base.startswith("."):
        return True
    ext = os.path.splitext(base)[1].lower()
    if ext in BINARY_SUFFIXES:
        return True
    return False


def _collect_files(include_raw_pdfs: bool) -> list[str]:
    files: list[str] = []

    for name in TEXT_ROOT_FILES:
        rel = name
        if os.path.isfile(os.path.join(ROOT, rel)):
            files.append(rel)

    for rel in TEXT_META_FILES:
        if os.path.isfile(os.path.join(ROOT, rel)):
            files.append(rel)

    for top in TEXT_GLOBS:
        base = os.path.join(ROOT, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                if _should_skip(rel):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext in {".md", ".txt", ".tsv"}:
                    files.append(rel)

    if include_raw_pdfs:
        raw_base = os.path.join(ROOT, "raw")
        if os.path.isdir(raw_base):
            for dirpath, dirnames, filenames in os.walk(raw_base):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, ROOT).replace("\\", "/")
                    if _should_skip(rel):
                        continue
                    if rel not in files:
                        files.append(rel)

    return sorted(set(files))


def _manifest(files: list[str], include_raw_pdfs: bool, stamp: str) -> str:
    wiki_n = sum(1 for f in files if f.startswith("wiki/"))
    think_n = sum(1 for f in files if f.startswith("think/"))
    raw_n = sum(1 for f in files if f.startswith("raw/"))
    lines = [
        "Yonatan Thesis KB export",
        f"created_utc: {stamp}",
        "",
        "Purpose: text bundle for external LLM context (wiki notes, think pages, index).",
        "PDFs are omitted by default; paths remain in meta/corpus.tsv.",
        "",
        f"files: {len(files)}",
        f"wiki_pages: {wiki_n}",
        f"think_pages: {think_n}",
        f"raw_files: {raw_n}",
        f"include_raw_pdfs: {include_raw_pdfs}",
        "",
        "Start with AGENTS.md and index.md, then follow [[wikilinks]].",
        "",
        "paths:",
    ]
    lines.extend(f"  - {f}" for f in files)
    return "\n".join(lines) + "\n"


def run_lint() -> int:
    r = subprocess.run(
        [sys.executable, "-m", "kb.lint.lint"],
        cwd=ROOT,
    )
    return r.returncode


def create_export(
    *,
    include_raw_pdfs: bool = False,
    lint_first: bool = True,
    stamp: str | None = None,
) -> str:
    if lint_first:
        if run_lint() != 0:
            raise RuntimeError("lint failed — fix vault or pass --skip-lint")

    stamp = stamp or _now_stamp()
    os.makedirs(EXPORT_DIR, exist_ok=True)
    archive = os.path.join(EXPORT_DIR, _archive_name(stamp))

    files = _collect_files(include_raw_pdfs)
    if not files:
        raise RuntimeError("nothing to export")

    manifest = _manifest(files, include_raw_pdfs, stamp)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("EXPORT_MANIFEST.txt", manifest)
        for rel in files:
            zf.write(os.path.join(ROOT, rel), rel)

    return archive


def list_exports() -> list[str]:
    if not os.path.isdir(EXPORT_DIR):
        return []
    pat = re.compile(rf"^{re.escape(PREFIX)}-.*\.zip$")
    names = [n for n in os.listdir(EXPORT_DIR) if pat.match(n)]
    return sorted(
        names,
        key=lambda n: os.path.getmtime(os.path.join(EXPORT_DIR, n)),
        reverse=True,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kb.maintenance.export", description="Export KB zip for LLM sharing")
    p.add_argument(
        "--include-raw-pdfs",
        action="store_true",
        help="include raw/ PDFs and other binaries (large)",
    )
    p.add_argument(
        "--skip-lint",
        action="store_true",
        help="do not run backend/src/kb/lint/lint.py before packing",
    )
    p.add_argument("--list", action="store_true", help="list existing exports")
    args = p.parse_args(argv)

    if args.list:
        exports = list_exports()
        if not exports:
            print("no exports in .exported/")
            return 0
        for name in exports:
            path = os.path.join(EXPORT_DIR, name)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"{name}\t{size_mb:.2f} MB")
        return 0

    try:
        archive = create_export(
            include_raw_pdfs=args.include_raw_pdfs,
            lint_first=not args.skip_lint,
        )
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    size_mb = os.path.getsize(archive) / (1024 * 1024)
    print(f"exported → {archive} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

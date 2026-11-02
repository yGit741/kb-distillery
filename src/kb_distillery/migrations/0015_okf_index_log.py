"""OKF reserved files (schema 1.5): `index.md` and `log.md` live in the bundle root `wiki/`, in OKF shape.

  index.md       the generated catalog moves from the vault root to wiki/index.md. The root file is removed; lint
                 writes wiki/index.md (frontmatter `okf_version: 0.2` only, bulleted `[Title](slug.md) — summary` rows, no status).
  meta/log.md    becomes wiki/log.md: no frontmatter, `# Log`, one `## YYYY-MM-DD` heading per day (newest day first)
                 and under it the day's entries, newest first, each `### <op> | <summary>` with its body lines kept.
                 Every entry of the old log is carried over; the text before the first entry (frontmatter, title,
                 intro) is dropped and counted in the report. A `### ` line inside an old entry body is demoted to
                 `####` so it cannot be read as an entry. An existing wiki/log.md is merged in, not overwritten.
Idempotent: nothing to move means nothing changes. Nothing is written until every entry has been parsed and merged.

    python src/kb_distillery/migrations/0015_okf_index_log.py [--root R] [--dry-run]
"""
import argparse
import os
import re
import sys

from kb_distillery.vault import log as kblog

PRODUCES = (1, 5)
LEGACY_ENTRY = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (.+?)\s*$")
LEGACY_INDEX = "index.md"
LEGACY_LOG = os.path.join("meta", "log.md")
NEW_LOG = os.path.join("wiki", "log.md")


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def parse_legacy(text):
    """([(date, block lines)] in file order, preamble line count, demoted heading count). A block is `### rest` and
    the entry's body lines, without trailing blank lines."""
    entries, cur, preamble, demoted = [], None, 0, 0
    for line in text.split("\n"):
        m = LEGACY_ENTRY.match(line)
        if m:
            cur = (m.group(1), [f"### {m.group(2)}"])
            entries.append(cur)
        elif cur is None:
            preamble += 1 if line.strip() else 0
        else:
            if line.startswith("### "):
                line, demoted = "#" + line, demoted + 1
            cur[1].append(line)
    for _d, block in entries:
        while len(block) > 1 and not block[-1].strip():
            block.pop()
    return entries, preamble, demoted


def merge(new_days, legacy_entries):
    """[(date, blocks)] newest day first, entries newest first: what wiki/log.md already holds comes first within a
    day, then the legacy entries latest-in-file first. A legacy entry equal to one wiki/log.md already holds (a rerun
    after a partial move) is skipped; equal entries within the legacy log are all kept."""
    by_day = {d: [list(b) for b in blocks] for d, blocks in new_days}
    held = {d: [tuple(b) for b in blocks] for d, blocks in new_days}
    for date, block in reversed(legacy_entries):
        if tuple(block) in held.get(date, ()):
            continue
        by_day.setdefault(date, []).append(list(block))
    return sorted(by_day.items(), key=lambda kv: kv[0], reverse=True)


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    report = {"index_removed": False, "index_bytes": 0, "log_moved": False, "entries": 0, "days": 0,
              "preamble_dropped": 0, "demoted_headings": 0, "merged_into_existing": False, "wrote": []}
    index_path = os.path.join(root, LEGACY_INDEX)
    legacy_path = os.path.join(root, LEGACY_LOG)
    new_path = os.path.join(root, NEW_LOG)
    write_log = None
    if os.path.isfile(legacy_path):
        entries, report["preamble_dropped"], report["demoted_headings"] = parse_legacy(_read(legacy_path))
        existing = kblog.parse(_read(new_path)) if os.path.isfile(new_path) else []
        report["merged_into_existing"] = bool(existing)
        days = merge(existing, entries)
        report["entries"] = sum(len(b) for _d, b in days)
        report["days"] = len(days)
        report["log_moved"] = True
        write_log = kblog.render(days)
        if sum(len(b) for _d, b in kblog.parse(write_log)) != report["entries"]:
            raise RuntimeError("the converted log does not hold every entry; nothing was written")
    if os.path.isfile(index_path):
        report["index_removed"] = True
        report["index_bytes"] = os.path.getsize(index_path)
    if not dry_run:
        if write_log is not None:
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            tmp = new_path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(write_log)
            os.replace(tmp, new_path)
            os.remove(legacy_path)
            report["wrote"].append(NEW_LOG)
        if report["index_removed"]:
            os.remove(index_path)
    _print(report, dry_run)
    return report


def _print(r, dry_run):
    verb = "would " if dry_run else ""
    print(f"okf index+log: {verb}move meta/log.md -> wiki/log.md ({r['entries']} entries, {r['days']} days"
          f"{', merged into an existing wiki/log.md' if r['merged_into_existing'] else ''}), "
          f"{verb}remove the root index.md ({r['index_bytes']} bytes; lint writes wiki/index.md)"
          if r["log_moved"] or r["index_removed"] else "okf index+log: nothing to move")
    if r["preamble_dropped"] or r["demoted_headings"]:
        print(f"  preamble lines dropped: {r['preamble_dropped']}  entry-body headings demoted: {r['demoted_headings']}")


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        apply(a.root, dry_run=a.dry_run)
    except RuntimeError as e:
        sys.exit(f"error: {e}")

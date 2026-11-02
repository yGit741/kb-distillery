"""The source model (schema 1.0): `layer:` on every page, two type renames, `depth`, disposition `source`.

Driven by meta/migration/source-model/spec_map.json (the same map `src/kb_distillery/ops/invariants.py compare
--map` checks against):
  * per page, only the front matter changes, through `wikiio.write_front_matter` (raises instead of
    writing if a body byte would move): `type: theme|concept` → `topic|idea`, a `layer:` line right
    after `type:`, `digestion-status:` → `depth:` with `catalog` → `listed`;
  * meta/corpus.tsv: only the `disposition` column, `digested` → `source`.
Refuses to run while any meta/.ingest session is open (closed sessions are history and are not
rewritten). Backs up every front matter it changes and the manifest to
meta/.migrate/source-model/backup/ first. Idempotent: a second run changes nothing.

    python src/kb_distillery/migrations/0008_source_model.py [--root R] --dry-run   # plan.json + diff, no writes
"""
import argparse
import datetime
import difflib
import json
import os
import sys

PRODUCES = (1, 0)
from kb_distillery.config.paths import vault_root
SPEC = os.path.join("meta", "migration", "source-model", "spec_map.json")
OUT = os.path.join("meta", ".migrate", "source-model")


def _meta(root):
    meta = os.path.join(root, "meta")
    from kb_distillery.vault import wikiio
    from kb_distillery.ops import invariants
    return wikiio, invariants


def open_sessions(root):
    idir = os.path.join(root, "meta", ".ingest")
    out = []
    for name in sorted(os.listdir(idir)) if os.path.isdir(idir) else []:
        sp = os.path.join(idir, name, "session.json")
        if os.path.isfile(sp):
            with open(sp, encoding="utf-8") as f:
                if json.load(f).get("status") in ("open", "finalizing"):
                    out.append(name)
    return out


def plan(root):
    """[(rel, old text, new text)] for pages, and (old, new) manifest text."""
    wikiio, inv = _meta(root)
    with open(os.path.join(root, SPEC), encoding="utf-8") as f:
        spec = json.load(f)
    pages = []
    wiki = os.path.join(root, "wiki")
    for fn in sorted(os.listdir(wiki)):
        if not fn.endswith(".md") or fn.startswith("."):
            continue
        rel = f"wiki/{fn}"
        with open(os.path.join(root, rel), encoding="utf-8", newline="") as f:
            old = f.read()
        fm, body = wikiio.split_page(old)
        if not fm:
            continue
        lines = inv.fm_lines(fm.encode("utf-8"))
        new_lines = inv.map_fm(lines, spec)
        if new_lines != lines:
            pages.append((rel, old, "---\n" + "\n".join(new_lines) + "\n---\n" + body))
    mpath = os.path.join(root, "meta", "corpus.tsv")
    manifest = None
    if os.path.isfile(mpath):
        with open(mpath, encoding="utf-8", newline="") as f:
            old = f.read()
        out = []
        for line in old.split("\n"):
            if line and not line.startswith(("#", "path\t")):
                parts = line.split("\t")
                if len(parts) > 3:
                    parts = inv.map_corpus_row(parts[1:], spec)
                    line = "\t".join([line.split("\t")[0]] + parts)
            out.append(line)
        new = "\n".join(out)
        if new != old:
            manifest = (old, new)
    return spec, pages, manifest


def _diff(rel, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=0))


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    busy = open_sessions(root)
    if busy:
        raise RuntimeError(f"refusing to migrate: open ingest sessions {busy} — finalize or abort them")
    wikiio, _inv = _meta(root)
    _spec, pages, manifest = plan(root)
    out = os.path.join(root, OUT)
    os.makedirs(out, exist_ok=True)
    summary = {"pages": len(pages), "manifest": bool(manifest), "dry_run": dry_run,
               "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if dry_run:
        with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as f:
            json.dump({**summary, "changes": [rel for rel, _o, _n in pages]}, f, indent=1)
        with open(os.path.join(out, "plan.diff"), "w", encoding="utf-8") as f:
            for rel, old, new in pages:
                f.write(_diff(rel, old, new))
            if manifest:
                f.write(_diff("meta/corpus.tsv", *manifest))
        print(f"dry run: {len(pages)} pages, manifest {'changes' if manifest else 'unchanged'} → {OUT}/plan.diff")
        return summary
    if not pages and not manifest:
        print("source model: nothing to change")
        return summary
    backup = os.path.join(out, "backup")
    os.makedirs(os.path.join(backup, "wiki"), exist_ok=True)
    for rel, old, _new in pages:
        with open(os.path.join(backup, rel), "w", encoding="utf-8", newline="") as f:
            f.write(wikiio.split_page(old)[0])            # the front matter is all that changes
    if manifest:
        with open(os.path.join(backup, "corpus.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write(manifest[0])
    for rel, old, new in pages:
        wikiio.write_front_matter(os.path.join(root, rel), wikiio.split_page(new)[0])
    if manifest:
        with open(os.path.join(root, "meta", "corpus.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write(manifest[1])
    with open(os.path.join(out, "applied.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(f"source model: {len(pages)} pages, manifest {'migrated' if manifest else 'unchanged'} "
          f"(backup {os.path.relpath(backup, root)})")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.root, dry_run=a.dry_run)

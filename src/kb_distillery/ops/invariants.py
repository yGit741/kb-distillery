"""Vault invariants: a safety net for schema migrations (snapshot → change → compare).

    python -m kb_distillery.ops.invariants snapshot [--root R] [--out FILE] [--no-lint]
    python -m kb_distillery.ops.invariants compare BEFORE AFTER [--map spec_map.json]

A snapshot records, for one checkout:
  * every page's front-matter lines and the SHA-256 of its body (the bytes after the closing `---`);
  * page counts per layer, type, depth and status;
  * link, dangling and orphan counts;
  * lint errors and warnings (`src/kb_distillery/lint/lint.py`, run as a subprocess — it regenerates index.md and
    corpus.tsv as always) and the open rows of meta/coherence-warnings.tsv;
  * per course/series hub: its Contents table against the corpus rows that name it;
  * every corpus.tsv row, and the sha1 of every raw file on disk (`lint.sha1`) against its row,
    with the gitignored binaries this checkout lacks listed.

`compare` without `--map` demands identity. With `--map` (meta/migration/<name>/spec_map.json)
only the mapped changes are allowed: per page, the AFTER front matter must equal the BEFORE one
rewritten by the map (type renames, the inserted layer line, renamed fields and values), every
body hash must be equal, corpus rows may differ only in a mapped disposition, raw/ must be
byte-identical, links/dangling/orphans/hub agreement unchanged, lint errors may not grow and
warnings may not grow. Exit 0 when the invariants hold, 1 otherwise.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys

from kb_distillery.paths import vault_root
from kb_distillery.core.links import WIKILINK_TARGET
META_DIR = os.path.join(vault_root(), "meta")
REPO = vault_root()

FORMAT = "kb-invariants/1"
_LINK = WIKILINK_TARGET
_DAYS = re.compile(r"\b\d+ days\b")
_LINE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):(?P<sp>\s*)(?P<val>[^\s#][^#]*?)?(?P<rest>\s*(#.*)?)$")


# ---------------------------------------------------------------- pages

def split_page(data):
    """bytes → (front matter incl. both fences, body). No front matter → (b"", data)."""
    if not data.startswith(b"---\n"):
        return b"", data
    end = data.find(b"\n---\n", 3)
    if end != -1:
        return data[:end + 5], data[end + 5:]
    if data.endswith(b"\n---"):
        return data, b""
    return b"", data


def fm_lines(fm_bytes):
    text = fm_bytes.decode("utf-8", errors="replace")
    lines = text.split("\n")
    return lines[1:-2] if text.endswith("\n---\n") else lines[1:-1]


def fm_value(lines, key):
    for line in lines:
        m = _LINE.match(line)
        if m and m.group("key") == key:
            return (m.group("val") or "").strip()
    return None


def read_pages(root):
    pages = {}
    wiki = os.path.join(root, "wiki")
    for fn in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not fn.endswith(".md") or fn.startswith("."):
            continue
        with open(os.path.join(wiki, fn), "rb") as f:
            data = f.read()
        fm, body = split_page(data)
        pages[fn[:-3]] = {"fm": fm_lines(fm) if fm else None,
                          "body_sha": hashlib.sha256(body).hexdigest(),
                          "_text": data.decode("utf-8", errors="replace")}
    return pages


def page_counts(pages):
    c = {"layer": collections.Counter(), "type": collections.Counter(),
         "depth": collections.Counter(), "status": collections.Counter()}
    for p in pages.values():
        lines = p["fm"] or []
        t = fm_value(lines, "type") or "-"
        c["layer"][fm_value(lines, "layer") or "-"] += 1
        c["type"][t] += 1
        depth = fm_value(lines, "depth") or fm_value(lines, "digestion-status")
        if depth:
            c["depth"][f"{t}:{depth}"] += 1
        c["status"][f"{t}:{fm_value(lines, 'status') or '-'}"] += 1
    return {k: dict(sorted(v.items())) for k, v in c.items()}


def _related(lines):
    v = fm_value(lines or [], "related") or ""
    return [x.strip() for x in v.strip("[]").split(",") if x.strip()]


def link_counts(pages):
    """Wikilinks (body + `related:`), links to no page or alias, pages nothing links to."""
    known = set(pages)
    for p in pages.values():
        known.update(x.strip() for x in (fm_value(p["fm"] or [], "aliases") or "").strip("[]").split(",")
                     if x.strip())
    inbound = collections.Counter()
    total = dangling = 0
    for slug, p in pages.items():
        targets = {m.strip() for m in _LINK.findall(p["_text"])} | set(_related(p["fm"]))
        total += len(targets)
        for t in targets:
            if t in known:
                inbound[t] += 1
            else:
                dangling += 1
    orphans = sum(1 for s in pages if not inbound[s])
    return {"links": total, "dangling": dangling, "orphans": orphans}


# ---------------------------------------------------------------- corpus, raw, hubs

def read_corpus(root):
    rows = {}
    path = os.path.join(root, "meta", "corpus.tsv")
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith(("#", "path\t")):
                continue
            parts = line.split("\t")
            rows[parts[0]] = parts[1:]
    return rows


def raw_state(root, corpus):
    from kb_distillery.lint import lint
    old, lint.ROOT = lint.ROOT, root
    try:
        files = {}
        raw = os.path.join(root, "raw")
        for dirpath, dirnames, filenames in os.walk(raw, followlinks=True):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                files[rel] = lint.sha1(rel)
    finally:
        lint.ROOT = old
    from kb_distillery.core.schema import RAW_BINARY_EXTS
    mismatch = sorted(p for p, row in corpus.items() if p in files and row and row[0] != files[p])
    missing = sorted(p for p in corpus if p not in files and os.path.splitext(p)[1].lower() in RAW_BINARY_EXTS)
    return {"files": files, "sha_mismatch": mismatch, "missing_binaries": missing}


def hub_agreement(pages, corpus):
    """course/series hubs: Contents raw paths vs corpus rows whose `collection` names the hub."""
    from kb_distillery.core import hubs
    out = {}
    for slug, p in pages.items():
        if fm_value(p["fm"] or [], "type") not in ("course", "series"):
            continue
        table = {r for row in hubs.parse_contents(p["_text"]) for r in row["raws"]}
        members = {path for path, row in corpus.items()
                   if len(row) > 4 and slug in [c.strip() for c in row[4].split(",")]}
        out[slug] = {"table": len(table), "corpus": len(members), "agree": table == members}
    return out


# ---------------------------------------------------------------- lint, coherence

def run_lint(root):
    script = os.path.join(root, "meta", "lint.py")
    if not os.path.isfile(script):
        script = os.path.join(META_DIR, "lint.py")
    env = {**os.environ, "KB_ROOT": root}
    cp = subprocess.run([sys.executable, script], cwd=root, env=env, capture_output=True, text=True)
    errors = sorted(_DAYS.sub("N days", l[6:]) for l in cp.stdout.splitlines() if l.startswith("ERROR "))
    warns = sorted(_DAYS.sub("N days", l[6:]) for l in cp.stdout.splitlines() if l.startswith("warn  "))
    return {"returncode": cp.returncode, "errors": errors, "warnings": warns}


def coherence_open(root):
    path = os.path.join(root, "meta", "coherence-warnings.tsv")
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 6 and parts[0] != "id" and parts[5] == "open":
                    rows.append(f"{parts[2]}\t{parts[3]}")
    return sorted(rows)


# ---------------------------------------------------------------- snapshot

def snapshot(root, lint=True):
    root = os.path.abspath(root)
    lint_res = run_lint(root) if lint else None        # first: lint regenerates corpus.tsv
    pages = read_pages(root)
    corpus = read_corpus(root)
    return {
        "format": FORMAT,
        "counts": page_counts(pages),
        "links": link_counts(pages),
        "lint": lint_res,
        "coherence_open": coherence_open(root),
        "hubs": hub_agreement(pages, corpus),
        "corpus": corpus,
        "raw": raw_state(root, corpus),
        "pages": {s: {"fm": p["fm"], "body_sha": p["body_sha"]} for s, p in pages.items()},
    }


def dump(snap, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- the map

def load_map(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def map_fm(lines, spec):
    """Front-matter lines rewritten by the spec map: `type:` renamed with the `layer:` line inserted
    right after it, renamed fields, renamed values. Unmapped lines are kept byte for byte."""
    if spec is None or lines is None:
        return lines
    types = spec.get("types", {})
    fields = spec.get("rename_fields", {})
    values = spec.get("values", {})
    layer_key = spec.get("layer_field", "layer")
    out = []
    for line in lines:
        m = _LINE.match(line)
        if not m or line.startswith((" ", "\t")):
            out.append(line)
            continue
        key, val = m.group("key"), (m.group("val") or "").strip()
        if key == layer_key:
            continue                                # re-derived from the type below
        new_key = fields.get(key, key)
        new_val = val
        if key == "type" and val in types:
            new_val = types[val]["type"]
        elif new_key in values and val in values[new_key]:
            new_val = values[new_key][val]
        if (new_key, new_val) != (key, val):
            line = f"{new_key}:{m.group('sp')}{new_val}{m.group('rest') or ''}"
        out.append(line)
        if key == "type" and val in types:
            out.append(f"{layer_key}: {types[val]['layer']}")
    return out


def map_corpus_row(row, spec):
    if spec is None or len(row) < 3:
        return row
    disp = spec.get("dispositions", {})
    return row[:2] + [disp.get(row[2], row[2])] + row[3:]


# ---------------------------------------------------------------- compare

def compare(a, b, spec=None, out=print):
    """Problems found between two snapshots (empty list = the invariants hold)."""
    problems = []

    def bad(msg):
        problems.append(msg)

    pa, pb = a["pages"], b["pages"]
    for s in sorted(set(pa) ^ set(pb)):
        bad(f"page set differs: {s} {'gone' if s in pa else 'new'}")
    body_same = 0
    for s in sorted(set(pa) & set(pb)):
        if pa[s]["body_sha"] != pb[s]["body_sha"]:
            bad(f"body changed: {s}")
        else:
            body_same += 1
        want = map_fm(pa[s]["fm"], spec)
        if want != pb[s]["fm"]:
            diff = [l for l in (pb[s]["fm"] or []) if l not in (want or [])]
            gone = [l for l in (want or []) if l not in (pb[s]["fm"] or [])]
            bad(f"front matter of {s} is not the mapped one (+{diff[:3]} -{gone[:3]})")
    expected_counts = page_counts({s: {"fm": map_fm(p["fm"], spec)} for s, p in pa.items()})
    if expected_counts != b["counts"]:
        for k in expected_counts:
            if expected_counts[k] != b["counts"].get(k):
                bad(f"counts[{k}]: expected {expected_counts[k]} got {b['counts'].get(k)}")
    if a["links"] != b["links"]:
        bad(f"links: {a['links']} → {b['links']}")
    if a["hubs"] != b["hubs"]:
        bad(f"hub agreement changed: {[h for h in set(a['hubs']) | set(b['hubs']) if a['hubs'].get(h) != b['hubs'].get(h)]}")
    if a["coherence_open"] != b["coherence_open"]:
        bad(f"open coherence rows: {len(a['coherence_open'])} → {len(b['coherence_open'])}")

    ca, cb = a["corpus"], b["corpus"]
    for p in sorted(set(ca) ^ set(cb)):
        bad(f"corpus row set differs: {p}")
    for p in sorted(set(ca) & set(cb)):
        if map_corpus_row(ca[p], spec) != cb[p]:
            bad(f"corpus row changed beyond the map: {p} {ca[p]} → {cb[p]}")
    ra, rb = a["raw"], b["raw"]
    if ra["files"] != rb["files"]:
        changed = sorted(k for k in set(ra["files"]) | set(rb["files"]) if ra["files"].get(k) != rb["files"].get(k))
        bad(f"raw/ changed: {len(changed)} files, e.g. {changed[:5]}")
    for k in ("sha_mismatch", "missing_binaries"):
        if ra[k] != rb[k]:
            bad(f"raw {k}: {len(ra[k])} → {len(rb[k])}")

    la, lb = a.get("lint"), b.get("lint")
    if la and lb:
        if len(lb["errors"]) > len(la["errors"]) or (not la["errors"] and lb["errors"]):
            bad(f"lint errors {len(la['errors'])} → {len(lb['errors'])}: {lb['errors'][:5]}")
        if len(lb["warnings"]) > len(la["warnings"]):
            bad(f"lint warnings {len(la['warnings'])} → {len(lb['warnings'])}")
        if spec is None and la != lb:
            bad("lint output differs")
    out(f"pages {len(pa)} → {len(pb)} · bodies identical {body_same}/{len(set(pa) & set(pb))} · "
        f"raw files {len(ra['files'])} → {len(rb['files'])} · corpus rows {len(ca)} → {len(cb)}")
    if la and lb:
        out(f"lint errors {len(la['errors'])} → {len(lb['errors'])} · warnings {len(la['warnings'])} → {len(lb['warnings'])}")
    out(f"layers {b['counts']['layer']}")
    out(f"types  {b['counts']['type']}")
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb_distillery.ops.invariants", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--root", default=os.environ.get("KB_ROOT") or REPO)
    s.add_argument("--out", default="-")
    s.add_argument("--no-lint", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--map", default=None)
    args = p.parse_args(argv)
    if args.cmd == "snapshot":
        snap = snapshot(args.root, lint=not args.no_lint)
        if args.out == "-":
            json.dump(snap, sys.stdout, indent=1, sort_keys=True, ensure_ascii=False)
            print()
        else:
            dump(snap, args.out)
            print(f"snapshot → {args.out} ({len(snap['pages'])} pages, {len(snap['corpus'])} corpus rows)")
        return 0
    problems = compare(load(args.before), load(args.after), load_map(args.map))
    for m in problems[:60]:
        print(f"FAIL {m}")
    if len(problems) > 60:
        print(f"… {len(problems) - 60} more")
    print("invariants hold" if not problems else f"{len(problems)} invariant violation(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

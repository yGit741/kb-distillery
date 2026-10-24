"""Vault invariants: the "did we break anything" numbers, read-only over any vault.

    pixi run harness-invariants                          print the headline numbers for this checkout
    pixi run harness-invariants -- --out baseline.json   write them (counts + SHA-256 of every page body)
    pixi run harness-invariants -- --compare baseline.json
                                                         line-by-line diff; exit 1 on any body-hash
                                                         change/removal or any count regression

Read-only: this reads `wiki/`, `meta/corpus.tsv`, `meta/coherence-warnings.tsv`; it never writes into
the vault. The numbers that need the vault's own tools (lint counts, graph nodes/edges, share-size
estimate) are computed in a throwaway COPY of the vault under the system temp dir.

Everything is keyed by the new data-model vocabulary (type / kind / depth); the one translation from
the live 16-type vault lives in legacy_model.py (DELETE after data-model stage 7). Page bodies are
hashed per slug, independent of type, so the hashes survive the migration unchanged.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .legacy_model import to_new_model

REPO = Path(__file__).resolve().parents[3]
LINK = re.compile(r"\[\[([^\]|#\\]+)")
CODE = re.compile(r"^\s*(?:>\s*)*(```|~~~).*?^\s*(?:>\s*)*\1[^\n]*$|`[^`\n]+`", re.M | re.S)
RAW_BINARY_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pptx", ".ppt", ".key"}
ROOT_MD = {"index", "AGENTS", "CLAUDE", "README", "GEMINI"}
LINT_LINE = re.compile(r"(\d+) pages · (\d+) raw files · (\d+) queued · (\d+) errors · (\d+) warnings")

# direction of "worse" per count: "down" = a decrease is a regression, "up" = an increase is
WORSE = {"pages_total": "down", "links_total": "down", "graph_nodes": "down", "graph_edges": "down",
         "raws_resolvable": "down", "dangling_links": "up", "orphan_pages": "up", "lint_errors": "up",
         "lint_warnings": "up", "coherence_open": "up", "raws_unresolvable": "up",
         "collection_tables_inconsistent": "up"}

GRAPH_SNIPPET = r'''
import json, sys
from kb.services import pages as explore_data, graph as graph_data
snap = graph_data.build_graph_snapshot()
idx = explore_data.build_index()
json.dump({"nodes": snap["node_count"], "edges": snap["link_count"],
           "share_bytes_estimate": len(json.dumps(snap)) + len(json.dumps(idx))}, open(sys.argv[1], "w"))
'''


def parse_frontmatter(text):
    """(fm dict, body). body = everything after the closing delimiter line, byte for byte."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        line = line.split("#")[0].rstrip()
        if not line.strip() or ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip()] = v
    nl = text.find("\n", end + 1)
    return fm, text[nl + 1:] if nl != -1 else ""


def load_pages(root):
    pages = {}
    for p in sorted((Path(root) / "wiki").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        pages[p.stem] = (fm, body, text)
    return pages


def _as_list(v):
    if v is None:
        return []
    return [str(x).strip() for x in (v if isinstance(v, list) else [v]) if str(x).strip()]


def _known_targets(root, slugs):
    known = set(slugs) | ROOT_MD
    meta = Path(root) / "meta"
    for dirpath, dirnames, files in os.walk(meta):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        known |= {f[:-3] for f in files if f.endswith(".md")}
    return known


def read_corpus(root):
    path = Path(root) / "meta" / "corpus.tsv"
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip() or line.startswith("path\t"):
                continue
            c = line.split("\t") + [""] * 7
            rows.append({"path": c[0], "disposition": c[3], "collection": c[5]})
    return rows


def read_coherence_open(root):
    path = Path(root) / "meta" / "coherence-warnings.tsv"
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()[1:]
    return sum(1 for l in lines if l.split("\t")[-1] == "open")


def contents_raws(body):
    m = re.search(r"^## Contents\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return set(re.findall(r"`(raw/[^`]+)`", m.group(1))) if m else set()


def structure_counts(root):
    pages = load_pages(root)
    c = {"pages_total": len(pages)}
    by_kind, by_depth = Counter(), Counter()
    for _slug, (fm, _body, _t) in pages.items():
        typ, kind, depth = to_new_model(fm)
        by_kind[f"{typ}/{kind}"] += 1
        if typ == "source":
            by_depth[f"{kind}:{depth or 'none'}"] += 1
    c["pages_by_type_kind"] = dict(sorted(by_kind.items()))
    c["sources_by_kind_depth"] = dict(sorted(by_depth.items()))

    known = _known_targets(root, pages)
    pairs, dangling = set(), set()
    inbound = Counter()
    for slug, (_fm, _body, text) in pages.items():
        for target in LINK.findall(CODE.sub("", text)):
            target = target.strip()
            pairs.add((slug, target))
            if target not in known:
                dangling.add((slug, target))
            elif target in pages and target != slug:
                inbound[target] += 1
    resolved = {p for p in pairs if p not in dangling}
    c["links_total"] = len(resolved)
    c["dangling_links"] = len(dangling)
    c["orphan_pages"] = sum(1 for s in pages if inbound[s] == 0)

    cited = set()
    for _slug, (fm, _b, _t) in pages.items():
        cited |= {r for r in _as_list(fm.get("raw")) if r != "none"}
    on_disk = {r for r in cited if (Path(root) / r).exists()}
    rows = read_corpus(root)
    absent = [r["path"] for r in rows if Path(r["path"]).suffix.lower() in RAW_BINARY_EXTS
              and not (Path(root) / r["path"]).exists()]
    c["raws_cited"] = len(cited)
    c["raws_resolvable"] = len(on_disk)
    c["raws_unresolvable"] = len(cited) - len(on_disk)      # absent binaries of a partial checkout count here
    c["raw_binaries_absent"] = len(absent)
    c["corpus_rows"] = len(rows)
    c["corpus_by_disposition"] = dict(sorted(Counter(r["disposition"].split(":")[0] for r in rows).items()))

    bad = []
    by_coll = {}
    for r in rows:
        for s in [x.strip() for x in r["collection"].split(",") if x.strip()]:
            by_coll.setdefault(s, set()).add(r["path"])
    tables = 0
    for slug, (fm, body, _t) in pages.items():
        typ, kind, _d = to_new_model(fm)
        if typ == "collection" and kind in ("course", "series"):
            tables += 1
            if contents_raws(body) != by_coll.get(slug, set()):
                bad.append(slug)
    c["collection_tables"] = tables
    c["collection_tables_inconsistent"] = len(bad)
    c["collection_tables_inconsistent_slugs"] = sorted(bad)
    c["coherence_open"] = read_coherence_open(root)
    c["page_bodies_sha256"] = {s: hashlib.sha256(b.encode("utf-8")).hexdigest() for s, (_f, b, _t) in sorted(pages.items())}
    return c


def vault_copy(root, dest):
    """Throwaway copy for running the vault's own lint/graph (they write index.md / corpus.tsv)."""
    skip = shutil.ignore_patterns(".git", ".pixi", ".cache", ".claude", ".cursor", ".github", "node_modules",
                                  "_quarantine", "__pycache__", ".ingest", ".exported", "*.pyc")
    shutil.copytree(root, dest, ignore=skip, symlinks=True)


def tool_counts(root):
    tmp = Path(tempfile.mkdtemp(prefix="kb-invariants-"))
    try:
        copy = tmp / "vault"
        vault_copy(root, copy)
        env = {k: v for k, v in os.environ.items() if k not in ("KB_ROOT", "KB_CI")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(copy / "backend" / "src")     # the measured vault runs its own code
        p = subprocess.run([sys.executable, "-m", "kb.lint.lint"], cwd=copy, env=env, capture_output=True, text=True, timeout=900)
        m = LINT_LINE.search(p.stdout)
        out = {"lint_ran": bool(m)}
        if m:
            out.update(lint_errors=int(m.group(4)), lint_warnings=int(m.group(5)), lint_queued=int(m.group(3)))
        snippet = tmp / "graph_snippet.py"
        snippet.write_text(GRAPH_SNIPPET, encoding="utf-8")
        res = tmp / "graph.json"
        q = subprocess.run([sys.executable, str(snippet), str(res)], cwd=copy, env=env, capture_output=True, text=True, timeout=900)
        if q.returncode == 0 and res.is_file():
            g = json.loads(res.read_text())
            out.update(graph_nodes=g["nodes"], graph_edges=g["edges"], share_bytes_estimate=g["share_bytes_estimate"])
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def collect(root, tools=True):
    root = Path(root)
    c = structure_counts(root)
    if tools:
        c.update(tool_counts(root))
    c["_schema"] = "vault-invariants/1"
    return c


# ---------------------------------------------------------------- reporting

def headline(c):
    lines = [f"pages {c['pages_total']} | links {c['links_total']} | dangling {c['dangling_links']} | orphans {c['orphan_pages']}",
             "by type/kind: " + ", ".join(f"{k}={v}" for k, v in c["pages_by_type_kind"].items())]
    if "lint_errors" in c:
        lines.append(f"lint errors {c['lint_errors']} | warnings {c['lint_warnings']} | graph {c.get('graph_nodes')} nodes / {c.get('graph_edges')} edges")
    lines.append(f"coherence open {c['coherence_open']} | raws resolvable {c['raws_resolvable']}/{c['raws_cited']} "
                 f"(partial checkout: {c['raw_binaries_absent']} raw binaries absent from disk)")
    lines.append(f"collection tables {c['collection_tables']} ({c['collection_tables_inconsistent']} inconsistent) | "
                 f"corpus rows {c['corpus_rows']} {c['corpus_by_disposition']}")
    return "\n".join(lines)


def compare(base, cur):
    """(lines, failed). Counts that differ are listed; regressions and body changes fail."""
    lines, failed = [], False
    keys = [k for k in sorted(set(base) | set(cur)) if k not in ("page_bodies_sha256", "_schema")
            and not k.endswith("_slugs")]
    for k in keys:
        a, b = base.get(k), cur.get(k)
        if a == b:
            continue
        if isinstance(a, dict) or isinstance(b, dict):
            a, b = a or {}, b or {}
            for sub in sorted(set(a) | set(b)):
                x, y = a.get(sub, 0), b.get(sub, 0)
                if x == y:
                    continue
                bad = y < x
                failed |= bad
                lines.append(f"{'REGRESSION' if bad else 'changed   '} {k}[{sub}]: {x} -> {y}")
            continue
        if a is None or b is None:
            lines.append(f"changed    {k}: {a} -> {b}")
            continue
        worse = WORSE.get(k)
        bad = (worse == "down" and b < a) or (worse == "up" and b > a)
        failed |= bad
        lines.append(f"{'REGRESSION' if bad else 'changed   '} {k}: {a} -> {b}")
    ba, bb = base.get("page_bodies_sha256", {}), cur.get("page_bodies_sha256", {})
    for slug in sorted(set(ba) | set(bb)):
        if slug not in bb:
            lines.append(f"BODY REMOVED {slug}")
            failed = True
        elif slug not in ba:
            lines.append(f"body added   {slug}")
        elif ba[slug] != bb[slug]:
            lines.append(f"BODY CHANGED {slug}")
            failed = True
    return lines, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="vault invariants (read-only)")
    ap.add_argument("--root", default=str(REPO), help="vault root (default: this checkout)")
    ap.add_argument("--out", help="write the full JSON here")
    ap.add_argument("--counts-only-out", help="write the JSON without page body hashes here")
    ap.add_argument("--compare", metavar="BASELINE.json")
    ap.add_argument("--no-tools", action="store_true", help="skip lint/graph (they run on a temp copy)")
    a = ap.parse_args(argv)
    cur = collect(a.root, tools=not a.no_tools)
    print(headline(cur))
    if a.out:
        Path(a.out).write_text(json.dumps(cur, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")
    if a.counts_only_out:
        slim = {k: v for k, v in cur.items() if k != "page_bodies_sha256"}
        Path(a.counts_only_out).write_text(json.dumps(slim, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {a.counts_only_out}")
    if a.compare:
        base = json.loads(Path(a.compare).read_text(encoding="utf-8"))
        lines, failed = compare(base, cur)
        print(f"\ncompare against {a.compare}:")
        print("\n".join("  " + l for l in lines) if lines else "  identical")
        print("INVARIANTS FAILED" if failed else "invariants hold")
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""scrap-wandb: one bundle per Weights & Biases run (0 LLM).

run → raw/inbox/run-<name>-<id>/
    run.md        what an agent reads: identity, config, summary, what the history and tables hold
    run.json      the same, structured (id, entity, project, url, state, tags, group, commit, config, summary)
    history.csv   every logged step, one column per metric
    <table>.csv   each logged table (a `wandb.Table`, from an artifact or from `run.log`)
Code, model and other file artifacts are listed in run.md, not copied: the run's URL keeps them.
A run bundle is evidence: once cataloged under raw/experiments/ it is never pulled again.
"""
import csv
import glob
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse

from kb_distillery.ingest.paths import ROOT
from kb_distillery.vault.schema import RAW_EXPERIMENTS, RUN_ITEM

DATA = "run.json"
HISTORY = "history.csv"
INBOX_PREFIX = "run-"
TABLE_SUFFIX = ".table.json"
LISTED_ONLY = {"code", "job", "wandb-history"}     # artifact types never downloaded
CELL = 160                                          # longest value shown in a run.md table cell


def _api():
    try:
        import wandb
    except ImportError as e:
        raise ValueError("scrap-wandb needs the `wandb` package in this environment (pip install wandb) "
                         "and a login (`wandb login` or $WANDB_API_KEY)") from e
    return wandb.Api()


def parse_ref(source):
    """(entity, project, run id or None) from a run URL, a project URL, `entity/project/run_id`,
    `entity/project/runs/run_id` or `entity/project`. A self-hosted URL may carry a path prefix."""
    s = (source or "").strip()
    parts = [p for p in (urlparse(s).path if "://" in s else s).split("/") if p]
    if "runs" in parts:
        i = parts.index("runs")
        if i >= 2 and len(parts) > i + 1:
            return parts[i - 2], parts[i - 1], parts[i + 1]
    elif "://" in s and len(parts) >= 2:
        return parts[-2], parts[-1], None
    elif len(parts) == 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], None
    raise ValueError(f"not a W&B run or project: {source!r} (give a run URL, entity/project/run_id or entity/project)")


def kebab(text, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:n].rstrip("-") or "run"


def existing(entity, project, run_id, root=ROOT):
    """Bundles (inbox or cataloged) of this run."""
    hits = []
    for pat in (f"raw/inbox/{INBOX_PREFIX}*/{DATA}", f"raw/{RAW_EXPERIMENTS}/*/{DATA}"):
        for p in sorted(glob.glob(os.path.join(root, pat))):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (d.get("entity"), d.get("project"), d.get("id")) == (entity, project, run_id):
                hits.append(os.path.relpath(os.path.dirname(p), root))
    return hits


def _plain(value):
    """A JSON-safe copy without W&B's internal keys; a logged media object becomes its type name."""
    if isinstance(value, dict):
        if "_type" in value:
            return f"({value['_type']})"
        return {str(k): _plain(v) for k, v in value.items() if not str(k).startswith("_wandb")}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _as_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    inner = getattr(obj, "_json_dict", None)             # wandb's HTTPSummary
    return dict(inner) if isinstance(inner, dict) else dict(obj)


def meta_of(run):
    created = getattr(run, "created_at", None)
    return {"id": run.id, "name": run.name or run.id, "entity": run.entity, "project": run.project,
            "url": run.url, "state": getattr(run, "state", None), "created": str(created) if created else None,
            "tags": list(getattr(run, "tags", None) or []), "group": getattr(run, "group", None),
            "job_type": getattr(run, "job_type", None), "notes": getattr(run, "notes", None) or "",
            "commit": getattr(run, "commit", None),
            "config": _plain(_as_dict(getattr(run, "config", None))),
            "summary": {k: v for k, v in _plain(_as_dict(getattr(run, "summary", None))).items()
                        if not k.startswith("_")}}                       # _step, _runtime, _timestamp: bookkeeping


def write_history(run, path, max_rows):
    """history.csv from the run's logged steps. Returns (rows, columns, truncated)."""
    rows, cols, truncated = [], {}, False
    for raw in run.scan_history():
        if len(rows) >= max_rows:
            truncated = True
            break
        row = {k: v for k, v in raw.items()
               if (k == "_step" or not k.startswith("_")) and not isinstance(v, (dict, list))}
        if set(row) - {"_step"}:
            rows.append(row)
            cols.update(dict.fromkeys(row))
    cols = sorted(cols, key=lambda c: (c != "_step", c))            # W&B returns keys in no fixed order
    if rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    return len(rows), cols, truncated


def _table_csv(src, dest):
    """A wandb.Table JSON file → CSV. Returns (rows, columns) or None when it is not a table."""
    try:
        t = json.load(open(src, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cols, data = t.get("columns"), t.get("data")
    if not isinstance(cols, list) or not isinstance(data, list):
        return None
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(data)
    return len(data), [str(c) for c in cols]


def pull_artifacts(run, dest, scratch, max_mb):
    """List the run's logged artifacts; download the small ones and keep their tables as CSV.
    Returns (artifacts, tables)."""
    arts, tables = [], []
    for art in run.logged_artifacts():
        size = int(getattr(art, "size", 0) or 0)
        entry = {"name": art.name, "type": art.type, "bytes": size, "tables": []}
        arts.append(entry)
        if art.type in LISTED_ONLY or size > max_mb * 1024 * 1024:
            continue
        folder = art.download(root=os.path.join(scratch, kebab(art.name, 80)))
        for src in sorted(glob.glob(os.path.join(folder, "**", f"*{TABLE_SUFFIX}"), recursive=True)):
            stem = kebab(os.path.basename(src)[:-len(TABLE_SUFFIX)], 80)
            name = f"{stem}.csv"
            if name == HISTORY or os.path.exists(os.path.join(dest, name)):
                name = f"{stem}-{kebab(art.name, 40)}.csv"
            got = _table_csv(src, os.path.join(dest, name))
            if got:
                tables.append({"file": name, "rows": got[0], "columns": got[1], "artifact": art.name})
                entry["tables"].append(name)
    return arts, tables


def _cell(value):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= CELL else s[:CELL - 1] + "…"


def _kv_table(d):
    if not d:
        return ["(none)"]
    return ["| Key | Value |", "|---|---|"] + [f"| `{k}` | {_cell(v)} |" for k, v in d.items()]


def _size(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(n, 0) / 1e3:.1f} kB"


def render_md(meta, history, tables, arts):
    rows, cols, truncated = history
    where = "/".join(x for x in (meta["entity"], meta["project"]) if x)
    out = [f"# {meta['name']}", "",
           f"- Run: {meta['url']}",
           f"- Project: {where}",
           f"- Group: {meta['group'] or '(none)'} · job type: {meta['job_type'] or '(none)'}",
           f"- State: {meta['state'] or 'unknown'} · created: {meta['created'] or 'unknown'}",
           f"- Tags: {', '.join(meta['tags']) or '(none)'}",
           f"- Code commit: {meta['commit'] or '(none recorded)'}"]
    if meta["notes"]:
        out += ["", "## Notes", "", meta["notes"].strip()]
    out += ["", "## Config", ""] + _kv_table(meta["config"])
    out += ["", "## Summary", ""] + _kv_table(meta["summary"])
    out += ["", "## History", ""]
    if rows:
        out += [f"`{HISTORY}`: {rows} rows{' (truncated)' if truncated else ''}, {len(cols)} columns.", "",
                "Columns: " + ", ".join(f"`{c}`" for c in cols)]
    else:
        out += ["No logged steps."]
    out += ["", "## Tables", ""]
    out += [f"- `{t['file']}`: {t['rows']} rows; columns " + ", ".join(f"`{c}`" for c in t["columns"])
            for t in tables] or ["(none)"]
    out += ["", "## Artifacts", ""]
    out += [f"- `{a['name']}` ({a['type']}, {_size(a['bytes'])})"
            + (f": kept as {', '.join('`' + t + '`' for t in a['tables'])}" if a["tables"] else ": not copied, see the run")
            for a in arts] or ["(none)"]
    return "\n".join(out) + "\n"


def pull_run(run, force=False, max_rows=100_000, max_mb=50, root=ROOT):
    """One run → raw/inbox/run-<name>-<id>/ (relative path). Raises resolve.DuplicateBlocked when the
    run is already in the kb: a cataloged bundle is never replaced, an inbox one only with force."""
    from kb_distillery.ingest import resolve as resolve_mod
    meta = meta_of(run)
    hits = existing(meta["entity"], meta["project"], meta["id"], root)
    cataloged = [h for h in hits if not h.startswith("raw/inbox/")]
    if cataloged or (hits and not force):
        print(f"FOUND wandb:{meta['id']} → {(cataloged or hits)[0]}")
        print("scrap blocked — a cataloged run is immutable" if cataloged
              else "scrap blocked — use the existing bundle or pass --force", file=sys.stderr)
        raise resolve_mod.DuplicateBlocked([{"raw": (cataloged or hits)[0], "reason": "wandb run id"}])
    name = hits[0].split("/")[-1][len(INBOX_PREFIX):] if hits else f"{kebab(meta['name'])}-{kebab(meta['id'], 16)}"
    rel = f"raw/inbox/{INBOX_PREFIX}{name}"
    final = os.path.join(root, rel)
    dest = os.path.join(root, ".cache", "wandb-build", name)        # built here, moved into the inbox when whole
    scratch = os.path.join(root, ".cache", "wandb-build", f"{name}.artifacts")
    for d in (dest, scratch):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(dest)
    try:
        history = write_history(run, os.path.join(dest, HISTORY), max_rows)
        arts, tables = pull_artifacts(run, dest, scratch, max_mb)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    data = {**meta, "history": {"rows": history[0], "columns": history[1], "truncated": history[2]},
            "tables": tables, "artifacts": arts}
    with open(os.path.join(dest, DATA), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(dest, RUN_ITEM), "w", encoding="utf-8") as f:
        f.write(render_md(meta, history, tables, arts))
    if os.path.isdir(final):
        shutil.rmtree(final)                                         # --force over this run's own inbox bundle
    os.makedirs(os.path.dirname(final), exist_ok=True)
    shutil.move(dest, final)
    print(f"scrap (wandb) → {rel}/ — {history[0]} history rows, {len(tables)} tables, {len(arts)} artifacts")
    return rel


def scrap_wandb(source, tag="kb", force=False, max_rows=100_000, max_mb=50, root=ROOT, api=None):
    """A run, or every finished run of a project that carries `tag` → inbox bundles. Returns their paths.
    A single run that is already in the kb raises DuplicateBlocked; in a project pull it is skipped."""
    from kb_distillery.ingest import resolve as resolve_mod
    entity, project, run_id = parse_ref(source)
    api = api or _api()
    if run_id:
        return [pull_run(api.run(f"{entity}/{project}/{run_id}"), force=force, max_rows=max_rows,
                         max_mb=max_mb, root=root)]
    out, skipped = [], 0
    for run in api.runs(f"{entity}/{project}", filters={"tags": {"$in": [tag]}} if tag else None):
        if getattr(run, "state", "finished") != "finished":
            print(f"skip {run.id}: state {run.state}")
            skipped += 1
            continue
        try:
            out.append(pull_run(run, force=force, max_rows=max_rows, max_mb=max_mb, root=root))
        except resolve_mod.DuplicateBlocked:
            skipped += 1
    print(f"scrap (wandb) {entity}/{project}: {len(out)} runs pulled, {skipped} skipped"
          + (f" (tag {tag})" if tag else ""))
    return out

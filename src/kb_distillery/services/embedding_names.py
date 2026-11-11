"""Names for the Embedding tab's principal components and clusters, written by an LLM from the pages that define
them (the pages at a component's two ends; the pages closest to a cluster's centre), each with its title and summary.

Every call goes through `kb_distillery.llm` (one request per component and per cluster, one `llm.run`), so the
backend is a flag: subscription, api or batch. Names are saved next to the vector store, stamped with the store's
signature: after `vectors-build` changes the vectors they are reported as stale instead of shown.

    python -m kb_distillery.services.embedding_names [--backend subscription|api|batch]
"""
import argparse
import datetime
import json
import os
import re
import sys
import threading

import numpy as np

from kb_distillery import llm
from kb_distillery.search import vectors
from kb_distillery.services import embedding

MODEL = "sonnet"
EFFORT = "low"
MAX_TOKENS = 600
EVIDENCE = 8                 # pages shown to the model per end of a component, and per cluster
SUMMARY_CHARS = 320
NAMES_FILE = "embedding-names.json"

COMPONENT_PROMPT = """These pages come from one personal knowledge base. They sit at the two ends of one principal \
component of the pages' embedding vectors: a direction along which the pages differ most.

LOW END
{low}

HIGH END
{high}

Name what the pages of each end have in common, so the two names read as the two poles of one axis. Use 2 to 4 plain \
words per name. If an end has no clear common theme, name it "mixed". Answer with JSON only:
{{"low": "<name>", "high": "<name>", "why": "<one short sentence on what separates the two ends>"}}"""

CLUSTER_PROMPT = """These pages come from one personal knowledge base. They are the pages closest to the centre of \
one cluster of the pages' embedding vectors ({size} pages in all).

{pages}

Name what this cluster is about in 2 to 4 plain words. If there is no clear common theme, name it "mixed". Answer with \
JSON only:
{{"name": "<name>", "why": "<one short sentence on what the pages share>"}}"""

_lock = threading.Lock()
_running = {}                # db_path -> {"backend": ..., "started": iso}
_errors = {}                 # db_path -> the last run's error, cleared by the next run


class NamesError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def names_path(db_path=None):
    return os.path.join(os.path.dirname(db_path or vectors.DB_PATH), NAMES_FILE)


def signature(db_path=None):
    """What the saved names belong to: the store file's mtime and size, or "" without a store."""
    try:
        st = os.stat(db_path or vectors.DB_PATH)
    except OSError:
        return ""
    return f"{st.st_mtime_ns}:{st.st_size}"


def load(db_path=None):
    """The saved names (any signature), or None."""
    try:
        with open(names_path(db_path), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _cards(cards_dir):
    """{slug: (title, summary)} from the cards (`# <title>`, blank line, summary)."""
    out = {}
    if not os.path.isdir(cards_dir):
        return out
    for f in os.listdir(cards_dir):
        if f.endswith(".md"):
            with open(os.path.join(cards_dir, f), encoding="utf-8") as fh:
                head, _, rest = fh.read().partition("\n")
            out[f[:-3]] = (head[2:].strip() if head.startswith("# ") else f[:-3], " ".join(rest.split()))
    return out


def _listing(slugs, cards):
    lines = []
    for s in slugs:
        title, summary = cards.get(s, (s, ""))
        lines.append(f"- {title}" + (f": {summary[:SUMMARY_CHARS]}" if summary else ""))
    return "\n".join(lines)


def build_requests(report, v, cards):
    """[(kind, index, llm.Request)] for every component and cluster of `report` (built from the store `v`)."""
    out = []
    points = report["points"]
    for c in report["components"]:
        a = c["index"]
        by = sorted(points, key=lambda p: p["pc"][a])
        low, high = [p["slug"] for p in by[:EVIDENCE]], [p["slug"] for p in by[::-1][:EVIDENCE]]
        out.append(("component", a, llm.Request(prompt=COMPONENT_PROMPT.format(low=_listing(low, cards), high=_listing(high, cards)),
                                                 id=f"component-{a}", model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS)))
    for c in report["clusters"]:
        idx = np.array([v.index[p["slug"]] for p in points if p["cluster"] == c["id"] and p["slug"] in v.index])
        if not len(idx):
            continue
        centre = v.m[idx].sum(axis=0)
        with np.errstate(all="ignore"):
            near = idx[np.argsort(-(v.m[idx] @ centre))[:EVIDENCE]]
        out.append(("cluster", c["id"], llm.Request(prompt=CLUSTER_PROMPT.format(size=c["size"], pages=_listing([v.slugs[i] for i in near], cards)),
                                                     id=f"cluster-{c['id']}", model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS)))
    return out


def parse(text, keys):
    """The first JSON object in a reply, as {key: short string} for `keys`; None when it is not there or incomplete."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    out = {k: " ".join(str(data.get(k) or "").split())[:200] for k in keys}
    return out if all(out[k] for k in keys if k != "why") else None


def name_all(backend=None, db_path=None, cards_dir=None):
    """Ask for every name, save them and return the saved record. Raises NamesError when there is nothing to name
    or the backend is unknown; a reply that cannot be read leaves that one item unnamed (counted in `failed`)."""
    db_path, cards_dir = db_path or vectors.DB_PATH, cards_dir or vectors.CARDS_DIR
    try:
        backend = llm.resolve_backend(backend)
    except llm.LLMError as e:
        raise NamesError(422, str(e)) from None
    sig = signature(db_path)
    report = embedding.build_embedding_report(db_path, cards_dir)
    v = vectors.load(db_path) if report["points"] else None
    if v is None or not len(v):
        raise NamesError(409, "no vectors to name: build the vector store first")
    reqs = build_requests(report, v, _cards(cards_dir))
    results = llm.run([r for _, _, r in reqs], backend=backend)
    record = {"signature": sig, "backend": backend, "model": MODEL, "usd": 0.0, "failed": 0,
              "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "components": {}, "clusters": {}}
    first_error = ""
    for (kind, index, _req), res in zip(reqs, results):
        record["usd"] += float(res.usd or 0)
        got = parse(res.text, ("low", "high", "why") if kind == "component" else ("name", "why")) if res.ok else None
        if got is None:
            record["failed"] += 1
            first_error = first_error or res.error or "a reply was not the JSON asked for"
            continue
        record["components" if kind == "component" else "clusters"][str(index)] = got
    record["usd"] = round(record["usd"], 4)
    if record["failed"] == len(reqs):
        raise NamesError(502, f"no names came back: {first_error}")
    path = names_path(db_path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return record


def start(backend=None, db_path=None, cards_dir=None):
    """Run `name_all` on a background thread (a batch run takes a long time); `status` reports it. Raises NamesError
    422 for an unknown backend, 409 when a run is already going or there is nothing to name."""
    db_path = db_path or vectors.DB_PATH
    try:
        backend = llm.resolve_backend(backend)
    except llm.LLMError as e:
        raise NamesError(422, str(e)) from None
    if not signature(db_path):
        raise NamesError(409, "no vectors to name: build the vector store first")
    with _lock:
        if db_path in _running:
            raise NamesError(409, "names are already being made")
        _running[db_path] = {"backend": backend}
        _errors.pop(db_path, None)

    def work():
        try:
            name_all(backend, db_path, cards_dir)
        except NamesError as e:
            _errors[db_path] = e.detail
        except Exception as e:          # noqa: BLE001  the thread must always clear its running mark
            _errors[db_path] = f"{type(e).__name__}: {e}"
        finally:
            with _lock:
                _running.pop(db_path, None)

    threading.Thread(target=work, name="embedding-names", daemon=True).start()


def status(db_path=None):
    """{state, backend, model, usd, at, failed, error, default_backend} for the report; state is none / running /
    current / stale (the vectors changed since the names were made)."""
    db_path = db_path or vectors.DB_PATH
    try:
        default = llm.resolve_backend()
    except llm.LLMError:
        default = llm.DEFAULT_BACKEND
    out = {"state": "none", "backend": None, "model": None, "usd": 0.0, "at": None, "failed": 0,
           "error": _errors.get(db_path), "default_backend": default}
    saved = load(db_path)
    if saved:
        out.update(state="current" if saved.get("signature") == signature(db_path) else "stale",
                   **{k: saved.get(k, out[k]) for k in ("backend", "model", "usd", "at", "failed")})
    running = _running.get(db_path)
    if running:
        out.update(state="running", backend=running["backend"])
    return out


def apply(report, db_path=None):
    """`report` with `names` (the status) and, while the saved names are current, each component's `low_name`,
    `high_name`, `why` and each cluster's `name`, `why`."""
    st = status(db_path)
    saved = load(db_path) if st["state"] in ("current", "running") else None
    if saved and saved.get("signature") != signature(db_path):
        saved = None
    comps, clusters = (saved or {}).get("components", {}), (saved or {}).get("clusters", {})
    out = dict(report)
    out["components"] = [{**c, "low_name": n.get("low"), "high_name": n.get("high"), "why": n.get("why")}
                         for c in report.get("components", []) for n in [comps.get(str(c["index"]), {})]]
    out["clusters"] = [{**c, "name": n.get("name"), "why": n.get("why")}
                       for c in report.get("clusters", []) for n in [clusters.get(str(c["id"]), {})]]
    out["names"] = st
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="embedding_names", description="Name the embedding's components and clusters with an LLM.")
    ap.add_argument("--backend", choices=llm.BACKENDS, help="default: $KB_LLM_BACKEND, else subscription")
    a = ap.parse_args(argv)
    try:
        r = name_all(a.backend)
    except NamesError as e:
        print(e.detail)
        return 1
    print(f"named {len(r['components'])} components and {len(r['clusters'])} clusters on {r['backend']} ({r['model']}, "
          f"${r['usd']:.4f}, {r['failed']} failed) → {names_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""digest-many: one Message Batch fills claims.json for many sources, then full-digest sessions run one at a time.

`submit` builds the same fill request `extract --fill` would (one per source) and sends them as a batch (half
price, hours). `collect` validates each reply: a good one is cached under `.cache/digest-many/<run>/claims/`, a bad
one lands in `drafts/` with the reason and is never forced. `drive` then walks the filled sources in order — one
ingest session open at a time (hard rule 6), the cached claims dropped into the session, `extract` validating
them, `map` / `draft` / `finalize` as for a hand digest, so each source ends in its own `kb(digest)` commit.
Everything is resumable: state.json holds each source's status, so re-running continues where it stopped."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import book as book_mod
from . import course, draft, extract
from . import map as map_mod
from . import session as session_mod
from .fm_merge import parse, split
from .paths import ROOT, session_dir
from kb_distillery.storage import StorageError, for_kb
from .verify import existing_digest_for_raw
from kb_distillery.core.schema import is_page_file

MODEL = "sonnet"
MAX_TEXT = 60_000          # chars of source text per request: a ceiling on cost, not a summary
OUT_TOKENS = 4_000         # expected reply size, for the up-front estimate only (the ceiling is extract.FILL_MAX_TOKENS)
STOP_AFTER = 3             # consecutive failed sessions that stop `drive`
CHUNK = 1_000              # requests per batch
TIERS = {"★★★": 0, "★★": 1, "★": 2, "–": 3}
POST_ROW = re.compile(r"\|\s*([\d-]+)\s*\|\s*\[.*?\]\((https?://[^)]+)\)\s*\|\s*`([\w-]+)`\s*\|\s*(\S+)\s*\|")


def run_dir(run):
    return os.path.join(ROOT, ".cache", "digest-many", run)


def _load(run):
    path = os.path.join(run_dir(run), "state.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"run": run, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": MODEL, "targets": {},
            "batches": [], "spent": 0.0}


def _save(state):
    os.makedirs(run_dir(state["run"]), exist_ok=True)
    path = os.path.join(run_dir(state["run"]), "state.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _log(state, **row):
    with open(os.path.join(run_dir(state["run"]), "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}, ensure_ascii=False) + "\n")


# --- selection -------------------------------------------------------------------------------------------
def page_index():
    """Every single-raw page: {slug, type, depth, raw, url} (frontmatter only)."""
    wiki = os.path.join(ROOT, "wiki")
    out = []
    for fn in sorted(os.listdir(wiki)):
        if not is_page_file(fn):
            continue
        with open(os.path.join(wiki, fn), encoding="utf-8", errors="ignore") as f:
            fm = dict((k, lines[0].split(":", 1)[1].strip()) for k, lines in parse(split(f.read())[0]))
        raw = fm.get("raw", "").strip("\"'")
        if not raw or raw.startswith("["):
            continue
        out.append({"slug": fn[:-3], "type": fm.get("type", ""), "depth": fm.get("depth", ""), "raw": raw,
                    "url": fm.get("url", "").rstrip("/")})
    return out


def hub_labels(hub):
    """{url: (topic, relevance tier)} from a series hub's `Posts by year` tables."""
    with open(os.path.join(ROOT, "wiki", f"{hub}.md"), encoding="utf-8") as f:
        text = f.read()
    section = text.split("## Posts by year", 1)[-1]
    return {m.group(2).rstrip("/"): (m.group(3), m.group(4)) for m in POST_ROW.finditer(section)}


def select(hub=None, topics=None, depth="easy", types=None, limit=None):
    """Raw paths of the pages to deepen, most relevant first (hub rows carry a relevance tier)."""
    store = for_kb(root=ROOT)

    def present(key):
        try:
            return store.exists(key)
        except StorageError:                      # a key that is not a clean raw path names nothing
            return False

    pages = [p for p in page_index() if p["depth"] == depth and present(p["raw"])]
    if types:
        pages = [p for p in pages if p["type"] in types]
    if hub:
        labels = hub_labels(hub)
        pages = [p for p in pages if p["url"] in labels and (not topics or labels[p["url"]][0] in topics)]
        pages.sort(key=lambda p: (TIERS.get(labels[p["url"]][1], 4), p["slug"]))
    out = [p["raw"] for p in pages]
    return out[:limit] if limit else out


# --- requests --------------------------------------------------------------------------------------------
def scope_for(raw_rel):
    """The row scope `full-digest` would use: the series/course row holding this file, if any."""
    hub, n, row = course.hub_row_for_raw(raw_rel)
    if row is None:
        return {}
    return {"hub": hub, "row": n, "raws": row["raws"], "label": row["title"]}


def request_id(raw_rel):
    """The batch custom_id: a hash of the raw PATH, so two clips with identical bytes never share one."""
    return hashlib.sha1(raw_rel.encode("utf-8")).hexdigest()[:20]


def build_request(raw_rel, model=MODEL):
    """(llm.Request, template) for one source, or (None, reason) when it cannot be filled in bulk."""
    from kb_distillery import llm
    scope = scope_for(raw_rel)
    if book_mod.is_book(os.path.join(ROOT, raw_rel)):
        return None, "a book: digest it by part (full-digest --pages / --section)"
    text = extract.extract_text(os.path.join(ROOT, raw_rel))
    if not text or not text.strip():
        return None, "no text extracted"
    template = extract._template(raw_rel, scope)
    prompt = extract.fill_prompt(template, text[:MAX_TEXT])
    return llm.Request(prompt, id=request_id(raw_rel), model=model, effort=extract.FILL_EFFORT,
                       max_tokens=extract.FILL_MAX_TOKENS), template


def estimate_usd(reqs, model=MODEL, out_tokens=OUT_TOKENS):
    """Batch price of these requests: input at ~3.5 chars a token, a fixed reply size each."""
    from kb_distillery import llm
    tokens_in = sum(len(r.prompt) for r in reqs) / 3.5
    return llm.cost(model, {"input_tokens": tokens_in, "output_tokens": out_tokens * len(reqs)}, batch=True)


# --- commands --------------------------------------------------------------------------------------------
def cmd_submit(a):
    from kb_distillery import llm
    state = _load(a.run)
    state["model"] = a.model
    raws = [r.strip() for r in open(a.raws_file, encoding="utf-8")] if a.raws_file else \
        select(a.hub, set(filter(None, (a.topics or "").split(","))), a.depth,
               set(filter(None, (a.types or "").split(","))), a.limit)
    retry = ("failed", "rejected") if a.retry else ()
    fresh = [r for r in dict.fromkeys(raws) if r and (r not in state["targets"] or state["targets"][r]["status"] in retry)]
    reqs, skipped = [], []
    for raw in fresh:
        req, why = build_request(raw, a.model)
        (reqs if req else skipped).append(req or (raw, why))
    est = estimate_usd(reqs, a.model)
    worst = estimate_usd(reqs, a.model, extract.FILL_MAX_TOKENS)
    print(f"{len(raws)} selected, {len(fresh)} to send, {len(reqs)} requests, {len(skipped)} skipped; "
          f"estimate ${est:.2f} on {a.model} (batch; worst case ${worst:.2f} if every reply hit the token ceiling)")
    for raw, why in skipped[:10]:
        print(f"  skipped {raw}: {why}")
    if state["spent"] + est > a.max_usd:
        print(f"refused: ${state['spent'] + est:.2f} would pass --max-usd {a.max_usd}", file=sys.stderr)
        return 2
    if a.dry_run or not reqs:
        return 0
    by_id = {request_id(r): r for r in fresh}
    for i in range(0, len(reqs), CHUNK):
        chunk = reqs[i:i + CHUNK]
        bid = llm.submit(chunk)             # a crash right here leaves a paid batch in .cache/llm/batches/ unrecorded
        for r in chunk:                     # targets are registered per chunk, only once their batch exists
            state["targets"][by_id[r.id]] = {"id": r.id, "status": "submitted", "usd": 0.0, "note": ""}
        state["batches"].append({"id": bid, "raws": [by_id[r.id] for r in chunk], "collected": False})
        _save(state)
        _log(state, event="submitted", batch=bid, n=len(chunk))
        print(f"batch {bid}: {len(chunk)} requests")
    return 0


def cmd_collect(a):
    from kb_distillery import llm
    state = _load(a.run)
    by_id = {t["id"]: raw for raw, t in state["targets"].items()}
    for b in state["batches"]:
        if b["collected"]:
            continue
        results = llm.collect(b["id"], wait_s=a.wait)
        if results and all("collect it later" in (r.error or "") for r in results):
            print(f"batch {b['id']}: not ended yet (collect again later)")
            continue
        ok = bad = 0
        for r in results:
            raw = by_id.get(r.id)
            if raw is None:
                continue
            t = state["targets"][raw]
            t["usd"] = round(r.usd, 5)
            state["spent"] = round(state["spent"] + r.usd, 5)
            if not r.ok and not r.text:
                t["status"], t["note"] = "failed", r.error
                bad += 1
                continue
            claims, reason = extract.claims_from_result(r, extract._template(raw, scope_for(raw)))
            sub = "drafts" if reason else "claims"
            os.makedirs(os.path.join(run_dir(a.run), sub), exist_ok=True)
            with open(os.path.join(run_dir(a.run), sub, f"{r.id}.json"), "w", encoding="utf-8") as f:
                json.dump(claims, f, indent=2, ensure_ascii=False)
            t["status"], t["note"] = ("rejected", reason) if reason else ("filled", "")
            ok, bad = ok + (not reason), bad + bool(reason)
        b["collected"] = True
        _save(state)
        _log(state, event="collected", batch=b["id"], ok=ok, rejected=bad)
        print(f"batch {b['id']}: {ok} filled, {bad} rejected/failed; spent ${state['spent']:.2f}")
    return 0


def digest_one(raw, claims_path):
    """One full-digest session from cached claims → the sha (after finalize committed it)."""
    if session_mod.find_open_session(raw):
        raise RuntimeError("an ingest session is already open for this source; finish or abort it first")
    sha = session_mod.begin(raw, depth="full", scope=scope_for(raw))
    try:
        shutil.copy(claims_path, os.path.join(session_dir(sha), "claims.json"))
        if extract.run_extract(sha) != 0:
            raise RuntimeError("claims did not validate")
        map_mod.run_map(sha, no_questions=True)
        draft.run_draft(sha)
        rc = subprocess.run([sys.executable, "-m", "kb_distillery.ingest", "finalize", sha], cwd=ROOT).returncode
        if rc != 0:
            raise RuntimeError("finalize failed (rolled back)")
    except BaseException:
        if session_mod.load_session(sha)["status"] == "open":
            session_mod.abort(sha)
        raise
    return sha


def _already_deepened(raw):
    page = existing_digest_for_raw(raw)
    if not page:
        return False
    with open(os.path.join(ROOT, page), encoding="utf-8", errors="ignore") as f:
        fm = dict((k, lines[0].split(":", 1)[1].strip()) for k, lines in parse(split(f.read())[0]))
    return fm.get("depth") in ("full", "deep")


def cmd_drive(a):
    state = _load(a.run)
    todo = [raw for raw, t in state["targets"].items() if t["status"] == "filled"]
    done = failed_row = 0
    for raw in todo[:a.max] if a.max else todo:
        t = state["targets"][raw]
        t0 = time.monotonic()
        if _already_deepened(raw):                                # finalized, but the crash came before state was saved
            t["status"], t["note"] = "finalized", "page already full/deep"
            _save(state)
            continue
        try:
            digest_one(raw, os.path.join(run_dir(a.run), "claims", f"{t['id']}.json"))
            t["status"], failed_row = "finalized", 0
            done += 1
        except Exception as e:                                   # a failed session rolled itself back
            t["status"], t["note"] = "failed", str(e)[:300]
            failed_row += 1
        t["seconds"] = round(time.monotonic() - t0, 1)
        _save(state)
        _log(state, event=t["status"], raw=raw, seconds=t["seconds"], note=t["note"])
        print(f"{t['status']:>9}  {t['seconds']:>6.1f}s  {raw}")
        if failed_row >= STOP_AFTER:
            print(f"stopped: {STOP_AFTER} failed sessions in a row", file=sys.stderr)
            return 1
    print(f"{done} finalized; {sum(1 for t in state['targets'].values() if t['status'] == 'filled')} left")
    return 0


def cmd_status(a):
    state = _load(a.run)
    counts = {}
    for t in state["targets"].values():
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    secs = [t["seconds"] for t in state["targets"].values() if t.get("seconds")]
    print(f"run {a.run}: {counts}  spent ${state['spent']:.2f}  batches {len(state['batches'])} "
          f"({sum(1 for b in state['batches'] if not b['collected'])} open)"
          + (f"  mean {sum(secs) / len(secs):.0f}s/source" if secs else ""))
    for raw, t in state["targets"].items():
        if t["status"] in ("rejected", "failed"):
            print(f"  {t['status']}: {raw}: {t['note'][:120]}")
    return 0


def run(argv):
    ap = argparse.ArgumentParser(prog="kb_distillery.ingest digest-many", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="batch the claim-fill requests (LLM, half price)")
    s.add_argument("--run", required=True)
    s.add_argument("--hub", help="series hub slug whose topic/relevance labels pick the posts")
    s.add_argument("--topics", help="comma-separated hub topics to keep")
    s.add_argument("--types", help="comma-separated page types to keep (paper, blog-post, …)")
    s.add_argument("--depth", default="easy", help="digest depth of the pages to deepen")
    s.add_argument("--raws-file", help="one raw path per line instead of a selection")
    s.add_argument("--limit", type=int)
    s.add_argument("--model", default=MODEL)
    s.add_argument("--max-usd", type=float, default=10.0, help="refuse a run whose estimate passes this")
    s.add_argument("--dry-run", action="store_true", help="count and estimate, send nothing")
    s.add_argument("--retry", action="store_true", help="resubmit sources that failed or were rejected earlier")
    c = sub.add_parser("collect", help="wait for the batches, validate, cache the claims")
    c.add_argument("--run", required=True)
    c.add_argument("--wait", type=int, default=24 * 3600, help="seconds to wait per batch")
    d = sub.add_parser("drive", help="one full-digest session per filled source, each its own kb(digest) commit")
    d.add_argument("--run", required=True)
    d.add_argument("--max", type=int, default=0, help="stop after N sources")
    st = sub.add_parser("status")
    st.add_argument("--run", required=True)
    a = ap.parse_args(argv)
    return {"submit": cmd_submit, "collect": cmd_collect, "drive": cmd_drive, "status": cmd_status}[a.cmd](a)

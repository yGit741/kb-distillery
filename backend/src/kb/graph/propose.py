"""Propose typed relations between wiki pages with an LLM — proposals only, nothing is written to the wiki.

    python -m kb.graph.propose submit  --run NAME [--backend batch|api|subscription] [--model sonnet]
                                       [--include-easy] [--include-people] [--limit N] [--max-usd 6] [--dry-run]
    python -m kb.graph.propose collect --run NAME [--wait S]
    python -m kb.graph.propose review  --run NAME [--min-confidence 0.5]
    python -m kb.graph.propose status  [--run NAME]

A subject is a source page at depth full/deep or a concept page (idea, question). Its candidates are the pages it
links or is linked from (wikilinks, `related:`) plus its closest card vectors, capped and filtered to the types a
relation from it may reach. One request per subject (kb.llm: batch by default) → a JSON list of
{to, kind, note, confidence, evidence}. Every proposal is validated (candidate slug, allowed kind, endpoint types,
contradicts note, confidence in 0..1); a failing one lands in the run's `rejected` bucket with its reason. The
confidence is DATA, not a gate: every structurally valid proposal is stored, weak ones included, and a cutoff is a
query-time choice (`review --min-confidence`, `apply --min-confidence`, the Relations screen). `submit --keep-above X`
sets a cutoff at creation instead (default 0: keep everything).

Writes ONLY under `<kb>/.cache/`: run state in `relations-propose/<run>/`, accepted rows in
`relations-proposals.jsonl` (one row per (from, to, kind), `origin: "llm"`, rewritten per run on collect).
`--dry-run` writes nothing at all. Kinds: the kb.toml `[edges] types` when declared, else KINDS.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

from kb import kbconfig
from kb import paths

ROOT = paths.ROOT
MODEL = "sonnet"
EASY_MODEL = "haiku"
DEFAULT_BACKEND = "batch"     # this tool's default when neither --backend nor $KB_LLM_BACKEND is set
KINDS = ("extends", "uses", "contradicts", "example-of", "open-problem-in", "addresses", "discusses", "student-of")
EASY_KINDS = frozenset({"example-of", "addresses", "open-problem-in"})
SYMMETRIC = frozenset({"contradicts"})
NOTE_REQUIRED = frozenset({"contradicts"})
PAPER_LIKE = frozenset({"paper", "blog-post", "article", "part", "lecture", "video"})
WORK = PAPER_LIKE | {"idea"}
GATES = {           # kind → (from types, to types); a declared kind without a gate takes any two distinct pages
    "extends": (WORK, WORK),
    "uses": (WORK, WORK),
    "contradicts": (WORK, WORK),
    "example-of": (WORK, frozenset({"idea"})),
    "open-problem-in": (frozenset({"question"}), WORK),
    "addresses": (PAPER_LIKE, frozenset({"question"})),
    "discusses": (PAPER_LIKE, frozenset({"idea", "topic", "question"})),
    "student-of": (frozenset({"person"}), frozenset({"person"})),
}
MEANING = {
    "extends": "builds on, generalises or strengthens the target's result or idea",
    "uses": "relies on the target's method, theorem or tool as an ingredient",
    "contradicts": "makes a claim that conflicts with a claim of the target (note: name both claims in one sentence)",
    "example-of": "is a concrete instance or example of the target idea",
    "open-problem-in": "is an open problem raised in or about the target",
    "addresses": "answers or makes progress on the target question",
    "discusses": "is substantially ABOUT the target (its main subject or one of them), whether or not it links the target; a passing mention, a list entry or a navigation link is not enough",
    "student-of": "is a student (PhD or postdoc) of the target person",
}
CONCEPT_SUBJECTS = frozenset({"idea", "question"})
DEEP = frozenset({"full", "deep"})
SHALLOW = frozenset({"easy", "listed"})
MIN_CONFIDENCE = 0.5       # the default REVIEW cutoff and the screen's "below the cut" mark, not a validation gate
KEEP_ABOVE = 0.0           # creation-time cutoff: a proposal below it is rejected when the reply is read (0 = keep all)
MAX_CANDIDATES = 20
VECTOR_K = 5
EXCERPT = 1500
OUT_TOKENS = 600           # expected reply, for the estimate
MAX_TOKENS = 2000          # reply ceiling, the worst case of the estimate
CHUNK = 1000               # requests per batch
DIRECT_CHUNK = 20          # api/subscription requests between state saves
OUT_FILE = "relations-proposals.jsonl"


def cache_dir():
    return os.path.join(ROOT, ".cache")


def run_dir(run):
    return os.path.join(cache_dir(), "relations-propose", run)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load(run):
    path = os.path.join(run_dir(run), "state.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"run": run, "created": _now(), "subjects": {}, "batches": [], "spent": 0.0}


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def _save(state):
    _write_atomic(os.path.join(run_dir(state["run"]), "state.json"), json.dumps(state, indent=1, ensure_ascii=False))


def _log(state, **row):
    os.makedirs(run_dir(state["run"]), exist_ok=True)
    with open(os.path.join(run_dir(state["run"]), "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": _now(), **row}, ensure_ascii=False) + "\n")


# --- kinds and gates ---------------------------------------------------------------------------------------
def kind_config(cfg=None):
    """{kinds, symmetric, note_required}: the kb's `[edges] types` (via kb.services.cypher.edge_config), else KINDS."""
    from kb.services.cypher import edge_config
    cfg = cfg if cfg is not None else kbconfig.current()
    ec = edge_config(cfg)
    declared = list(ec.get("types") or [])
    if not declared and cfg is not None:            # edge_config on main has no `types` yet: read the table itself
        given = cfg.section("edges").get("types")
        declared = [str(t) for t in given if t] if isinstance(given, list) else []
    kinds = tuple(dict.fromkeys(declared)) or KINDS
    sym_labels = {str(s).upper() for s in ec.get("symmetric") or ()}
    symmetric = {k for k in kinds if k in SYMMETRIC or k.upper().replace("-", "_") in sym_labels}
    note_required = (NOTE_REQUIRED | set(ec.get("note_required") or ())) & set(kinds)
    return {"kinds": kinds, "symmetric": symmetric, "note_required": note_required}


def gate_ok(kind, from_type, to_type):
    gate = GATES.get(kind)
    return gate is None or (from_type in gate[0] and to_type in gate[1])


def kinds_for(subject_type, kc, easy=False):
    """The kinds a relation FROM a page of this type may take."""
    out = [k for k in kc["kinds"] if k not in GATES or subject_type in GATES[k][0]]
    return [k for k in out if k in EASY_KINDS] if easy else out


# --- pages, subjects, candidates ---------------------------------------------------------------------------
def _unquote(v):
    v = str(v or "").strip()
    return v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'" else v


def _no_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        return text[end + 4:] if end != -1 else text
    return text


def _body(text):
    """The page body after its frontmatter and title, without the user's `## My notes` section."""
    text = re.sub(r"(?ms)^## My notes\b.*?(?=^## |\Z)", "", _no_frontmatter(text))
    return re.sub(r"(?m)^#\s+.+$", "", text, count=1).strip()


def _title(text, slug):
    m = re.search(r"(?m)^#\s+(.+)$", _no_frontmatter(text))
    return m.group(1).strip() if m else slug


def excerpt(text, limit=EXCERPT):
    """Problem / main result / key claims first (what a source page leads with), whitespace collapsed."""
    body = _body(text)
    i = body.find("**Problem:**")
    body = body[i:] if i > 0 else body
    return re.sub(r"\s+", " ", body).strip()[:limit]


def load_pages(root=None):
    """{slug: {slug, type, depth, title, summary, text, links}} — `links` = outbound ∪ inbound slugs."""
    from kb.core.graph import inbound_index, outbound_links
    from kb.search.semfind import load_pages as _pages
    raw = _pages(root or ROOT)
    inbound = inbound_index(raw)
    out = {}
    for slug, (_rel, fm, text) in raw.items():
        outbound = sorted(s for s in outbound_links(text, fm) if s in raw and s != slug)
        out[slug] = {"slug": slug, "type": str(fm.get("type", "")), "depth": str(fm.get("depth", "")),
                     "title": _title(text, slug), "summary": _unquote(fm.get("summary")), "text": text,
                     "out": outbound, "in": sorted(s for s in inbound.get(slug, ()) if s != slug)}
    return out


def select(pages, include_easy=False, include_people=False):
    """[(slug, easy)] subjects, concept pages and deep sources first, then shallow ones."""
    deep, shallow = [], []
    for slug, p in sorted(pages.items()):
        if p["type"] in CONCEPT_SUBJECTS or p["depth"] in DEEP or (include_people and p["type"] == "person"):
            deep.append((slug, False))
        elif include_easy and p["depth"] in SHALLOW:
            shallow.append((slug, True))
    return deep + shallow


def load_vectors():
    """The card vectors of this kb, or None (missing, unreadable, mixed models). NaN rows are filtered per query."""
    try:
        from kb.search import vectors
        return vectors.load(os.path.join(cache_dir(), "vectors.sqlite"))
    except Exception as e:                                       # missing numpy, sqlite error, mixed models
        print(f"vectors skipped: {e}", file=sys.stderr)
        return None


def neighbours(vecs, slug, k=VECTOR_K):
    if vecs is None:
        return []
    try:
        return [s for s, c in vecs.neighbours(slug, k + 5) if c == c][:k]      # c != c: a NaN vector
    except Exception:
        return []


def concept_neighbours(vecs, slug, pages, types, k=VECTOR_K, pool=60):
    """The k nearest pages of one of `types` by card vector. The plain neighbours of a blog post are other blog
    posts, so a post could never be offered the idea it is about unless it linked it."""
    if vecs is None:
        return []
    try:
        near = [s for s, c in vecs.neighbours(slug, pool) if c == c]
    except Exception:
        return []
    return [s for s in near if s in pages and pages[s]["type"] in types][:k]


def candidates(slug, pages, kinds, vecs=None, cap=MAX_CANDIDATES):
    """Linked pages (outbound, then nearest concepts for `discusses`, then vector neighbours, then inbound) a
    relation of one of `kinds` may reach."""
    p = pages[slug]
    concepts = concept_neighbours(vecs, slug, pages, GATES["discusses"][1]) if "discusses" in kinds else []
    out = []
    for c in [*p["out"], *concepts, *neighbours(vecs, slug), *p["in"]]:
        if c == slug or c in out or c not in pages:
            continue
        if any(gate_ok(k, p["type"], pages[c]["type"]) for k in kinds):
            out.append(c)
        if len(out) >= cap:
            break
    return out


# --- prompt and reply ---------------------------------------------------------------------------------------
def build_prompt(subject, cands, kinds, kc):
    """The request text for one subject; `subject` and `cands` are page dicts."""
    kind_lines = "\n".join(f"- {k}: the subject {MEANING.get(k, k.replace('-', ' ') + ' the target')}" for k in kinds)
    cand_lines = "\n".join(
        f"{i}. {c['slug']} ({c['type']}) — {c['title']}: {(c['summary'] or '')[:200]}" for i, c in enumerate(cands, 1))
    needs_note = ", ".join(sorted(kc["note_required"] & set(kinds))) or "none"
    return f"""You propose typed relations FROM one page of a research wiki TO pages in a numbered candidate list.

SUBJECT: {subject['slug']} ({subject['type']}) — {subject['title']}
Summary: {subject['summary']}
Excerpt: {excerpt(subject['text'])}

CANDIDATES:
{cand_lines}

ALLOWED KINDS (the subject is the source of every relation):
{kind_lines}

RULES:
- Propose a relation only when the subject's text clearly supports it; when unsure, leave it out.
- `to` must be a candidate slug exactly as listed; never invent a slug and never use the subject itself.
- Kinds that need a note ({needs_note}): one sentence naming the conflicting claims. Other notes are optional.
- confidence is 0..1; evidence is a short quote or paraphrase from the subject that supports the relation.
- Return [] when nothing qualifies.

Reply with ONLY a JSON list, no prose:
[{{"to": "<slug>", "kind": "<kind>", "note": "", "confidence": 0.0, "evidence": ""}}]"""


def parse_reply(text):
    """(list of dicts, "") or (None, reason). Accepts a bare list, fenced JSON or {"proposals": [...]}."""
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    for cand in (t, t[t.find("["):t.rfind("]") + 1] if "[" in t else ""):
        if not cand:
            continue
        try:
            v = json.loads(cand)
        except ValueError:
            continue
        if isinstance(v, dict) and isinstance(v.get("proposals"), list):
            v = v["proposals"]
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)], ""
    return None, "reply is not a JSON list"


def _pair(kind, a, b, kc):
    return tuple(sorted((a, b))) if kind in kc["symmetric"] else (a, b)


def validate(subject, items, cand_slugs, pages, kc, kinds=None, keep_above=KEEP_ABOVE):
    """(accepted, rejected): accepted are {from, to, kind, note, confidence, evidence}; rejected keep the proposal
    and a `reason`. Symmetric kinds are stored once with the slugs in sorted order."""
    kinds = set(kinds or kc["kinds"])
    accepted, rejected, seen = [], [], set()
    for item in items:
        to = item.get("to")
        if to not in cand_slugs and (isinstance(to, int) or (isinstance(to, str) and to.strip().isdigit())):
            # a bare number that is not itself a candidate slug → the Nth listed candidate
            n = int(to)
            to = cand_slugs[n - 1] if 1 <= n <= len(cand_slugs) else str(to)
        to = str(to or "").strip().strip("[]").strip()
        kind = str(item.get("kind") or "").strip().lower()
        note = str(item.get("note") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        try:
            conf = float(item.get("confidence"))
        except (TypeError, ValueError):
            conf = None
        reason = ""
        if to == subject:
            reason = "self-relation"
        elif to not in cand_slugs:
            reason = f"`{to}` is not a candidate"
        elif kind not in kinds:
            reason = f"kind `{kind}` is not allowed here"
        elif not gate_ok(kind, pages[subject]["type"], pages[to]["type"]):
            reason = f"{kind} does not join {pages[subject]['type']} → {pages[to]['type']}"
        elif kind in kc["note_required"] and not note:
            reason = f"{kind} needs a note"
        elif conf is None or not 0 <= conf <= 1:
            reason = "confidence missing or outside 0..1"
        elif conf < keep_above:
            reason = f"confidence {conf} < {keep_above}"
        row = {"from": subject, "to": to, "kind": kind, "note": note, "confidence": conf, "evidence": evidence}
        if not reason:
            a, b = _pair(kind, subject, to, kc)
            if (a, b, kind) in seen:
                reason = "duplicate"
            else:
                seen.add((a, b, kind))
                row["from"], row["to"] = a, b
        (rejected if reason else accepted).append({**row, "reason": reason} if reason else row)
    return accepted, rejected


# --- requests -----------------------------------------------------------------------------------------------
def request_id(slug):
    """custom_id ≤ 64 chars: a hash of the slug (thesis slugs run longer than that)."""
    return "s" + hashlib.sha1(slug.encode("utf-8")).hexdigest()[:20]


def plan(pages, subjects, kc, model=MODEL, vecs=None, only_kinds=None):
    """[(slug, llm.Request, info)] for subjects with at least one allowed kind and one candidate.
    `only_kinds` limits what is asked (a cheap run for one new kind)."""
    from kb import llm
    out = []
    for slug, easy in subjects:
        p = pages[slug]
        kinds = kinds_for(p["type"], kc, easy)
        if p["type"] == "person":
            kinds = [k for k in kinds if k == "student-of" or k not in GATES]
        if only_kinds:
            kinds = [k for k in kinds if k in only_kinds]
        cands = candidates(slug, pages, kinds, vecs) if kinds else []
        if not cands:
            continue
        m = EASY_MODEL if easy else model
        req = llm.Request(build_prompt(p, [pages[c] for c in cands], kinds, kc), id=request_id(slug), model=m,
                          max_tokens=MAX_TOKENS, effort="low")
        out.append((slug, req, {"kinds": kinds, "candidates": cands, "easy": easy, "model": m}))
    return out


def estimate_usd(reqs, batch=True, out_tokens=OUT_TOKENS):
    """Price each request by its own model: input at ~3.5 chars a token, a fixed reply size each."""
    from kb import llm
    return sum(llm.cost(r.model, {"input_tokens": len(r.prompt) / 3.5, "output_tokens": out_tokens}, batch=batch)
               for r in reqs)


def resolve_backend(given):
    from kb import llm
    b = (given or os.environ.get(llm.ENV_BACKEND) or DEFAULT_BACKEND).strip().lower()
    return llm.resolve_backend(b)


# --- results → proposals ------------------------------------------------------------------------------------
def _ingest(state, result, pages, kc):
    """Validate one Result into its subject's state entry; → True when it parsed."""
    slug = next((s for s, t in state["subjects"].items() if t["id"] == result.id), None)
    if slug is None:
        return False
    t = state["subjects"][slug]
    t["usd"] = round(result.usd, 5)
    state["spent"] = round(state["spent"] + result.usd, 5)
    if not result.text:
        t["status"], t["note"] = "failed", result.error or "empty reply"
        return False
    items, why = parse_reply(result.text)
    if items is None:
        t["status"], t["note"], t["proposals"] = "rejected", why, []
        t["rejected"] = [{"reply": result.text[:500], "reason": why}]
        return False
    if slug not in pages:
        t["status"], t["note"], t["proposals"], t["rejected"] = "failed", "subject page is gone", [], []
        return False
    acc, rej = validate(slug, items, t["candidates"], pages, kc, t["kinds"], state.get("keep_above", KEEP_ABOVE))
    stamp = {"origin": "llm", "model": result.model or t["model"], "run": state["run"], "at": _now()}
    for row in acc:
        row.update(stamp)
        if t.get("easy"):
            row["tier"] = "low"
    t["status"], t["note"], t["proposals"], t["rejected"] = "done", result.error, acc, rej
    return True


def _legacy_low(state, kc):
    """Rows an older run rejected ONLY for low confidence (reason `confidence x < 0.5`), shaped like accepted ones.
    A run that recorded `keep_above` cut those rows on purpose at creation, so it promotes nothing."""
    out = []
    if "keep_above" in state:
        return out
    for slug, t in state["subjects"].items():
        for r in t.get("rejected") or []:
            if not str(r.get("reason", "")).startswith("confidence ") or "missing" in str(r.get("reason")):
                continue
            row = {k: r.get(k, "") for k in ("from", "to", "kind", "note", "confidence", "evidence")}
            row["from"], row["to"] = _pair(row["kind"], row["from"], row["to"], kc)
            row.update({"origin": "llm", "model": t.get("model", ""), "run": state["run"], "at": r.get("at") or _now()})
            if t.get("easy"):
                row["tier"] = "low"
            out.append(row)
    return out


def run_rows(state):
    """This run's rows, deduped across subjects on (from, to, kind): accepted ones first, then low-confidence rows an
    older run kept only in its `rejected` bucket (so a rewrite of the file never loses them)."""
    rows, seen = [], set()
    legacy = _legacy_low(state, kind_config())
    for r in [r for t in state["subjects"].values() for r in t.get("proposals") or []] + legacy:
        key = (r["from"], r["to"], r["kind"])
        if key not in seen:
            seen.add(key)
            rows.append(r)
    return rows


def write_proposals(state):
    """Rewrite `.cache/relations-proposals.jsonl`: other runs' rows kept, this run's replaced."""
    path = os.path.join(cache_dir(), OUT_FILE)
    keep = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("run") != state["run"]:
                        keep.append(row)
    rows = keep + run_rows(state)
    _write_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return len(rows) - len(keep)


# --- commands -----------------------------------------------------------------------------------------------
def cmd_submit(a):
    from kb import llm
    backend = resolve_backend(a.backend)
    kc = kind_config()
    pages = load_pages()
    state = _load(a.run)
    state["keep_above"] = getattr(a, "keep_above", KEEP_ABOVE)
    collected = {b["id"] for b in state["batches"] if b["collected"]}

    def resend(t):          # --retry: failed / rejected, or still "submitted" although its batch was collected
        return a.retry and (t["status"] in ("failed", "rejected")
                            or (t["status"] == "submitted" and t.get("batch") in collected))
    subjects = [(s, e) for s, e in select(pages, a.include_easy, a.include_people)
                if s not in state["subjects"] or resend(state["subjects"][s])]
    types = {t for t in (getattr(a, "types", None) or "").split(",") if t}
    only_kinds = {k for k in (getattr(a, "kinds", None) or "").split(",") if k}
    unknown = only_kinds - set(kc["kinds"])
    if unknown:
        print(f"error: kinds this kb does not declare: {', '.join(sorted(unknown))} (declared: {', '.join(kc['kinds'])})", file=sys.stderr)
        return 2
    if types:
        subjects = [(s, e) for s, e in subjects if pages[s]["type"] in types]
    subjects = subjects[:a.limit] if a.limit else subjects
    planned = plan(pages, subjects, kc, a.model, load_vectors(), only_kinds or None)
    reqs = [r for _, r, _ in planned]
    batch = backend == "batch"
    est, worst = estimate_usd(reqs, batch), estimate_usd(reqs, batch, MAX_TOKENS)
    n_cands = sum(len(i["candidates"]) for _, _, i in planned)
    print(f"{len(subjects)} subjects, {len(reqs)} requests ({len(subjects) - len(reqs)} without candidates), "
          f"{n_cands} candidates; estimate ${est:.2f} on {a.model}"
          f"{' (+haiku for easy pages)' if a.include_easy else ''} via {backend}"
          f"{' (API-equivalent; subscription is not billed per call)' if backend == 'subscription' else ''}; "
          f"worst case ${worst:.2f} if every reply hit {MAX_TOKENS} tokens")
    if state["spent"] + est > a.max_usd:
        print(f"refused: ${state['spent'] + est:.2f} would pass --max-usd {a.max_usd}", file=sys.stderr)
        return 2
    if a.dry_run or not reqs:
        return 0
    state["backend"], state["model"] = backend, a.model
    info = {r.id: (slug, i) for slug, r, i in planned}

    def register(chunk, bid):
        for r in chunk:
            slug, i = info[r.id]
            state["subjects"][slug] = {"id": r.id, "status": "submitted", "usd": 0.0, "note": "", "batch": bid,
                                       "model": i["model"], "easy": i["easy"], "kinds": i["kinds"],
                                       "candidates": i["candidates"]}

    if batch:
        for k in range(0, len(reqs), CHUNK):
            chunk = reqs[k:k + CHUNK]
            bid = llm.submit(chunk)
            register(chunk, bid)
            state["batches"].append({"id": bid, "ids": [r.id for r in chunk], "collected": False})
            _save(state)
            _log(state, event="submitted", batch=bid, n=len(chunk))
            print(f"batch {bid}: {len(chunk)} requests (collect with: collect --run {a.run})")
        return 0
    done = 0
    for k in range(0, len(reqs), DIRECT_CHUNK):               # api / subscription: run now, save as we go
        chunk = reqs[k:k + DIRECT_CHUNK]
        bid = f"{backend}-{_now()}-{k}"
        register(chunk, bid)
        try:
            results = llm.run(chunk, backend=backend)
        except Exception as e:                                # keep what earlier chunks got; this one is retryable
            for r in chunk:
                t = state["subjects"][info[r.id][0]]
                t["status"], t["note"] = "failed", f"{type(e).__name__}: {e}"[:300]
            state["batches"].append({"id": bid, "ids": [r.id for r in chunk], "collected": True})
            _save(state)
            _log(state, event="failed", backend=backend, n=len(chunk), error=str(e)[:300])
            print(f"stopped: {e} (re-run with --retry)", file=sys.stderr)
            write_proposals(state)
            return 1
        for res in results:
            done += _ingest(state, res, pages, kc)
        state["batches"].append({"id": bid, "ids": [r.id for r in chunk], "collected": True})
        _save(state)
        _log(state, event="ran", backend=backend, n=len(chunk))
    n = write_proposals(state)
    print(f"{done} subjects answered; {n} proposals in .cache/{OUT_FILE}; spent ${state['spent']:.2f}")
    return 0


def cmd_collect(a):
    from kb import llm
    state = _load(a.run)
    if not state["batches"]:
        print(f"run {a.run}: nothing submitted")
        return 1
    kc, pages = kind_config(), load_pages()
    for b in state["batches"]:
        if b["collected"]:
            continue
        results = llm.collect(b["id"], wait_s=a.wait)
        if results and all("collect it later" in (r.error or "") for r in results):
            print(f"batch {b['id']}: not ended yet (collect again later)")
            continue
        ok = sum(_ingest(state, r, pages, kc) for r in results)
        b["collected"] = True
        _save(state)
        _log(state, event="collected", batch=b["id"], ok=ok, n=len(results))
        print(f"batch {b['id']}: {ok}/{len(results)} replies parsed; spent ${state['spent']:.2f}")
    n = write_proposals(state)
    print(f"{n} proposals from run {a.run} in .cache/{OUT_FILE}")
    return 0


def review_text(state, pages, min_conf=MIN_CONFIDENCE):
    """A per-subject markdown digest of the run's proposals (best first) and a count of the rejected ones."""
    title = lambda s: pages[s]["title"] if s in pages else s               # noqa: E731
    lines = [f"# Relation proposals — run {state['run']}", ""]
    total = 0
    for slug, t in sorted(state["subjects"].items(), key=lambda kv: title(kv[0]).lower()):
        props = sorted((r for r in t.get("proposals") or [] if r["confidence"] >= min_conf),
                       key=lambda r: -r["confidence"])
        if not props:
            continue
        total += len(props)
        lines += [f"## {title(slug)} (`{slug}`)", ""]
        for r in props:
            other = r["to"] if r["from"] == slug else r["from"]
            arrow = "↔" if r["kind"] in SYMMETRIC else "→"
            low = " · low tier" if r.get("tier") == "low" else ""
            lines.append(f"- **{r['kind']}** {arrow} {title(other)} (`{other}`) · confidence {r['confidence']:.2f}{low}")
            if r.get("note"):
                lines.append(f"  - note: {r['note']}")
            if r.get("evidence"):
                lines.append(f"  - evidence: {r['evidence']}")
        n_rej = len(t.get("rejected") or [])
        if n_rej:
            lines.append(f"- _{n_rej} rejected_ (see `.cache/relations-propose/{state['run']}/state.json`)")
        lines.append("")
    rejected = sum(len(t.get("rejected") or []) for t in state["subjects"].values())
    lines.insert(2, f"{total} proposals at confidence ≥ {min_conf} over "
                    f"{sum(1 for t in state['subjects'].values() if t['status'] == 'done')} answered subjects; "
                    f"{rejected} rejected.\n")
    return "\n".join(lines)


def cmd_review(a):
    state = _load(a.run)
    if not state["subjects"]:
        print(f"run {a.run}: nothing submitted")
        return 1
    print(review_text(state, load_pages(), a.min_confidence))
    return 0


def plan_apply(rows, pages, config, min_conf, kinds=None, subjects=None, limit=None):
    """Which proposals to write as stated relations: ({slug: [new {to, kind, note}]}, [(row, why skipped)]).

    A row is taken when it meets `min_conf` (and `kinds` / `subjects` when given) and passes the same check lint runs
    on a stated relation (kind declared in kb.toml [edges], target exists and is another page, a note where the kind
    needs one). A relation the page already states is skipped, and so is a symmetric one the other page states.
    `limit` caps how many pages are touched. Best confidence first, so a cap keeps the strongest."""
    from kb.graph import relations as R
    symmetric = set(config.get("symmetric") or ())
    stated = {slug: R.parse_relations(p["text"]) for slug, p in pages.items()}

    def has(a, b, kind):
        return any(r["to"] == b and r["kind"] == kind for r in stated.get(a, ()))

    out, skipped = {}, []
    for r in sorted(rows, key=lambda r: (-r["confidence"], r["from"], r["to"], r["kind"])):
        if r["confidence"] < min_conf or (kinds and r["kind"] not in kinds) or (subjects and r["from"] not in subjects):
            continue
        rel = {"to": r["to"], "kind": R.kind_name(r["kind"]), "note": (r.get("note") or "").strip()}
        why = R._check(r["from"], rel, pages, config)
        if why:
            skipped.append((r, why.split(": ", 1)[1]))
            continue
        a, b = r["from"], r["to"]
        if has(a, b, rel["kind"]) or (rel["kind"] in symmetric and has(b, a, rel["kind"])):
            skipped.append((r, "already stated"))
            continue
        if limit and a not in out and len(out) >= limit:
            continue
        out.setdefault(a, []).append(rel)
        stated.setdefault(a, []).append(rel)
    return out, skipped


def cmd_apply(a):
    """Write the chosen proposals into the pages' `relations:` blocks (dry run unless --write)."""
    from kb.graph import relations as R
    from kb.services.cypher import edge_config
    path = os.path.join(cache_dir(), OUT_FILE)
    if not os.path.isfile(path):
        print(f"no proposals file ({path}) — run submit and collect first")
        return 1
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if a.run:
        rows = [r for r in rows if r.get("run") == a.run]
    pages = load_pages()
    kinds = set(a.kinds.split(",")) if a.kinds else None
    subjects = set(a.subjects.split(",")) if a.subjects else None
    plan, skipped = plan_apply(rows, pages, edge_config(), a.min_confidence, kinds, subjects, a.limit)
    n = sum(len(v) for v in plan.values())
    print(f"{n} relation(s) on {len(plan)} page(s) at confidence >= {a.min_confidence}; {len(skipped)} skipped")
    for slug, rels in sorted(plan.items()):
        for r in rels:
            print(f"  {slug} --{r['kind']}--> {r['to']}" + (f"  ({r['note'][:70]})" if r["note"] else ""))
    for r, why in skipped[:10]:
        print(f"  skipped {r['from']} --{r['kind']}--> {r['to']}: {why}")
    if not a.write:
        print("dry run: nothing written (add --write inside `ops begin refine …` / `ops commit`)")
        return 0
    for slug, rels in sorted(plan.items()):
        file = os.path.join(ROOT, "wiki", f"{slug}.md")
        with open(file, encoding="utf-8") as f:
            text = f.read()
        with open(file, "w", encoding="utf-8") as f:
            f.write(R.set_relations(text, R.parse_relations(text) + rels))
    print(f"wrote {n} relation(s) on {len(plan)} page(s)")
    return 0


def cmd_repack(a):
    """Rewrite the proposals file from a run's saved state (no LLM): picks up rows an older run kept only as rejected."""
    state = _load(a.run)
    if not state["subjects"]:
        print(f"run {a.run}: nothing submitted")
        return 1
    n = write_proposals(state)
    print(f"run {a.run}: {n} proposal row(s) in {OUT_FILE}")
    return 0


def cmd_status(a):
    base = os.path.join(cache_dir(), "relations-propose")
    runs = [a.run] if a.run else sorted(os.listdir(base)) if os.path.isdir(base) else []
    if not runs:
        print("no runs")
    for run in runs:
        state = _load(run)
        counts = {}
        for t in state["subjects"].values():
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        print(f"run {run}: {counts}  proposals {len(run_rows(state))}  spent ${state['spent']:.2f}  "
              f"batches {len(state['batches'])} ({sum(1 for b in state['batches'] if not b['collected'])} open)")
        if a.run:
            for slug, t in state["subjects"].items():
                if t["status"] in ("failed", "rejected"):
                    print(f"  {t['status']}: {slug}: {(t['note'] or '')[:120]}")
    return 0


def run(argv=None):
    ap = argparse.ArgumentParser(prog="kb.graph.propose", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="one relation request per subject page (LLM; batch by default)")
    s.add_argument("--run", required=True)
    s.add_argument("--backend", choices=("batch", "api", "subscription"),
                   help=f"default: $KB_LLM_BACKEND, then {DEFAULT_BACKEND}")
    s.add_argument("--model", default=MODEL)
    s.add_argument("--include-easy", action="store_true",
                   help=f"also easy/listed pages ({EASY_MODEL}; example-of/addresses/open-problem-in only, tier low)")
    s.add_argument("--include-people", action="store_true", help="also person pages (student-of only)")
    s.add_argument("--limit", type=int)
    s.add_argument("--kinds", help="ask only these relation kinds, comma-separated (a cheap run for one new kind)")
    s.add_argument("--types", help="only subject pages of these types, comma-separated (e.g. blog-post)")
    s.add_argument("--keep-above", type=float, default=KEEP_ABOVE,
                   help="drop proposals below this confidence when the reply is read (default 0: keep all)")
    s.add_argument("--max-usd", type=float, default=6.0, help="refuse a run whose estimate passes this")
    s.add_argument("--dry-run", action="store_true", help="count and estimate, send and write nothing")
    s.add_argument("--retry", action="store_true", help="resend subjects that failed or were rejected")
    c = sub.add_parser("collect", help="wait for the batches, validate, write the proposals file")
    c.add_argument("--run", required=True)
    c.add_argument("--wait", type=int, default=24 * 3600, help="seconds to wait per batch")
    r = sub.add_parser("review", help="per-subject markdown digest of a run's proposals")
    r.add_argument("--run", required=True)
    r.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    rp = sub.add_parser("repack", help="rewrite the proposals file from a run's saved state (no LLM)")
    rp.add_argument("--run", required=True)
    st = sub.add_parser("status")
    st.add_argument("--run")
    ap_ = sub.add_parser("apply", help="write chosen proposals into pages as stated relations (dry run unless --write)")
    ap_.add_argument("--min-confidence", type=float, required=True, help="no default: you choose what counts as accepted")
    ap_.add_argument("--run", help="only this run's rows (default: every run in the proposals file)")
    ap_.add_argument("--kinds", help="comma-separated relation kinds to take")
    ap_.add_argument("--subjects", help="comma-separated page slugs to take proposals for")
    ap_.add_argument("--limit", type=int, help="touch at most this many pages (strongest first)")
    ap_.add_argument("--write", action="store_true", help="edit the pages; wrap in `ops begin refine` / `ops commit`")
    a = ap.parse_args(argv)
    return {"submit": cmd_submit, "collect": cmd_collect, "review": cmd_review, "status": cmd_status, "repack": cmd_repack,
            "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(run())

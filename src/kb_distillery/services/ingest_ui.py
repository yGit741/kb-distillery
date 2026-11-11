"""Ingest from the app: drop a file or paste a URL, say how deeply to read it, and get a proposal instead of a page.

HTTP-free (`kb_distillery.server.routers.ingest_ui` relays `IngestError(status, message)`). One job per source, run in a
background thread of the server process:

  fetch     a URL is downloaded (an upload skips this step)
  convert   the bytes are saved under raw/ and catalogued through `inbox_add` (one `kb(catalog)` step, as the inbox
            endpoint does) and their text is extracted
  digest    one LLM call through `kb_distillery.llm` (the request's `backend`) fills the claims the full digest fills;
            the `listed` tier makes no call
  propose   the would-be pages become ONE proposal (`proposals.service.create`, producer kind `ingest`): a create_page
            op for the source page and for each new concept, an edit_page op for a page that already exists

Each job's public record is kept as small JSON under `<kb>/.local/ingest/<id>.json` (kb-local state, never committed),
so the list survives a restart; a record still "running" that no thread of this process owns is shown as "interrupted".

Nothing here writes `wiki/`; the owner reviews the proposal. The one exception is catalog's own bookkeeping, unchanged:
a paper PDF still gets its depth-listed stub, and a `collection` that is a course or series gets its Contents row.
When the stub is there, the proposal edits it rather than creating a second page.

  start_file(name, data, ...)  validates, returns {job_id}      start_url(url, ...)  same, for a URL
  get(job_id)                  {status, steps, proposal_id?, error?}
  listing(root)                the jobs newest first (the last 200), each with its proposal's live status
  events(job_id)               (event, data) pairs for `server.sse`: `job` on every change, `end` when it stops
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import socket
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from kb_distillery import llm
from kb_distillery.config import net
from kb_distillery.config.paths import vault_root
from kb_distillery.ingest import digest_many, extract
from kb_distillery.ingest import scrap
from kb_distillery.proposals import service as proposals
from kb_distillery.proposals.model import ProposalError
from kb_distillery.services import inbox_add
from kb_distillery.vault import frontmatter, links
from kb_distillery.vault.schema import DEPTH, LOCAL_DIR, unit_slug_for_raw, unit_type_for_raw

DEFAULT_ROOT = vault_root()
TIERS = DEPTH                                   # listed | easy | full | deep
DEFAULT_TIER = "full"
MODEL_TIER = {"easy": "light", "full": "standard", "deep": "strong"}
TEXT_CHARS = {"easy": 12_000, "full": digest_many.MAX_TEXT, "deep": 100_000}
UPLOAD_EXTS = frozenset({".pdf", ".md", ".markdown", ".txt", ".html", ".htm"})
MAX_NEW_CONCEPTS = 4
POLL = 0.4
PING_EVERY = 25
STEPS = ("fetch", "convert", "digest", "propose")
LOCAL_SUBDIR = "ingest"
KEEP = 200
_ID = re.compile(r"^[0-9a-f]{8}$")
_SLUG = re.compile(r"[^a-z0-9]+")
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


class IngestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# --- validation ------------------------------------------------------------------------------------------------
def _clean_tier(tier):
    tier = (tier or DEFAULT_TIER).strip().lower()
    if tier not in TIERS:
        raise IngestError(422, f"tier must be one of {', '.join(TIERS)}")
    return tier


def _clean_collection(collection, root):
    collection = (collection or "").strip()
    if not collection:
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", collection):
        raise IngestError(422, f"{collection!r} is not a page slug")
    if not os.path.isfile(os.path.join(root, "wiki", collection + ".md")):
        raise IngestError(422, f"there is no collection page {collection!r}")
    return collection


def _clean_year(year):
    """The year the owner typed for a paper whose file name carries none; None when the field was left empty."""
    if year is None or str(year).strip() == "":
        return None
    try:
        y = int(str(year).strip())
    except ValueError:
        y = 0
    if not 1800 <= y <= 2099:
        raise IngestError(422, "the year must be four digits, such as 2024")
    return y


def check_url(url) -> str:
    """The URL, or IngestError(422): http(s) only, a real host, no credentials, nothing on this machine or its network."""
    url = (url or "").strip() if isinstance(url, str) else ""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise IngestError(422, "paste a web address that starts with http:// or https://")
    if p.username or p.password:
        raise IngestError(422, "the address must not carry a user name or password")
    host = p.hostname.lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if (ip and _private(ip)) or \
            host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")) or "." not in host and not ip:
        raise IngestError(422, "that address points at this machine or its network; paste a public web address")
    return url


def _private(ip):
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified or ip.is_multicast


def _resolve_public(host):
    """Every address `host` resolves to must be public (this also catches short forms such as 127.1, and DNS names
    that point inside); IngestError otherwise."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise IngestError(502, "that address could not be found") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if _private(ip) or (ip.version == 6 and ip.ipv4_mapped and _private(ip.ipv4_mapped)):
            raise IngestError(422, "that address points at this machine or its network; paste a public web address")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


MAX_REDIRECTS = 5


def _download(url):
    """(bytes, Content-Type) of a public URL: each redirect hop is checked again, and the body is capped."""
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=net.ssl_context()), _NoRedirect)
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        _resolve_public(urlparse(url).hostname)
        req = urllib.request.Request(url, headers={"User-Agent": "kb-distillery-ingest/1.0"})
        try:
            resp = opener.open(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urljoin(url, e.headers["Location"])
                continue
            raise
        with resp:
            data = resp.read(inbox_add.MAX_FILE_BYTES + 1)
            if len(data) > inbox_add.MAX_FILE_BYTES:
                raise IngestError(413, f"that address answers with more than {inbox_add.MAX_FILE_BYTES >> 20} MB")
            return data, resp.headers.get("Content-Type", "") or ""
    raise IngestError(502, "that address redirects too many times")


def check_upload(name, data):
    ext = os.path.splitext(name or "")[1].lower()
    if ext not in UPLOAD_EXTS:
        raise IngestError(415, f"{ext or 'that'} files cannot be ingested here: use one of {', '.join(sorted(UPLOAD_EXTS))}")
    if not data:
        raise IngestError(422, "the file is empty")
    if len(data) > inbox_add.MAX_FILE_BYTES:
        raise IngestError(413, f"larger than {inbox_add.MAX_FILE_BYTES >> 20} MB")


# --- job state ---------------------------------------------------------------------------------------------------
def _new_job(source, tier, collection, backend, root, kind):
    job = {"id": secrets.token_hex(4), "status": "running", "source": source, "kind": kind, "tier": tier,
           "collection": collection, "backend": backend or "",
           "steps": [{"name": n, "state": "pending", "detail": ""} for n in STEPS],
           "proposal_id": None, "pages": [], "error": None, "created": time.time(), "finished": None, "root": root}
    with _LOCK:
        _JOBS[job["id"]] = job
    _save(job)
    _prune(job["root"])
    return job


def _prune(root):
    """Keep the newest KEEP record files of this kb (by modification time); older ones are removed."""
    d = _folder(root)
    try:
        files = [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".json") and _ID.fullmatch(n[:-5])]
        if len(files) <= KEEP:
            return
        files.sort(key=os.path.getmtime, reverse=True)
        for f in files[KEEP:]:
            os.remove(f)
    except OSError:
        pass


def _folder(root):
    return os.path.join(root, LOCAL_DIR, LOCAL_SUBDIR)


def _record(job) -> dict:
    with _LOCK:
        return {"id": job["id"], "status": job["status"], "source": job["source"], "kind": job["kind"],
                "tier": job["tier"], "collection": job["collection"], "backend": job["backend"],
                "steps": [dict(s) for s in job["steps"]], "proposal_id": job["proposal_id"], "pages": list(job["pages"]),
                "error": job["error"], "created": job["created"], "finished": job["finished"]}


def _save(job):
    """Write the job's public record atomically; a disk problem never stops the job itself."""
    rec = _record(job)
    d = _folder(job["root"])
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, rec["id"] + ".json"))
    except OSError:
        traceback.print_exc()


def _step(job, name, state, detail=""):
    with _LOCK:
        for s in job["steps"]:
            if s["name"] == name:
                s["state"], s["detail"] = state, detail
    _save(job)


def _current_step(rec) -> str:
    """The step the job is on (or stopped at): the active/failed one, else the first pending, else the last."""
    steps = rec["steps"]
    for want in ("active", "failed"):
        for s in steps:
            if s["state"] == want:
                return s["name"]
    for s in steps:
        if s["state"] == "pending":
            return s["name"]
    return steps[-1]["name"]


def _public(job) -> dict:
    rec = _record(job)
    return {k: rec[k] for k in ("id", "status", "source", "tier", "collection", "steps", "proposal_id", "pages", "error")} | \
        {"kind": rec["kind"], "backend": rec["backend"], "started": rec["created"], "finished": rec["finished"], "step": _current_step(rec)}


def _from_disk(root, job_id):
    if not _ID.fullmatch(job_id or ""):
        return None
    try:
        with open(os.path.join(_folder(root), job_id + ".json"), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    need = {"id", "status", "source", "tier", "collection", "steps", "created"}
    if not isinstance(rec, dict) or not need <= rec.keys() or not isinstance(rec["steps"], list) or not rec["steps"] \
            or not all(isinstance(x, dict) and "name" in x and "state" in x for x in rec["steps"]):
        return None                                                 # a record this code did not write: skipped, not fatal
    for k, v in (("backend", ""), ("pages", []), ("proposal_id", None), ("error", None), ("finished", None)):
        rec.setdefault(k, v)
    if rec.get("status") == "running" and job_id not in _JOBS and not rec.get("demo"):
        # its thread died with the last server process (a demo seed record is a fixture that stays "running")
        rec["status"] = "interrupted"
        rec["error"] = "the server stopped while this was running"
        for s in rec.get("steps", []):
            if s["state"] == "active":
                s["state"], s["detail"] = "failed", rec["error"]
    rec.setdefault("kind", "url" if str(rec.get("source", "")).startswith(("http://", "https://")) else "file")
    rec["root"] = root
    return rec


def get(job_id: str, root=None) -> dict:
    job = _JOBS.get(job_id)
    if job:
        return _public(job)
    rec = _from_disk(root or DEFAULT_ROOT, job_id)
    if not rec:
        raise IngestError(404, f"no ingest job {job_id!r}")
    return _public(rec)


def listing(root=None, limit=KEEP) -> list[dict]:
    """The last `limit` jobs of this kb, newest first. Each carries `proposal_status` (open, stale, applied, rejected,
    undone) and `proposal_updated`, read from the proposals now, or None when the job has no proposal (or it no longer exists)."""
    root = root or DEFAULT_ROOT
    d = _folder(root)
    names = [n[:-5] for n in os.listdir(d) if n.endswith(".json") and _ID.fullmatch(n[:-5])] if os.path.isdir(d) else []
    rows = []
    for n in names:
        job = _JOBS.get(n)
        rec = _public(job) if job and job["root"] == root else None
        if rec is None:
            disk = _from_disk(root, n)
            rec = _public(disk) if disk else None
        if rec:
            rows.append(rec)
    rows.sort(key=lambda r: r["started"], reverse=True)
    rows = rows[:limit]
    live = {}
    if any(r["proposal_id"] for r in rows):
        try:
            live = {p["id"]: p for p in proposals.inbox(None, root)["proposals"]}
        except Exception:                                           # noqa: BLE001 - the status is a courtesy, never fatal
            live = {}
    return [{**r, "proposal_status": live[r["proposal_id"]]["status"] if r["proposal_id"] in live else None,
             "proposal_updated": live[r["proposal_id"]]["updated"] if r["proposal_id"] in live else None} for r in rows]


def events(job_id: str, poll: float = POLL, root=None):
    """`job` whenever the job changes, a ping on a quiet stretch, `end` once it is done or failed."""
    last, quiet = None, 0
    while True:
        try:
            cur = get(job_id, root)
        except IngestError:
            yield "end", {"status": "gone"}
            return
        if cur != last:
            yield "job", cur
            last, quiet = cur, 0
        else:
            quiet += 1
            if quiet % PING_EVERY == 0:
                yield "ping", None
        if cur["status"] != "running":
            yield "end", {"status": cur["status"]}
            return
        time.sleep(poll)


# --- starting ------------------------------------------------------------------------------------------------------
def _prepare(tier, collection, backend, root):
    root = root or DEFAULT_ROOT
    tier = _clean_tier(tier)
    collection = _clean_collection(collection, root)
    if backend and backend not in ("subscription", "api", "batch"):
        raise IngestError(422, "backend must be subscription, api or batch")
    return root, tier, collection


def _spawn(job, work):
    threading.Thread(target=work, name=f"kb-ingest-{job['id']}", daemon=True).start()
    return {"job_id": job["id"]}


def start_file(name, data, tier=None, collection=None, backend=None, root=None, year=None) -> dict:
    root, tier, collection = _prepare(tier, collection, backend, root)
    year = _clean_year(year)
    check_upload(name, data)
    job = _new_job(name or "upload", tier, collection, backend, root, "file")
    return _spawn(job, lambda: _run(job, root, name, data, "", fetch=None, year=year))


def start_url(url, tier=None, collection=None, backend=None, root=None) -> dict:
    root, tier, collection = _prepare(tier, collection, backend, root)
    url = check_url(url)
    job = _new_job(url, tier, collection, backend, root, "url")
    return _spawn(job, lambda: _run(job, root, None, None, url, fetch=_fetch))


# --- the job -----------------------------------------------------------------------------------------------------------
def _fetch(url):
    """(name, bytes) of a URL; IngestError when the answer is not a document this screen takes."""
    try:
        data, ctype = _download(url)
    except IngestError:
        raise
    except Exception as e:                                      # noqa: BLE001 - urllib raises many kinds
        raise IngestError(502, f"could not fetch that address ({e.__class__.__name__}: {e})") from None
    ctype = (ctype or "").lower()
    stem = scrap.web_clip_name(url).rsplit(".", 1)[0]
    if scrap.is_pdf(data, ctype):
        return stem + ".pdf", data
    if "html" in ctype or data[:512].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return stem + ".html", data
    if "markdown" in ctype or "text/plain" in ctype or urlparse(url).path.lower().endswith((".md", ".txt")):
        return stem + ".md", data
    raise IngestError(415, f"that address answers with {ctype or 'an unknown type'}, not a PDF, web page or text")


def _fail(job, message):
    with _LOCK:
        for s in job["steps"]:
            if s["state"] == "active":
                s["state"], s["detail"] = "failed", message
        job["status"], job["error"], job["finished"] = "failed", message, time.time()
    _save(job)


def _run(job, root, name, data, url, fetch, year=None):
    try:
        if fetch:
            _step(job, "fetch", "active", url)
            name, data = fetch(url)
            _step(job, "fetch", "done", f"{name} ({len(data) // 1024 or 1} KB)")
        else:
            _step(job, "fetch", "skipped", "uploaded from this machine")
        raw_rel, text = _convert(job, root, name, data, year)
        claims = _digest(job, root, raw_rel, text, url)
        _propose(job, root, raw_rel, claims, url)
    except IngestError as e:
        _fail(job, e.message)
    except ProposalError as e:
        _fail(job, str(e))
    except Exception as e:                                      # noqa: BLE001 - a thread must never die silently
        traceback.print_exc()
        _fail(job, f"something went wrong ({e.__class__.__name__}: {e}); nothing was changed in the wiki")


def _convert(job, root, name, data, year=None):
    _step(job, "convert", "active", "saving the source")
    name = _as_catalog_name(name)
    try:
        res = inbox_add.add_files([(name, data)], root=root, collection=job["collection"], year=year)
    except inbox_add.SourceError as e:
        raise IngestError(e.status, e.message) from None
    f = res["files"][0]
    if f["status"] == "duplicate":
        raise IngestError(409, "this source is already in the knowledge base")
    if f["status"] == "refused":
        raise IngestError(415, f.get("reason") or "this file was refused")
    raw_rel = f.get("raw_path") or ""
    if not raw_rel or raw_rel.startswith("raw/inbox/"):
        raise IngestError(409, f.get("reason") or "the source was stored but could not be filed yet")
    _step(job, "convert", "active", "reading the text")
    text = extract.extract_text(os.path.join(root, raw_rel)) or ""
    if not text.strip():
        raise IngestError(422, "no text could be read from this source (a scanned PDF needs a text layer)")
    _step(job, "convert", "done", f"{raw_rel} ({len(text) // 1000 or 1}k characters)")
    return raw_rel, text


def _as_catalog_name(name):
    base, ext = os.path.splitext(os.path.basename(name or "source"))
    return base + {".txt": ".md", ".markdown": ".md", ".htm": ".html"}.get(ext.lower(), ext.lower())


def _template(raw_rel):
    year = os.path.basename(raw_rel)[:4]
    return {"raw": raw_rel, "title": "", "problem": "", "method": "", "results": [], "equations": [],
            "concepts": [], "open_questions": [], "citekey": "", "url": "",
            "year": int(year) if year.isdigit() else None, "authors": []}


def _digest(job, root, raw_rel, text, url):
    if job["tier"] == "listed":
        _step(job, "digest", "skipped", "listed only: the source is filed, not read")
        return None
    backend = job["backend"] or None
    _step(job, "digest", "active", f"reading with the {backend or 'default'} backend")
    template = _template(raw_rel)
    prompt = extract.fill_prompt(template, text[:TEXT_CHARS[job["tier"]]])
    r = llm.ask(prompt, backend=backend, model=MODEL_TIER[job["tier"]], effort=extract.FILL_EFFORT,
                max_tokens=extract.FILL_MAX_TOKENS)
    if not r.ok and not r.text:
        raise IngestError(502, f"the model could not be reached ({r.error}); the source is already filed under raw/, digest it from the Pipeline screen")
    claims, reason = extract.claims_from_result(r, template)
    if reason:
        raise IngestError(422, f"the model's reply could not be used ({reason}); the source is already filed under raw/, digest it from the Pipeline screen")
    if url and not claims.get("url"):
        claims["url"] = url
    _step(job, "digest", "done", f"{len(claims.get('results') or [])} result(s), {len(claims.get('concepts') or [])} concept(s)")
    return claims


# --- the proposal --------------------------------------------------------------------------------------------------------
def _kebab(s):
    return _SLUG.sub("-", str(s).lower()).strip("-")[:80]


def _yaml_list(items):
    return "[" + ", ".join(str(i) for i in items) + "]"


def source_page(slug, page_type, raw_rel, tier, claims, concept_links, title, url, area=()):
    """The text of the new source page. `claims` is None for the listed tier (a stub, as catalog writes it)."""
    title_yaml = frontmatter.title_line(title)
    title_yaml = title_yaml + "\n" if title_yaml else ""
    paper = page_type == "paper"
    head = f"type: {page_type}\nlayer: source\n{title_yaml}"
    if paper:
        authors = (claims or {}).get("authors") or []
        head += f"authors: {_yaml_list(authors)}\nyear: {(claims or {}).get('year') or ''}\n"
    maturity = "digested" if claims else "to-read"
    draft = "" if claims else "status: draft\n"
    tail = f"citekey: {(claims or {}).get('citekey') or ''}\n" if paper else ""
    fm = (f"---\n{head}area: {_yaml_list(area)}\nmaturity: {maturity}\n{draft}depth: {tier}\nraw: {raw_rel}\n{tail}"
          f"url: {url}\n---\n")
    if not claims:
        return fm + f"\n# {title}\n\n**Problem:**\n\n**Main result:**\n\n## Links out\n- Concepts: <!-- [Title](slug.md) -->\n"
    results = claims.get("results") or []
    key_claims = "\n".join(f"- {r}" for r in results[1:] or results)
    concepts = ", ".join(concept_links) or "<!-- [Title](slug.md) -->"
    return (fm + f"\n# {title}\n\n**Problem:** {claims.get('problem', '')}\n\n**Main result:** {results[0] if results else ''}\n\n"
            f"## Setup & assumptions\n\n{claims.get('method', '')}\n\n## Key claims\n\n{key_claims}\n\n"
            f"## Links out\n- Concepts: {concepts}\n")


def concept_page(name, title, source_link, line=""):
    return (f"---\ntype: idea\nlayer: concept\narea: []\nmaturity: seed\nsources: []\nrelated: []\ndiscussed_with: []\n"
            f"description:\n---\n\n# {title}\n\n**One-liner:** {line}\n\n## Connections\n- {source_link}\n\n"
            f"## My notes\n\n<!-- Yours: no tool rewrites this section, and it stays last. -->\n")


def add_source_link(text, source_link):
    """`text` with one more bullet under its `## Connections` (made before `## My notes`, or at the end, when missing)."""
    if source_link in text:
        return text
    bullet = f"- {source_link}\n"
    m = re.search(r"^## Connections[^\n]*\n(?:(?!^## ).*\n?)*", text, flags=re.M)
    if m:
        block = m.group(0).rstrip("\n") + "\n"
        return text[:m.start()] + block + bullet + ("\n" if text[m.end():] else "") + text[m.end():].lstrip("\n")
    notes = re.search(r"^## My notes", text, flags=re.M)
    section = f"## Connections\n{bullet}\n"
    if notes:
        return text[:notes.start()] + section + text[notes.start():]
    return text.rstrip("\n") + "\n\n" + section


def build_ops(root, raw_rel, tier, claims, url):
    """([ops], title, [page slugs]) for one ingested source."""
    wiki = os.path.join(root, "wiki")
    titles = links.read_titles(wiki) if os.path.isdir(wiki) else {}
    page_type = unit_type_for_raw(raw_rel)
    slug = unit_slug_for_raw(raw_rel, page_type)
    title = links.shown_title((claims or {}).get("title") or "") or \
        re.sub(r"^(1[89]|20)\d{2}-", "", os.path.splitext(os.path.basename(raw_rel))[0]).replace("-", " ").strip().title()
    source_link = links.page_link(slug, {slug: title})
    ops, concept_links, seen, new = [], [], {slug}, 0
    for c in ((claims or {}).get("concepts") or []):
        cslug = _kebab(c)
        if not cslug or cslug in seen:
            continue
        seen.add(cslug)
        path = os.path.join(wiki, cslug + ".md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                old = f.read()
            new_text = add_source_link(old, source_link)
            concept_links.append(links.page_link(cslug, titles))
            if new_text != old:
                ops.append({"kind": "edit_page", "slug": cslug, "new_text": new_text,
                            "reason": f"the new source {title} is about this idea"})
        elif new < MAX_NEW_CONCEPTS:
            new += 1
            nice = links.shown_title(str(c)).strip().capitalize() or cslug
            concept_links.append(links.link(cslug, nice))
            ops.append({"kind": "create_page", "slug": cslug, "text": concept_page(cslug, nice, source_link),
                        "reason": f"a new idea named in {title}"})
    text = source_page(slug, page_type, raw_rel, tier, claims, concept_links, title, url or (claims or {}).get("url") or "")
    existing = os.path.join(wiki, slug + ".md")
    if os.path.isfile(existing):                                # catalog's depth-listed stub: fill it in
        ops.insert(0, {"kind": "edit_page", "slug": slug, "new_text": text, "reason": "digest of the new source"})
    else:
        ops.insert(0, {"kind": "create_page", "slug": slug, "text": text, "reason": "digest of the new source"})
    return ops, title, [o["slug"] for o in ops]


def _propose(job, root, raw_rel, claims, url):
    _step(job, "propose", "active", "preparing the pages for your review")
    ops, title, slugs = build_ops(root, raw_rel, job["tier"], claims, url)
    p = proposals.create(f"Ingest: {title}", ops, root=root, note=f"tier {job['tier']}",
                         producer={"kind": "ingest", "instruction": f"ingest {job['source']}",
                                   "context": {"source": raw_rel, "tier": job["tier"], "collection": job["collection"]}})
    _step(job, "propose", "done", f"{len(slugs)} page{'s' if len(slugs) != 1 else ''}")
    with _LOCK:
        job["proposal_id"], job["pages"], job["status"], job["finished"] = p["id"], slugs, "done", time.time()
    _save(job)

"""Send one think note into several knowledge bases, with provenance on both sides (docs: think.md).

    distill_note("thesis-decision", [("thesis", "/…/kbs/thesis"), ("demo", "/…/examples/demo")])

* kb side: `wiki/distilled-think-<note>.md` (type `distilled-think`) whose `sources:` cite `think:<note>.md`.
* think side: `<think>/.provenance/<note>.json` lists where the note went. The note itself is never edited;
  this function is the only writer of that sidecar, and the `kbd distill` command is its only caller.

Nothing here imports `kb_distillery.paths` (which needs a selected kb): the think space and every kb root are arguments, so
one process can write into two kbs. No LLM call is made unless the caller passes a `summarize` function
(`llm_summarizer` builds one over `kb_distillery.llm`). Running it twice changes nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from kb_distillery import kbconfig
from kb_distillery.core import frontmatter

THINK_CITE = "think:"
LEGACY_PREFIX = "think/"
PROVENANCE_DIR = ".provenance"
PAGE_PREFIX = "distilled-think-"


class DistillError(ValueError):
    """A note or kb that cannot be distilled; raised before anything is written."""


@dataclass
class Outcome:
    kb: str
    page: str            # kb-relative path of the distilled-think page
    root: str
    written: bool        # False when the page was already there (idempotent re-run)


# --- think side -------------------------------------------------------------------------------------
def note_rel(arg: str, think_root: str) -> str:
    """`note` | `note.md` | `sub/note.md` | `think:note.md` | `think/note.md` -> the note's path inside the think space."""
    rel = arg.strip().replace("\\", "/")
    for prefix in (THINK_CITE, LEGACY_PREFIX):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    if not rel.endswith(".md"):
        rel += ".md"
    parts = rel.split("/")
    if rel.startswith("/") or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise DistillError(f"not a note path inside the think space: {arg!r}")
    if not os.path.isfile(os.path.join(think_root, *parts)):
        raise DistillError(f"no think note {rel!r} in {think_root}")
    return rel


def cite(rel: str) -> str:
    return THINK_CITE + rel


def resolve_cite(source: str, think_root: str | None = None) -> str | None:
    """The file a `sources[].resource` citation names (`think:<note>.md`, or the legacy `think/<note>.md`), or None if it is gone."""
    think_root = think_root or kbconfig.think_root()
    for prefix in (THINK_CITE, LEGACY_PREFIX):
        if source.startswith(prefix):
            parts = source[len(prefix):].split("/")
            if parts and not any(p in ("", ".", "..") for p in parts):
                path = os.path.join(think_root, *parts)
                return path if os.path.isfile(path) else None
    return None


def provenance_path(think_root: str, rel: str) -> str:
    return os.path.join(think_root, PROVENANCE_DIR, *rel.split("/")) + ".json"


def read_provenance(think_root: str, rel: str) -> dict:
    """Where the note went: `{"note": rel, "distilled": [{"kb", "page", "at", "note_sha256"}, …]}` (empty when never)."""
    try:
        with open(provenance_path(think_root, rel), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("distilled"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"note": rel, "distilled": []}


def _write_provenance(think_root: str, rel: str, data: dict) -> None:
    data["distilled"] = sorted(data["distilled"], key=lambda e: e["kb"])
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path = provenance_path(think_root, rel)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# --- note content -----------------------------------------------------------------------------------
def read_body(path: str) -> str:
    """The note's text without frontmatter; only the human zone when the note marks one."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:].lstrip("\n")
    if "<!-- human-zone -->" in text:
        body = text.split("<!-- human-zone -->", 1)[1].split("<!-- end-human-zone -->", 1)[0]
    return body.strip()


def default_summary(body: str) -> str:
    """Deterministic, no LLM: the note's first paragraph, capped."""
    para = body.split("\n\n")[0].replace("\n", " ").strip() if body else ""
    if not para:
        return "Empty note: write in think and distill again."
    return para[:600] + ("…" if len(para) > 600 else "")


def llm_summarizer(backend: str | None = None):
    """A `summarize(body, title)` over `kb_distillery.llm` (the repo's one LLM tool). `backend` is subscription | api | batch;
    None means `$KB_LLM_BACKEND`, then subscription. Imported lazily so the default path never loads it."""
    def summarize(body: str, title: str) -> str:
        from kb_distillery import llm
        prompt = (f"Summarize this personal research note titled {title!r} in at most 5 sentences. Plain prose, no "
                  f"headings, no preamble, keep the author's claims and open questions.\n\n{body[:20000]}")
        res = llm.ask(prompt, backend=backend)
        if not res.ok:
            raise DistillError(f"summary failed ({res.backend or backend}): {res.error}")
        return res.text.strip()
    return summarize


# --- kb side ----------------------------------------------------------------------------------------
def slug_for(rel: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", rel[:-3].lower()).strip("-")
    if not stem:
        raise DistillError(f"cannot name a page after {rel!r}")
    return PAGE_PREFIX + stem


def resolve_kbs(refs) -> list[tuple[str, str]]:
    """Each ref (an id, a path, or an `(id, root)` pair) -> `(id, root)`; duplicates dropped, order kept."""
    out: dict[str, str] = {}
    for ref in refs:
        if isinstance(ref, tuple):
            kb_id, root = ref
        else:
            try:
                cfg = kbconfig.load(ref)
            except kbconfig.KbConfigError as e:
                raise DistillError(str(e)) from e
            kb_id, root = cfg.id, cfg.root
        if not os.path.isdir(os.path.join(root, "wiki")):
            raise DistillError(f"{root} has no wiki/ folder: not a knowledge base")
        out.setdefault(kb_id, os.path.realpath(root))
    if not out:
        raise DistillError("no knowledge base given")
    return list(out.items())


def _title(rel: str) -> str:
    return os.path.basename(rel)[:-3].replace("-", " ").replace("_", " ").strip().title() or rel


def render_page(rel: str, summary: str, at: str) -> str:
    return f"""---
type: distilled-think
layer: concept
maturity: review
{frontmatter.sources_line([cite(rel)])}
distilled_at: {at}
---

# Distilled · {_title(rel)}

## Summary

{summary.strip()}

## Proposed propagation

_Sent with `kbd distill`; no edits proposed yet. Run the distill-think skill on this note to propose them._

## Not promoting

—
"""


def _front(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return frontmatter.parse(f.read())[0] or {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def distill_note(note: str, kbs, think_root: str | None = None, summarize=None, now: str | None = None) -> list[Outcome]:
    """Write the distilled-think page into every kb in `kbs` and record each in the note's provenance.

    Checks everything first (note, kbs, page-name collisions) and writes only if all pass; pages are written
    before the provenance, so a crash leaves a page that the next run adopts instead of duplicating."""
    think_root = os.path.realpath(think_root or kbconfig.think_root())
    rel = note_rel(note, think_root)
    targets = resolve_kbs(kbs)
    slug = slug_for(rel)
    page_rel = f"wiki/{slug}.md"
    for kb_id, root in targets:
        existing = os.path.join(root, page_rel)
        if os.path.isfile(existing) and cite(rel) not in frontmatter.resources(_front(existing)):
            raise DistillError(f"{kb_id}: {page_rel} already exists and cites another note; rename one of them")

    path = os.path.join(think_root, *rel.split("/"))
    body = read_body(path)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    stamp = now or _now()
    summary = None

    prov = read_provenance(think_root, rel)
    recorded = {e["kb"]: e for e in prov["distilled"]}
    outcomes = []
    for kb_id, root in targets:
        full = os.path.join(root, page_rel)
        written = not os.path.isfile(full)
        if written:
            if summary is None:
                summary = (summarize or (lambda b, t: default_summary(b)))(body, _title(rel))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(render_page(rel, summary, stamp))
        if kb_id not in recorded:
            recorded[kb_id] = {"kb": kb_id, "page": page_rel, "at": _front(full).get("distilled_at") or stamp,
                               "note_sha256": sha}
        outcomes.append(Outcome(kb_id, page_rel, root, written))
    prov["note"] = rel
    prov["distilled"] = list(recorded.values())
    _write_provenance(think_root, rel, prov)
    return outcomes

"""Cards into a kb: <kb>/raw/printed-docs/ir-*.md as one `kb(catalog)` knowledge step, and the artifact graph.

raw/ is split by format and nothing may sit loose in it, so the cards go to the flat `printed-docs/` folder (typed documents).
They follow the raw rules (`raw-and-corpus.md`): a lowercase kebab name unique in the vault, one row each in `meta/corpus.tsv`.
A card is derived evidence, not backlog, so its row starts as `skip` (a decision: it needs no note of its own) and stays so when
a page cites it.

The write is the same step `services/inbox_add.py` takes: the ops lock, no open session, the kb's storage connector for the
bytes (a changed card replaces its old text: the card is regenerated, not a source), one `commit_op("catalog", ...)`. A card
whose bytes did not change is left alone, so exporting twice at the same commits commits nothing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from kb_distillery.codekb.cites import CARD_DIR
from kb_distillery.config import kb as kbconfig
from kb_distillery.ops import core
from kb_distillery.storage import StorageError, for_kb
from kb_distillery.vault.pages import read_manifest
from kb_distillery.vault.schema import RAW_PRINTED

GRAPH = "artifacts/graph.json"
assert CARD_DIR == f"raw/{RAW_PRINTED}"


class ExportError(RuntimeError):
    pass


def _sha12(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def _seed_rows(root: str, keys: list[str], shas: dict[str, str]) -> None:
    """A row for each new card, as `skip`; a row that exists keeps its disposition (lint refreshes the hash)."""
    from kb_distillery.lint.lint import write_manifest      # lazy: lint reads the kb's config when imported
    rows = read_manifest(root)
    for key in keys:
        r = rows.get(key)
        if r is None:
            rows[key] = {"path": key, "sha1": shas[key], "kind": RAW_PRINTED, "disposition": "skip", "slug": "", "collection": "", "scopes": ""}
        else:
            r["sha1"] = shas[key]
    write_manifest(rows, root)


def export(cards_dir: Path, root: str, summary: str | None = None) -> dict:
    """Copy <cards_dir>/*.md into the kb at `root` and commit them. Returns {"added", "updated", "unchanged", "gone", "commit"}."""
    cards = sorted(cards_dir.glob("*.md"))
    if not cards:
        raise ExportError(f"{cards_dir} has no cards: run `distill code cards` first")
    try:
        kbconfig.require_writable(root)
        store = for_kb(root=root)
        with core.ops_lock(root):
            session = core.current_session(root)
            if session:
                raise ExportError(f"an ops session is open ({session['op']} {session['target']}): finish it first")
            before = core.knowledge_state(root)
            out: dict = {"added": [], "updated": [], "unchanged": [], "gone": [], "commit": None}
            shas: dict[str, str] = {}
            for src in cards:
                key, data = f"{CARD_DIR}/{src.name}", src.read_bytes()
                shas[key] = _sha12(data)
                if store.exists(key):
                    if store.info(key).sha1[:12] == shas[key]:
                        out["unchanged"].append(src.name)
                        continue
                    out["updated"].append(src.name)
                else:
                    out["added"].append(src.name)
                store.put(key, data, overwrite=True)
            rows = read_manifest(root)
            reseed = [f"{CARD_DIR}/{n}" for n in out["unchanged"] if f"{CARD_DIR}/{n}" not in rows or f"{CARD_DIR}/{n}" in before]   # a failed earlier run left them bare or uncommitted
            have = {Path(k).name for k in store.list(f"{CARD_DIR}/ir-")}
            out["gone"] = sorted(have - {c.name for c in cards})
            touched = [f"{CARD_DIR}/{n}" for n in out["added"] + out["updated"]] + reseed
            if not touched:
                return out
            _seed_rows(root, touched, shas)
            n = len(touched)
            out["commit"] = core.commit_op("catalog", "code-ir", summary or f"code IR: {n} card{'s' if n != 1 else ''}",
                                           paths=sorted(set(core.changed_since(before, root)) | set(touched) | {"meta/corpus.tsv"}),
                                           root=root, _locked=True)
            return out
    except (core.OpsError, kbconfig.ReadOnlyError, StorageError) as e:
        raise ExportError("knowledge step refused: " + str(e)) from e

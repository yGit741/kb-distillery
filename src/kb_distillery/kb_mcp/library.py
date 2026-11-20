"""The read model behind the kb-mcp tools: local knowledge bases in, plain dicts out. Never writes to a kb.

The one side effect is the machine-local search index `<kb>/.cache/search/fts.sqlite` that `kb_distillery.search.fts`
keeps (gitignored, rebuilt from the files at any time); when it cannot be written the search falls back to a scan.
Lookups raise `KbMcpError`, whose message names what was wrong and what exists.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import subprocess
from datetime import date, datetime, timedelta, timezone

from kb_distillery.config import kb as kbconfig
from kb_distillery.config.layout import LOG_REL, MANIFEST, WIKI_DIR
from kb_distillery.search import fts
from kb_distillery.storage import StorageError, for_kb
from kb_distillery.vault import frontmatter
from kb_distillery.vault import log as kblog

MAX_PAGE_CHARS = 40_000
MAX_EXCERPT_CHARS = 20_000
MAX_EXCERPT_FILE = 5_000_000        # a text source larger than this is described, not read
TEXT_EXTS = (".md", ".txt")
RESERVED = ("index.md", "log.md")
_WORD = re.compile(r"\w+", re.U)
_OP = re.compile(r"^(?P<op>[^|]+?)\s*\|\s*(?P<summary>.*?)(?:\s*←.*)?$")
_KB_COMMIT = re.compile(r"^kb\((?P<op>[^)]+)\):\s*(?P<summary>.*?)(?:\s*\(kb-(?P<version>[\d.]+)\))?$")


class KbMcpError(ValueError):
    """A request the library cannot answer (unknown kb or page, bad argument)."""


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def _read(path: str, limit: int | None = None) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def _inside(root: str, path: str) -> bool:
    """True when `path` really lies under `root` (a symlink out of the folder does not)."""
    root = os.path.realpath(root)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


class Library:
    """The bases dir (`$KB_DISTILLERY_HOME`) plus any extra kb folders, looked up fresh on every call."""

    def __init__(self, extra: list[str] | None = None):
        self.extra = [os.path.realpath(os.path.expanduser(p)) for p in extra or []]

    # ---------- which kbs ----------
    def roots(self) -> dict[str, str]:
        """id -> folder: every kb of the bases dir, then each extra folder (its kb.toml id; the first one wins)."""
        found = dict(kbconfig.discover())
        for folder in self.extra:
            try:
                cfg = kbconfig.load_dir(folder, strict=False)
            except kbconfig.KbConfigError:
                continue
            found.setdefault(cfg.id, cfg.root)
        return found

    def _config(self, kb: str) -> kbconfig.KbConfig:
        roots = self.roots()
        key = next((i for i in roots if i == kb or i.lower() == kb.lower()), None)
        if key is None:       # also accept the kb's display name
            for i, root in roots.items():
                try:
                    if kbconfig.load_dir(root, strict=False).name.lower() == kb.lower():
                        key = i
                        break
                except kbconfig.KbConfigError:
                    continue
        if key is None:
            raise KbMcpError(f"no knowledge base {kb!r}; known: {', '.join(sorted(roots)) or 'none'}")
        return kbconfig.load_dir(roots[key], strict=False)

    def _configs(self, kb: str | None) -> list[kbconfig.KbConfig]:
        if kb:
            return [self._config(kb)]
        out = []
        for root in self.roots().values():
            try:
                out.append(kbconfig.load_dir(root, strict=False))
            except kbconfig.KbConfigError:
                continue
        return out

    # ---------- pages ----------
    @staticmethod
    def _wiki(cfg) -> str:
        return os.path.join(cfg.root, WIKI_DIR)

    def _page_files(self, cfg) -> list[str]:
        """Wiki-relative paths (`/` separated) of every content page: no index.md, no log.md."""
        wiki = self._wiki(cfg)
        try:
            names = sorted(os.listdir(wiki))          # a flat folder, as the search index sees it (sections hold only index.md)
        except OSError:
            return []
        return [n for n in names if n.endswith(".md") and n not in RESERVED and not n.startswith(".")
                and os.path.isfile(os.path.join(wiki, n)) and _inside(wiki, os.path.join(wiki, n))]

    def _meta(self, cfg, rel: str) -> tuple[dict, str, str]:
        text = _read(os.path.join(self._wiki(cfg), rel))
        fm, body = frontmatter.parse(text)
        fm = fm or {}
        slug = os.path.splitext(os.path.basename(rel))[0]
        return fm, text, frontmatter.page_title(fm, body, slug)

    def _resolve(self, cfg, page: str) -> str:
        """The wiki-relative path of `page`: a path, a file name, a slug or a title (case-insensitive)."""
        want = (page or "").strip().replace("\\", "/").lstrip("/")
        if want.startswith(WIKI_DIR + "/"):
            want = want[len(WIKI_DIR) + 1:]
        files = self._page_files(cfg)
        for cand in (want, want + ".md"):
            if cand in files:
                return cand
        low = want.lower().removesuffix(".md")
        for rel in files:
            if os.path.splitext(os.path.basename(rel))[0].lower() == low:
                return rel
        for rel in files:
            if self._meta(cfg, rel)[2].lower() == low:
                return rel
        raise KbMcpError(f"no page {page!r} in {cfg.id}; find one with search or get_index")

    # ---------- the tools ----------
    def list_kbs(self) -> dict:
        return {"kbs": [self._summary(c) for c in self._configs(None)]}

    def _summary(self, cfg) -> dict:
        kb = cfg.data.get("kb") if isinstance(cfg.data.get("kb"), dict) else {}
        return {"id": cfg.id, "title": cfg.name, "description": str(kb.get("description") or ""), "kit": cfg.kit,
                "pages": len(self._page_files(cfg)), "sources": len(self._corpus(cfg, ("source", "partial"))),
                "last_change": self._last_change(cfg)}

    def _corpus(self, cfg, dispositions=None) -> dict[str, dict]:
        """raw path -> manifest row (meta/corpus.tsv), optionally only some dispositions."""
        path, rows = os.path.join(cfg.root, MANIFEST), {}
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8", newline="") as f:
            lines = [ln for ln in f if ln.strip() and not ln.startswith("#")]
        for row in csv.DictReader(lines, delimiter="\t"):
            if row.get("path") and (dispositions is None or (row.get("disposition") or "") in dispositions):
                rows[row["path"]] = row
        return rows

    def _last_change(self, cfg) -> str:
        """ISO time of the newest commit touching wiki/ (a kb's own git repo), else of the newest wiki file."""
        if cfg.git_root:
            got = self._git(cfg.root, "log", "-1", "--format=%cI", "--", WIKI_DIR)
            if got:
                return got.strip()
        newest = 0.0
        for dirpath, _d, files in os.walk(self._wiki(cfg)):
            for name in files:
                try:
                    newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
                except OSError:
                    pass
        return datetime.fromtimestamp(newest, timezone.utc).isoformat(timespec="seconds") if newest else ""

    @staticmethod
    def _git(root: str, *args: str) -> str | None:
        try:
            p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.stdout if p.returncode == 0 else None

    def search(self, query: str, kb: str | None = None, limit: int = 10) -> dict:
        limit = max(1, min(int(limit), 50))
        hits = [h for cfg in self._configs(kb) for h in self._search_one(cfg, query, limit)]
        hits.sort(key=lambda h: h.pop("_score"), reverse=True)
        return {"query": query, "hits": hits[:limit]}

    def _search_one(self, cfg, query: str, limit: int) -> list[dict]:
        try:
            raw = fts.search(cfg.root, query, kinds=["page"], limit=limit * 2)
            if not raw and len(_words(query)) > 1:      # the index wants every word: a question gets its words one by one
                best: dict[str, dict] = {}
                for w in {w for w in _words(query) if len(w) > 2}:
                    for h in fts.search(cfg.root, w, kinds=["page"], limit=limit * 2):
                        if h["path"] not in best or h["score"] > best[h["path"]]["score"]:
                            best[h["path"]] = h
                raw = sorted(best.values(), key=lambda h: -h["score"])
        except (OSError, sqlite3.Error, ValueError):
            raw = self._scan_search(cfg, query)
        out, wiki_prefix, pages = [], WIKI_DIR + "/", set(self._page_files(cfg))
        for h in raw:
            path = str(h["path"]).replace(os.sep, "/")
            rel = path[len(wiki_prefix):] if path.startswith(wiki_prefix) else path
            if rel not in pages:
                continue
            fm = self._meta(cfg, rel)[0]
            out.append({"kb": cfg.id, "page": rel, "title": h["title"], "description": frontmatter.unquote(str(fm.get("description") or "")),
                        "snippet": h["snippet"], "_score": h["score"]})
            if len(out) >= limit:
                break
        return out

    def _scan_search(self, cfg, query: str) -> list[dict]:
        """The fallback when the index cannot be written: count the query words in each page."""
        words, hits = _words(query), []
        for rel in self._page_files(cfg):
            fm, text, title = self._meta(cfg, rel)
            low = text.lower()
            score = sum(low.count(w) for w in words) + 5 * sum(w in title.lower() for w in words)
            if score:
                hits.append({"title": title, "path": f"{WIKI_DIR}/{rel}", "snippet": "", "score": float(score)})
        return sorted(hits, key=lambda h: -h["score"])[:20]

    def find_kb(self, question: str, limit: int = 3) -> dict:
        words, ranked = set(_words(question)), []
        for cfg in self._configs(None):
            s = self._summary(cfg)
            have = set(_words(f"{s['id']} {s['title']} {s['description']}"))
            pages = self._search_one(cfg, question, 3)
            score = len(words & have) + 0.5 * max((p["_score"] for p in pages), default=0.0)
            if score > 0:
                ranked.append((score, {**s, "score": round(score, 3),
                                       "best_pages": [{k: v for k, v in p.items() if k != "_score"} for p in pages]}))
        ranked.sort(key=lambda r: -r[0])
        return {"question": question, "kbs": [r[1] for r in ranked[:max(1, int(limit))]]}

    def get_index(self, kb: str, section: str | None = None) -> str:
        cfg = self._config(kb)
        rel = "index.md"
        if section:
            name = section.strip().strip("/")
            if "/" in name or name.startswith(".") or not os.path.isfile(os.path.join(self._wiki(cfg), name, "index.md")):
                raise KbMcpError(f"no index section {section!r} in {cfg.id}; the root index lists them")
            rel = f"{name}/index.md"
        path = os.path.join(self._wiki(cfg), rel)
        if not os.path.isfile(path) or not _inside(self._wiki(cfg), path):     # a symlink out of wiki/ is not an index
            raise KbMcpError(f"{cfg.id} has no wiki/{rel}")
        return f"<!-- kb: {cfg.id} | index: {rel} -->\n{_read(path)}"

    def get_page(self, kb: str, page: str) -> str:
        cfg = self._config(kb)
        rel = self._resolve(cfg, page)
        text = _read(os.path.join(self._wiki(cfg), rel))
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + "\n\n[... truncated]"
        return f"<!-- kb: {cfg.id} | page: {rel} -->\n{text}"

    def get_sources(self, kb: str, page: str, max_chars: int = 2000) -> dict:
        """The raw sources a page cites: its `raw:` file and its `sources[].resource` entries. A text source comes with
        its first `max_chars` characters (0 = metadata only); every other file is described, never served."""
        cfg = self._config(kb)
        rel = self._resolve(cfg, page)
        fm = self._meta(cfg, rel)[0]
        limit = max(0, min(int(max_chars), MAX_EXCERPT_CHARS))
        resources = ([str(fm["raw"]).strip()] if fm.get("raw") else []) + frontmatter.resources(fm)
        corpus, out, seen = self._corpus(cfg), [], set()
        for res in resources:
            if res in seen:
                continue
            seen.add(res)
            path = res.lstrip("/")
            if path.startswith("raw/"):
                out.append(self._raw_entry(cfg, res, path, corpus, limit))
            else:
                out.append({"resource": res, "kind": "url" if re.match(r"https?://", res) else "other"})
        return {"kb": cfg.id, "page": rel, "sources": out}

    def _raw_entry(self, cfg, res: str, path: str, corpus: dict, limit: int) -> dict:
        """One cited raw file, read through the kb's storage connector (a key outside the raw tree is refused there)."""
        row = corpus.get(path, {})
        entry = {"resource": res, "kind": "raw", "path": path, "disposition": row.get("disposition", ""),
                 "slug": row.get("slug", "")}
        try:
            store = for_kb(cfg)
            info = store.info(path)
            entry["available"], entry["bytes"] = True, info.size
            if limit and path.lower().endswith(TEXT_EXTS) and info.size <= MAX_EXCERPT_FILE:
                text = store.get(path).decode("utf-8", errors="replace")
                entry["excerpt"], entry["truncated"] = text[:limit], len(text) > limit
        except StorageError:
            return {**entry, "available": False}
        return entry

    def whats_new(self, since: str | None = None, kb: str | None = None, limit: int = 20) -> dict:
        """Recent knowledge steps, newest first: the entries of each kb's wiki/log.md, else its `kb(op)` commits."""
        cutoff = since or (date.today() - timedelta(days=30)).isoformat()
        try:
            date.fromisoformat(cutoff)
        except ValueError:
            raise KbMcpError(f"since must be YYYY-MM-DD, got {since!r}") from None
        entries = []
        for cfg in self._configs(kb):
            entries += [e for e in self._log_entries(cfg) if e["date"] >= cutoff]
        entries.sort(key=lambda e: e["date"], reverse=True)
        return {"since": cutoff, "entries": entries[:max(1, int(limit))]}

    def _log_entries(self, cfg) -> list[dict]:
        path = os.path.join(cfg.root, LOG_REL)
        out = []
        if os.path.isfile(path):
            for day, blocks in kblog.parse(_read(path)):
                for block in blocks:
                    m = _OP.match(block[0].removeprefix("### ").strip())
                    out.append({"kb": cfg.id, "date": day, "op": m["op"].strip() if m else "", "summary": m["summary"] if m else block[0],
                                "source": "log.md"})
        if out or not cfg.git_root:
            return out
        raw = self._git(cfg.root, "log", "--grep=^kb(", "-n", "200", "--format=%cs%x1f%s") or ""
        for line in raw.splitlines():
            day, _, subject = line.partition("\x1f")
            m = _KB_COMMIT.match(subject)
            if m:
                out.append({"kb": cfg.id, "date": day, "op": m["op"], "summary": m["summary"], "version": m["version"] or "",
                            "source": "git"})
        return out

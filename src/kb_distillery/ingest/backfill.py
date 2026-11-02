"""Repair paper author lists from arXiv. 0 LLM.

The researcher bootstrap wrote `authors: [<researcher>]` on every paper it imported, so
co-authors (e.g. Vardi on Daniely's hardness papers) were invisible. This fills the full list
from arXiv, editing only the `authors:` line, and only when the fetched record is verifiably
the same paper.
"""
import os
import re

from . import arxiv_meta
from .paths import ROOT
from kb_distillery.core import frontmatter, wikiio
from .resolve import normalize_arxiv_id

WIKI = os.path.join(ROOT, "wiki")
FM_AUTHORS = re.compile(r"^authors:.*$", re.M)
TITLE = re.compile(r"^#\s+(.+)$", re.M)
UNSAFE = re.compile(r"[,#\[\]]")   # the vault's flat-YAML parser splits on , and strips # comments


def _frontmatter(text):
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    return (text[3:end], end) if end != -1 else (None, None)


def _field(fm_text, key):
    m = re.search(rf"^{key}:\s*(.*)$", fm_text, re.M)
    return m.group(1).strip() if m else ""


def _list(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [x.strip() for x in value[1:-1].split(",") if x.strip()]
    return [value] if value else []


def format_authors(names):
    return "[" + ", ".join(UNSAFE.sub("", n).strip() for n in names if n.strip()) + "]"


def candidates():
    """[(path, arxiv_id, current_authors, title)] for paper pages that cite arXiv."""
    out = []
    for fn in sorted(os.listdir(WIKI)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(WIKI, fn)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fm, end = _frontmatter(text)
        if not fm or _field(fm, "type") != "paper":
            continue
        aid = normalize_arxiv_id(_field(fm, "url"))
        if not aid:
            continue
        t = TITLE.search(text[end:])
        out.append((path, aid, _list(_field(fm, "authors")), t.group(1).strip() if t else ""))
    return out


def plan(rows, fetched):
    """Split into (updates, unchanged, mismatched, missing). Pure — no I/O, so it is testable."""
    updates, unchanged, mismatched, missing = [], [], [], []
    for path, aid, current, title in rows:
        meta = fetched.get(aid)
        if not meta or not meta["authors"]:
            missing.append((path, aid))
            continue
        if not arxiv_meta.same_paper(meta, current, title):
            mismatched.append((path, aid, meta["title"]))
            continue
        new = [UNSAFE.sub("", a).strip() for a in meta["authors"]]
        if [a.lower() for a in new] == [a.lower() for a in current]:
            unchanged.append(path)
        else:
            updates.append((path, current, new))
    return updates, unchanged, mismatched, missing


def apply(updates):
    for path, _old, new in updates:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        line = f"authors: {format_authors(new)}"
        fm = wikiio.split_page(text)[0]
        fm2 = (FM_AUTHORS.sub(lambda _m: line, fm, count=1) if FM_AUTHORS.search(fm)
               else fm.replace("---\n", f"---\n{line}\n", 1))
        wikiio.write_front_matter(path, fm2)


def backfill_authors(dry_run=False, fetcher=None):
    rows = candidates()
    print(f"{len(rows)} paper pages cite arXiv — fetching metadata…")
    fetched = (fetcher or arxiv_meta.fetch)([aid for _p, aid, _a, _t in rows])
    updates, unchanged, mismatched, missing = plan(rows, fetched)

    for path, old, new in updates:
        added = [a for a in new if a.lower() not in {o.lower() for o in old}]
        print(f"  {os.path.basename(path)[:-3]}: +{len(added)} → {', '.join(new)}")
    for path, aid, got in mismatched:
        print(f"  SKIP {os.path.basename(path)[:-3]}: url arXiv:{aid} is “{got[:70]}” — "
              "not this paper, fix its url:")
    for path, aid in missing:
        print(f"  SKIP {os.path.basename(path)[:-3]}: arXiv:{aid} not returned")

    print(f"\n{len(updates)} to update · {len(unchanged)} already complete · "
          f"{len(mismatched)} url mismatches · {len(missing)} not found")
    if dry_run:
        print("dry run — nothing written")
    elif updates:
        apply(updates)
        print(f"wrote {len(updates)} pages — run `python3 -m kb_distillery.lint.lint`")
    return 0 if not mismatched else 1


FM_URL = re.compile(r"^url:.*$", re.M)


def _set_field(path, regex, line):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm = wikiio.split_page(text)[0]
    fm2 = regex.sub(lambda _m: line, fm, count=1) if regex.search(fm) else fm.replace("---\n", f"---\n{line}\n", 1)
    wikiio.write_front_matter(path, fm2)


def _set_url(path, url):
    """Set `url:` and keep the Source page's `sources:` resource in step with it: the old url goes, the new http(s)
    one comes in (an emptied url leaves no resource). Front matter only."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm = frontmatter.parse(text)[0] or {}
    old = str(fm.get("url") or "").strip()
    keep = [(e.get("resource") if isinstance(e, dict) else e) for e in
            ([fm["sources"]] if isinstance(fm.get("sources"), (str, dict)) else list(fm.get("sources") or []))]
    keep = [r for r in keep if r and r != old]
    if url and frontmatter.url_sources(url):
        keep.insert(0, url)
    def edit(inner):
        inner = re.sub(r"^url:.*$", lambda _m: f"url: {url}" if url else "url:", inner, count=1, flags=re.M)
        inner = re.sub(r"^sources:.*(?:\n[ \t]+.*|\n- .*)*\n?", "", inner + "\n", count=1, flags=re.M).rstrip("\n")
        if keep:
            inner = re.sub(r"^(url:.*)$", lambda m: m.group(1) + "\n" + frontmatter.sources_line(keep), inner,
                           count=1, flags=re.M)
        return inner
    new = wikiio.edit_front_matter(text, edit)
    if new != text:
        wikiio.write_page(path, new)


def _raw_of(fm_text):
    raw = _field(fm_text, "raw")
    if raw.startswith("["):
        return None                     # multi-file units are not single papers
    return raw if raw.lower().endswith(".pdf") and raw.startswith("raw/") else None


def wrong_downloads(stamp=None, pages=None):
    """[(page_path, raw_rel, want, got)] — paper pages whose PDF is stamped with another arXiv
    id than their url: cites. These are wrong downloads (a Semantic Scholar id that pointed at a
    stranger's paper), not metadata drift: the bytes must be replaced, and any digest made from
    them is of the wrong paper."""
    stamp = stamp or arxiv_meta.stamp
    out = []
    for fn in sorted(pages if pages is not None else os.listdir(WIKI)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(WIKI, fn)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fm, _end = _frontmatter(text)
        if not fm or _field(fm, "type") != "paper":
            continue
        want, raw_rel = normalize_arxiv_id(_field(fm, "url")), _raw_of(fm)
        if not want or not raw_rel:
            continue
        got = stamp(os.path.join(ROOT, raw_rel))
        if got and normalize_arxiv_id(got) != want:
            out.append((path, raw_rel, want, got))
    return out


def refetch_raw(dry_run=True, downloader=None, stamp=None):
    """Replace every wrong download with the PDF its page actually cites. The new bytes are
    checked (PDF magic + stamp == url) before they overwrite anything. The sha1 change then
    re-opens the corpus row as `queued` on the next lint — the right outcome, since the digest
    was written from the wrong paper."""
    from . import scrap
    rows = wrong_downloads(stamp)
    if not rows:
        print("no wrong downloads: every paper PDF is stamped with the arXiv id its page cites")
        return 0
    for path, raw_rel, want, got in rows:
        print(f"  {os.path.basename(path)[:-3]}\n      {raw_rel} is arXiv:{got}, page cites arXiv:{want}")
    print(f"\n{len(rows)} wrong downloads" + (" — dry run, nothing replaced; add --apply" if dry_run else ""))
    if dry_run:
        return 1
    download = downloader or scrap._download
    stamp = stamp or arxiv_meta.stamp
    replaced, failed = 0, []
    for path, raw_rel, want, _got in rows:
        dest = os.path.join(ROOT, raw_rel)
        tmp = dest + ".refetch"
        try:
            data = download(f"https://arxiv.org/pdf/{want}", tmp)
            if not data.startswith(scrap.PDF_MAGIC):
                raise ValueError("not a PDF")
            new_stamp = stamp(tmp)
            if new_stamp and normalize_arxiv_id(new_stamp) != want:
                raise ValueError(f"fetched PDF is stamped arXiv:{new_stamp}")
            os.replace(tmp, dest)
            replaced += 1
            print(f"  replaced {raw_rel} ← arXiv:{want}")
        except Exception as e:  # keep the old bytes; report
            failed.append((raw_rel, str(e)))
            print(f"  FAILED  {raw_rel}: {e}")
            if os.path.exists(tmp):
                os.remove(tmp)
    print(f"\n{replaced} replaced · {len(failed)} failed")
    if replaced:
        print("run `python3 -m kb_distillery.lint.lint`: the sha1 change re-queues these rows; their pages were "
              "digested from the wrong paper — re-digest, then `pixi run ops -- record catalog "
              "refetch-raw \"…\" meta/corpus.tsv`")
    return 0 if not failed else 1


def fix_urls(dry_run=False, searcher=None, pause=arxiv_meta.PAUSE_S):
    """Re-find papers whose `url:` points at an unrelated arXiv record, by title search."""
    import time
    rows = candidates()
    fetched = arxiv_meta.fetch([aid for _p, aid, _a, _t in rows])
    _u, _same, mismatched, _missing = plan(rows, fetched)
    by_path = {p: (aid, cur, title) for p, aid, cur, title in rows}
    search = searcher or arxiv_meta.search_title
    fixed, unresolved, unavailable = [], [], []
    print(f"{len(mismatched)} pages cite the wrong arXiv record — searching by title…")
    for i, (path, bad, _got) in enumerate(mismatched):
        _aid, current, title = by_path[path]
        slug = os.path.basename(path)[:-3]
        try:
            hit = search(title, current)
        except arxiv_meta.ArxivUnavailable as e:
            unavailable.append(path)      # not "no match": the url must stay as it is
            print(f"  ???  {slug}: arXiv unavailable ({e}) — left untouched, retry later")
            continue
        if hit:
            fixed.append((path, bad, hit))
            print(f"  FIX  {slug}: arXiv:{bad} → arXiv:{hit['id']}  ({', '.join(hit['authors'][:4])})")
        else:
            unresolved.append((path, bad))
            print(f"  ---  {slug}: no confident match — url cleared, check by hand")
        if pause and i + 1 < len(mismatched):
            time.sleep(pause)
    if not dry_run:
        for path, _bad, hit in fixed:
            _set_url(path, hit["url"])
            _set_field(path, FM_AUTHORS, f"authors: {format_authors(hit['authors'])}")
        for path, _bad in unresolved:
            # a demonstrably wrong link is worse than none: dedup and the reader both trust it
            _set_url(path, "")
    print(f"\n{len(fixed)} fixed · {len(unresolved)} cleared for manual lookup · "
          f"{len(unavailable)} unavailable" + (" · dry run, nothing written" if dry_run else ""))
    return 0 if not unavailable else 1

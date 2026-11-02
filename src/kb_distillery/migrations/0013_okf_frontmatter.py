"""OKF frontmatter (schema 1.5): the page header follows Open Knowledge Format v0.2 (`wiki/` is the bundle root).

Per page, front matter only (the body is kept byte for byte), line by line so key order and every untouched line stay:
  status      -> maturity (same values); OKF `status: draft` is set on pages at `depth: listed`, omitted otherwise
  summary     -> description
  summary_by  -> generated: {by, at}. `summary_by: me` = the user wrote it -> `human:<owner>`, the owner read from
                 kb.toml `[kb] owner`; a tool-written summary -> `summarize/<model>`. `at` only from a matching row of
                 .cache/summaries/proposals.jsonl (its `ts`, with the machine's UTC offset), else left out
  date        -> created (`YYYY-MM-DDT00:00:00Z`); an empty `date:` is dropped
  title       -> from the first heading when the page has none
  sources     -> objects with a `resource`: a wiki page (core.links.page_path), the page's own http(s) `url` on a Source
                 page, a `think:<note>.md` or any other descriptor kept as plain text. `raw:` stays an extension field
  related     -> page paths (core.links.page_path), resolved through slug, `aliases:` and meta/aliases.tsv
  type        -> `excalidraw` on a .md under wiki/ with frontmatter but no `type`
Whatever cannot be resolved or added safely is kept as it was and listed in the report (printed, and returned).
Idempotent: a field already in the new shape is left alone.

    python src/kb_distillery/migrations/0013_okf_frontmatter.py [--root R] [--dry-run]
"""
import argparse
import datetime
import json
import os
import re
import sys

from kb_distillery.core import frontmatter as fmlib
from kb_distillery.core import links

PRODUCES = (1, 5)
PRODUCER = "summarize"                      # `generated.by` of a tool-written summary is `summarize/<model>`
UNKNOWN_MODEL = "unknown"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*:(.*)$")
HTTP = re.compile(r"^https?://\S+$")
OKF_STATUS = {"draft", "stable", "deprecated"}


# -- helpers ---------------------------------------------------------------------------------------------------
def owner_of(root):
    """The `human:<id>` id: kb.toml `[kb] owner`; None when the key is missing."""
    import tomllib
    try:
        with open(os.path.join(root, "kb.toml"), "rb") as f:
            return str(tomllib.load(f).get("kb", {}).get("owner") or "").strip() or None
    except OSError:
        return None


def split_entries(inner):
    """The lines between the fences as [key or None, [lines]]: continuation lines belong to the key above them."""
    out = []
    for line in inner.split("\n"):
        m = KEY.match(line)
        cont = line.startswith((" ", "\t")) or line.startswith("- ") or line.rstrip() == "-"
        if m and not cont:
            out.append([m.group(1), [line]])
        elif out:
            out[-1][1].append(line)
        else:
            out.append([None, [line]])
    return out


def _find(entries, key):
    return next((i for i, e in enumerate(entries) if e[0] == key), None)


def _put_after(entries, after, key, line):
    i = next((i for a in after for i in [_find(entries, a)] if i is not None), None)
    entries.insert(len(entries) if i is None else i + 1, [key, [line]])


def _with_offset(ts, tz=None):
    """A proposals.jsonl `ts` (naive local time of the machine that ran `summarize run`, or already offset) with its
    UTC offset, `YYYY-MM-DDTHH:MM:SS+HH:MM`."""
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz) if tz else d.astimezone()
    return d.isoformat(timespec="seconds")


def load_proposals(root):
    """{slug: [rows, oldest first]} from .cache/summaries/proposals.jsonl."""
    path = os.path.join(root, ".cache", "summaries", "proposals.jsonl")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("slug"):
                    out.setdefault(r["slug"], []).append(r)
    except OSError:
        pass
    return out


def _generated(fm, owner, proposals, tz, report, slug):
    """The `generated: {...}` line for a page's summary, or None when it has no summary."""
    by_me = fm.get("summary_by") == "me"
    at = None
    if by_me:
        by = f"human:{owner}"
    else:
        summary = fmlib.unquote(fm.get("summary") or fm.get("description"))
        row = next((r for r in reversed(proposals.get(slug, []))
                    if r.get("summary") == summary and r.get("summary_from") == fm.get("summary_from")), None)
        by = f"{PRODUCER}/{(row or {}).get('model') or UNKNOWN_MODEL}"
        at = _with_offset(row.get("ts"), tz) if row and row.get("ts") else None
        if row is None:
            report["no_proposal"].append(slug)
    if at is None:
        report["no_at"].append(slug)
    return "generated: {by: " + fmlib.scalar(by) + (", at: " + at if at else "") + "}"


# -- one page ----------------------------------------------------------------------------------------------------
def _split_head(text):
    """(frontmatter block with its closing `---` line, rest) of a page; ('', text) when there is no block."""
    if not text.startswith(("---\n", "---\r\n")):
        return "", text
    close = text.find("\n---", 3)
    if close == -1:
        return "", text
    nl = text.find("\n", close + 1)
    cut = len(text) if nl == -1 else nl + 1
    return text[:cut], text[cut:]


def migrate_page(text, slug, ctx, report):
    """The page text in the new shape (same text when nothing changes). A CRLF frontmatter block is migrated as LF and
    written back as CRLF; the body is never touched. A block mixing both is refused by `apply` before any write."""
    head, body = _split_head(text)
    lf_head, crlf = fmlib.to_lf(head)
    probe = lf_head + body.replace("\r\n", "\n")        # the body is read (first heading), never rewritten
    new = _migrate_page(probe, slug, ctx, report)
    if new == probe:
        return text
    new_head = _split_head(new)[0]
    return fmlib.from_lf(new_head, crlf) + body


def _migrate_page(text, slug, ctx, report):
    fm, body = fmlib.parse(text)
    if fm is None:
        return text
    inner = text[4:text.find("\n---", 3)] if text.startswith("---\n") else None
    if inner is None:
        return text
    entries = split_entries(inner)
    rest = text[4 + len(inner):]                      # "\n---..." onward, untouched

    # status -> maturity, OKF status: draft at depth listed
    legacy_status = "status" in fm and str(fm["status"]) not in OKF_STATUS and "maturity" not in fm
    if legacy_status:
        i = _find(entries, "status")
        entries[i] = ["maturity", [re.sub(r"^status:", "maturity:", entries[i][1][0], count=1)] + entries[i][1][1:]]
    if fm.get("depth") == "listed" and ("status" not in fm or legacy_status):
        _put_after(entries, ("maturity", "depth"), "status", "status: draft")

    # summary -> description
    if "summary" in fm and "description" not in fm:
        i = _find(entries, "summary")
        entries[i] = ["description", [re.sub(r"^summary:", "description:", entries[i][1][0], count=1)] + entries[i][1][1:]]

    # summary_by -> generated
    has_summary = "summary" in fm or "description" in fm
    if "generated" not in fm and (has_summary or "summary_by" in fm):
        if fm.get("summary_by") == "me" and not ctx["owner"]:
            raise RuntimeError("kb.toml has no `[kb] owner = \"<id>\"`: needed to write `generated: {by: human:<id>}` "
                               f"for the user's own summary (wiki/{slug}.md has `summary_by: me`)")
        if fm.get("summary_by") not in (None, "me", ""):
            report["odd_summary_by"].append(slug)
        line = _generated(fm, ctx["owner"], ctx["proposals"], ctx["tz"], report, slug)
        j = _find(entries, "summary_by")
        if j is not None:
            entries[j] = ["generated", [line]]
        else:
            _put_after(entries, ("summary_from", "description", "summary"), "generated", line)
    elif "summary_by" in fm:
        entries.pop(_find(entries, "summary_by"))

    # date -> created
    if "date" in fm and "created" not in fm:
        i = _find(entries, "date")
        d = fmlib.unquote(fm["date"]) if isinstance(fm["date"], str) else None
        if d is None:
            report["date_kept"].append((slug, str(fm["date"])))
        elif not d:
            entries.pop(i)                          # an empty `date:` (template placeholder) says nothing
        elif DATE.match(d):
            entries[i] = ["created", [f"created: {d}T00:00:00Z"] + entries[i][1][1:]]
        else:
            report["date_kept"].append((slug, str(fm["date"])))

    # title from the first heading
    h1 = fmlib.first_heading(text)
    if "title" not in fm:
        if h1:
            _put_after(entries, ("layer", "type"), "title", "title: " + fmlib.quote(h1))
        else:
            report["no_heading"].append(slug)
    elif h1 and fmlib.unquote(fm["title"]) != h1:
        report["title_differs"].append((slug, fmlib.unquote(fm["title"]), h1))

    # sources -> objects with a resource
    srcs = fm.get("sources", [])
    srcs = [srcs] if isinstance(srcs, (str, dict)) else list(srcs or [])
    think = str(fm.get("source") or "")
    if fm.get("type") == "distilled-think" and think.startswith("think:") and not srcs:
        srcs = [think]                              # the think-note citation moves from `source:` into `sources`
        entries.pop(_find(entries, "source"))
    new_srcs, changed = [], False
    for item in srcs:
        if isinstance(item, dict):
            new_srcs.append(item.get("resource") or "")
            continue
        item = fmlib.unquote(str(item))
        changed = True
        if not item:
            continue
        if item.startswith(("raw/", "think/")):
            report["source_dropped"].append((slug, item))      # never a resource into raw/ or think/
            continue
        slug_ref = links.page_slug(item)
        if slug_ref is None:
            new_srcs.append(item)                   # think:<note>.md, a URL, papers/x: a descriptor kept as text
            if not re.match(r"^(think:|https?://)", item):
                report["source_text"].append((slug, item))
            continue
        hit = links.resolve_slug(slug_ref, ctx["slugs"], ctx["aliases"], ctx["mentions"])
        if hit is None:
            report["source_unresolved"].append((slug, item))
        new_srcs.append(links.page_path(hit or slug_ref))
    url = fmlib.unquote(str(fm.get("url") or ""))
    if fm.get("layer") == "source" and HTTP.match(url) and url not in new_srcs:
        new_srcs.insert(0, url)
        changed = True
    new_srcs = [r for r in dict.fromkeys(new_srcs) if r]
    if changed:
        line = fmlib.sources_line(new_srcs)
        i = _find(entries, "sources")
        if i is not None:
            entries[i] = ["sources", [line]]
        else:
            _put_after(entries, ("url", "raw", "layer", "type"), "sources", line)

    # related -> page paths
    if "related" in fm:
        rel = fm["related"]
        rel = [rel] if isinstance(rel, str) and rel else list(rel or [])
        out, changed = [], False
        for r in rel:
            r = fmlib.unquote(str(r))
            s = links.page_slug(r)
            if s is None:
                out.append(r)
                report["related_text"].append((slug, r))
                continue
            hit = links.resolve_slug(s, ctx["slugs"], ctx["aliases"], ctx["mentions"])
            if hit is None:
                report["related_unresolved"].append((slug, s))
            path = links.page_path(hit or s)
            changed |= path != r
            out.append(path)
        if changed:
            entries[_find(entries, "related")] = ["related", [fmlib.related_line(list(dict.fromkeys(out)))]]

    new_inner = "\n".join(line for _k, lines in entries for line in lines)
    return "---\n" + new_inner + rest if new_inner != inner else text


def _excalidraw(text, rel, report):
    """Add `type: excalidraw` to a plugin file with frontmatter and no type; report one that cannot take it."""
    if text.startswith("---\r\n"):
        new = _excalidraw_lf("---\n" + text[5:], rel, report)
        return text if new == "---\n" + text[5:] else "---\r\ntype: excalidraw\r\n" + text[5:]
    return _excalidraw_lf(text, rel, report)


def _excalidraw_lf(text, rel, report):
    fm, _body = fmlib.parse(text)
    if fm is None:
        report["no_type"].append((rel, "no frontmatter block"))
        return text
    if str(fm.get("type") or "").strip():
        return text
    if not rel.endswith(".excalidraw.md"):
        report["no_type"].append((rel, "frontmatter without type, not an excalidraw drawing"))
        return text
    return "---\ntype: excalidraw\n" + text[4:]


# -- the vault ---------------------------------------------------------------------------------------------------
def apply(root, dry_run=False, tz=None):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    report = {k: [] for k in ("no_at", "no_proposal", "odd_summary_by", "date_kept", "no_heading", "title_differs",
                              "source_unresolved", "source_text", "source_dropped", "related_unresolved", "related_text", "no_type")}
    report["changed"] = []
    if not os.path.isdir(wiki):
        return report
    flat, others = {}, []
    for dirpath, _dirs, files in os.walk(wiki):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            if dirpath == wiki:
                flat[fn[:-3]] = (path, text)
            else:
                others.append((path, text))
    mixed = fmlib.mixed_line_ends([(p, _split_head(t)[0]) for p, t in [*flat.values(), *others]])
    if mixed:
        raise RuntimeError("these pages mix CRLF and LF line ends in their frontmatter; make them one or the other first, nothing was written: "
                           + ", ".join(os.path.relpath(p, root) for p in mixed[:10]) + (" …" if len(mixed) > 10 else ""))
    fms = {s: (fmlib.parse(t.replace("\r\n", "\n"))[0] or {}) for s, (_p, t) in flat.items()}
    ctx = {"slugs": set(flat), "aliases": links.alias_map(fms),
           "mentions": links.mention_map(os.path.join(root, "meta", "aliases.tsv")),
           "owner": owner_of(root), "proposals": load_proposals(root), "tz": tz}
    todo = {}
    for slug, (path, text) in flat.items():
        new = migrate_page(text, slug, ctx, report)
        if new != text:
            todo[path] = new
    for path, text in others:
        new = _excalidraw(text, os.path.relpath(path, root), report)
        if new != text:
            todo[path] = new
    for path, new in todo.items():
        report["changed"].append(os.path.relpath(path, root))
        if not dry_run:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
    _print(report, dry_run)
    return report


def _print(r, dry_run):
    print(f"okf frontmatter: {len(r['changed'])} pages {'would change' if dry_run else 'changed'}")
    for key in ("no_at", "no_proposal", "odd_summary_by", "no_heading"):
        if r[key]:
            print(f"  {key}: {len(r[key])}" + (f" {r[key][:8]}" if len(r[key]) <= 8 else ""))
    for key in ("related_unresolved", "source_dropped", "source_unresolved", "source_text", "related_text", "date_kept", "title_differs",
                "no_type"):
        if r[key]:
            print(f"  {key}: {len(r[key])} e.g. {r[key][:5]}")


if __name__ == "__main__":
    from kb_distillery.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        apply(a.root, dry_run=a.dry_run)
    except RuntimeError as e:
        sys.exit(f"error: {e}")

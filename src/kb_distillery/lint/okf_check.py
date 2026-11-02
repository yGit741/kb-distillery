#!/usr/bin/env python3
"""okf-check: the blocking Open Knowledge Format v0.2 gate. Exits 1 on any finding, 0 on none (--json always exits 0).

    python -m kb_distillery.lint.okf_check [--kb ID] [--json] [--only=wiki/a.md ...]

`wiki/` is the bundle root. `index.md` and `log.md` are OKF reserved files, not pages: they are not counted, need no
`type` and the other frontmatter rules skip them; their links are still checked, and `log.md` (a historical record
whose old entries quote `[[...]]` text) is exempt from the wikilink rule only. A kb commit (`ops`) and the engine
`ship` gates (on examples/demo) run it on the whole bundle; there is no bypass. A kb commit checks only the pages it
changes (`--only`), so one bad page never blocks an unrelated step, and undo/restore (the way out) are exempt.

Rules:
  type        every non-reserved page has a non-empty `type`
  status      `status`, when present, is draft, stable or deprecated
  sources     every `sources` entry is a mapping with a `resource`
  timestamp   `created`, `updated`, `generated.at` carry a UTC offset
  wikilink    no `[[...]]` left in a page body (code, math, comments and `## My notes` excluded)
  link        every markdown link to a page resolves, and its `#anchor` matches a heading
  boundary    no link into `raw/` or `think/`
"""
import datetime
import json
import os
import re
import sys
from collections import Counter

from kb_distillery.vault import links as page_links

STATUSES = {"draft", "stable", "deprecated"}
RESERVED = {"index.md", "log.md"}                     # OKF reserved names: no frontmatter rules
SKIP_DIRS = {"raw", "think", "meta", "digest", ".git"}
CODE = re.compile(r"^\s*(?:>\s*)*(```|~~~).*?^\s*(?:>\s*)*\1[^\n]*$|`[^`\n]+`", re.M | re.S)
MD_LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
OFFSET = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def slugify(heading):
    """GitHub-style anchor of a heading."""
    s = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s", "-", s)


def front_matter(text):
    """(dict or None when absent/unparseable, body)."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    import yaml
    try:
        fm = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None, text[end + 5:]
    return (fm if isinstance(fm, dict) else None), text[end + 5:]


def has_offset(value):
    if isinstance(value, datetime.datetime):
        return value.tzinfo is not None
    if isinstance(value, datetime.date):
        return False
    return bool(OFFSET.search(str(value).strip()))


def pages(root):
    """(relative path, absolute path) of every markdown file of the bundle, `wiki/` (reserved files included)."""
    bundle = os.path.join(root, "wiki")
    for dirpath, dirs, files in os.walk(bundle):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.endswith(".md"):
                path = os.path.join(dirpath, name)
                yield os.path.relpath(path, root), path


def is_reserved(rel):
    return os.path.basename(rel) in RESERVED


def check_page(rel, text, root):
    """List of (rule, message) for one page."""
    out = []
    fm, body = front_matter(text)
    if not is_reserved(rel):
        if fm is None or not str(fm.get("type") or "").strip():
            out.append(("type", "no parseable non-empty `type`"))
        if fm:
            if "status" in fm and str(fm["status"]) not in STATUSES:
                out.append(("status", f"status {fm['status']!r} is not draft, stable or deprecated"))
            srcs = fm.get("sources") or []
            if not isinstance(srcs, list):
                out.append(("sources", f"`sources` is not a list: {srcs!r}"))
                srcs = []
            for entry in srcs:
                if not (isinstance(entry, dict) and entry.get("resource")):
                    out.append(("sources", f"source entry without `resource`: {entry!r}"))
            gen = fm.get("generated")
            stamps = {k: fm[k] for k in ("created", "updated") if k in fm}
            if isinstance(gen, dict) and "at" in gen:
                stamps["generated.at"] = gen["at"]
            for key, value in stamps.items():
                if not has_offset(value):
                    out.append(("timestamp", f"{key} {value!r} has no UTC offset"))
    if os.path.basename(rel) != "log.md":
        for found in sorted(set(page_links.leftover_wikilinks(body))):
            out.append(("wikilink", found))
    own = {slugify(h) for h in HEADING.findall(CODE.sub("", body))}
    for href in MD_LINK.findall(page_links.prose(body)):      # not in code, math, comments or `## My notes`
        if re.match(r"[a-z][a-z0-9+.-]*:", href, re.I):          # http:, mailto:
            continue
        path, _, anchor = href.partition("#")
        if path.startswith("/"):
            target = path.lstrip("/")
        elif path:
            target = os.path.normpath(os.path.join(os.path.dirname(rel), path))
        else:
            target = rel
        top = target.split("/", 1)[0]
        if top in ("raw", "think"):
            out.append(("boundary", f"link into {top}/: {href}"))
            continue
        full = os.path.join(root, target)
        if not os.path.isfile(full):
            out.append(("link", f"unresolved: {href}"))
        elif anchor and target.endswith(".md"):
            if target == rel:
                heads = own
            else:
                with open(full, encoding="utf-8") as f:
                    heads = {slugify(h) for h in HEADING.findall(CODE.sub("", front_matter(f.read())[1]))}
            if anchor.lower() not in heads:
                out.append(("link", f"unresolved anchor: {href}"))
    return out


def check(root, only=None):
    """{relative path: [(rule, message)]} for pages with findings, and the page count. `only` (relative paths) limits
    the pages checked to those; links still resolve against the whole bundle."""
    findings, count = {}, 0
    only = None if only is None else {os.path.normpath(p) for p in only}
    for rel, path in pages(root):
        if only is not None and os.path.normpath(rel) not in only:
            continue
        count += not is_reserved(rel)
        try:
            with open(path, encoding="utf-8") as f:
                found = check_page(rel, f.read(), root)
        except (OSError, ValueError, TypeError) as e:       # a bad page is a finding, never a crash
            found = [("read", f"{type(e).__name__}: {e}")]
        if found:
            findings[rel] = found
    return findings, count


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    from kb_distillery.config.paths import vault_root
    root = vault_root()
    only = [a[len("--only="):] for a in argv if a.startswith("--only=")] or None   # a commit checks the pages it changes
    try:
        findings, count = check(root, only)
    except Exception as e:                                  # a gate that cannot run must block, not pass
        print(f"okf-check: could not run: {type(e).__name__}: {e}")
        return 1
    totals = Counter(rule for found in findings.values() for rule, _ in found)
    if as_json:
        print(json.dumps({"pages": count, "findings": {p: [list(f) for f in fs] for p, fs in findings.items()},
                          "totals": dict(totals)}, indent=1))
        return 0
    for rel, found in sorted(findings.items()):
        for rule, message in found:
            print(f"ERROR okf-check: {rel}: {rule}: {message}")
    summary = ", ".join(f"{n} {rule}" for rule, n in sorted(totals.items())) or "none"
    print(f"okf-check: {count} pages, {sum(totals.values())} findings ({summary})")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

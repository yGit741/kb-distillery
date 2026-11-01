"""Turn a writer CLI run into exactly one knowledge commit.

`python -m kb_distillery.ingest …` and `python -m kb_distillery.distill …` go through `run()`: it
records which knowledge files are dirty, runs the command, and commits only the
files the command changed — never your pre-existing edits or other sessions'
files. `--no-commit` (or KB_OPS_DISABLE=1, or --dry-run) skips the commit.
"""
import os
import sys

from . import core

# (subcommand, sub-subcommand or None) -> (op, already linted by the command)
INGEST = {
    ("scrap", None): ("import", True),
    ("scrap-mail", None): ("import", True),
    ("scrap-gdrive", None): ("import", True),
    ("scrap-wordpress", None): ("import", True),
    ("scrap-youtube", None): ("import", True),
    ("catalog", None): ("catalog", True),
    ("drain-inbox", None): ("catalog", True),
    ("finalize", None): ("digest", True),
    ("backfill-authors", None): ("refine", False),
    ("index-researcher", "finalize"): ("catalog", True),
    ("index-researcher", "relink"): ("refine", False),
}
INGEST_BEGIN = {("easy-digest", None): "digest", ("video-digest", None): "digest"}  # agent keeps editing; skill ends with `ops commit`
DISTILL = {("apply", None): ("distill", True)}

# kb summaries are noun phrases — the op in kb(<op>) is already the verb
SUMMARY = {
    "scrap": "{target} into the inbox",
    "scrap-mail": "mail thread {target} into the inbox",
    "scrap-gdrive": "{n} Google Drive files into the inbox",
    "scrap-wordpress": "{n} WordPress clips and figures into the inbox",
    "scrap-youtube": "video {target} into the inbox",
    "drain-inbox": "inbox drain ({n} items)",
    "backfill-authors": "authors and arXiv URLs ({n} pages)",
    "index-researcher": "{target} researcher profile",
    "apply": "{target} distill",
}


def _positional(argv):
    return [a for a in argv if not a.startswith("-")]


def _digest_slug(pos):
    """The digested page's slug from the session's plan.json (finalize <session>)."""
    if len(pos) < 2 or pos[0] != "finalize":
        return None
    try:
        import json
        with open(os.path.join(core.ROOT, "meta", ".ingest", pos[1], "plan.json"), encoding="utf-8") as f:
            return json.load(f).get("wiki_slug") or None
    except (OSError, ValueError):
        return None


def _target(paths, pos):
    slug = _digest_slug(pos)
    if slug:
        return slug
    for p in paths:
        if p.startswith("wiki/") and p.endswith(".md") and "/distilled-think-" not in p:
            return os.path.basename(p)[:-3]
    for p in paths:
        parts = p.split("/")
        if p.startswith(("raw/inbox/video-", "raw/videos/")) and len(parts) > 3:
            return parts[2].removeprefix("video-")           # a video bundle is named by its folder
    for p in paths:
        if p.startswith("raw/"):
            return os.path.splitext(os.path.basename(p))[0]
    return pos[-1] if len(pos) > 1 else (pos[0] if pos else "kb")


def _items(paths):
    """Cataloged items, not changed paths: a paper is a raw PDF plus its wiki stub (one item),
    and corpus.tsv, index.md and the log are bookkeeping. Falls back to the path count."""
    from kb_distillery.core.schema import strip_prefix
    stems = set()
    for p in paths:
        if p.startswith("raw/"):
            stems.add(os.path.splitext(os.path.basename(p))[0])
        elif p.startswith("wiki/") and p.endswith(".md"):
            stems.add(strip_prefix(os.path.basename(p)[:-3]))
    return len(stems) or len(paths)


def run(cli_main, argv=None, table=INGEST, begin_table=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    skip = "--no-commit" in argv or "--dry-run" in argv or os.environ.get("KB_OPS_DISABLE") == "1"
    argv = [a for a in argv if a != "--no-commit"]
    pos = _positional(argv)
    key = (pos[0] if pos else None, pos[1] if len(pos) > 1 else None)
    entry = table.get(key) or table.get((key[0], None))
    begin_op = (begin_table or {}).get((key[0], None))
    if skip or not (entry or begin_op):
        return cli_main(argv)

    if begin_op:
        try:
            target = pos[1] if len(pos) > 1 else key[0]
            parts = target.replace(os.sep, "/").split("/")
            # a video bundle's item is always video.md: name the session after its folder
            name = parts[-2] if len(parts) > 3 and parts[:2] == ["raw", "videos"] else \
                os.path.splitext(os.path.basename(target))[0]
            # no summary: the subject becomes the page title, the tier goes in a KB-Tier trailer
            core.begin(begin_op, name, root=core.ROOT)
        except core.OpsError as e:
            print(f"ops: no session opened — {e}")
        return cli_main(argv)

    before = core.knowledge_state(core.ROOT)
    rc = cli_main(argv)
    if rc not in (0, None):
        return rc
    paths = core.changed_since(before, core.ROOT)
    if key[0] == "apply":  # include the distilled-think draft written earlier by propose/revise
        paths += [p for p in core.changed_paths(core.ROOT)["knowledge"]
                  if p.startswith("wiki/distilled-think-") and p not in paths]
    if not paths:
        return rc
    op, linted = entry
    target = _target(paths, pos)
    n = _items(paths) if key[0] == "drain-inbox" else len(paths)
    summary = SUMMARY.get(key[0], "{target}").format(target=core.short_title(target), n=n)
    try:
        core.commit_op(op, target, summary, paths=paths, lint=not linted, root=core.ROOT)
    except core.OpsError as e:
        print(f"ops: not committed — {e}\n     (label saved; `pixi run ops -- sync` or the nightly sync will commit it)")
    return rc

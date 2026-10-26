"""CLI: python3 -m kb.ingest <command> [args]"""
import argparse
import json
import os
import sys

from . import net, extract, map, draft, session, scrap, mail, catalog, easy_digest, resolve as resolve_mod, researcher
from . import gdrive
from . import book as book_mod
from . import backfill as backfill_mod
from .paths import INGEST_ROOT, ROOT, load_session, session_dir


def _add_scope_flags(sp):
    sp.add_argument("--part", default=None, metavar="N",
                    help="row number of the book's partition, as printed by `toc`")
    sp.add_argument("--pages", default=None, metavar="A-B",
                    help="page range to read, 1-based inclusive (e.g. 19-42)")
    sp.add_argument("--section", default=None, metavar="SPEC",
                    help="chapter number, #index or title text from `toc`")
    sp.add_argument("--whole-book", action="store_true",
                    help="skip the book gate and skim the first 25 pages")
    sp.add_argument("--row", default=None, metavar="N",
                    help="row of a course/series Contents table; pass the hub slug as raw_path")


def cmd_status(_args):
    if not os.path.isdir(INGEST_ROOT):
        print("no sessions")
        return 0
    for sha in sorted(os.listdir(INGEST_ROOT)):
        sp = os.path.join(INGEST_ROOT, sha, "session.json")
        if not os.path.isfile(sp):
            continue
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        print(f"{sha}\t{s.get('status')}\t{s.get('raw')}")
    return 0


def cmd_backlog(_args):
    from .backlog import shallow_paper_slugs
    shallow = shallow_paper_slugs()
    print(f"shallow digests ({len(shallow)}):")
    for s in shallow[:50]:
        print(f"  {s}")
    if len(shallow) > 50:
        print(f"  ... and {len(shallow) - 50} more")
    return 0


def _row_scope(args):
    """`full-digest <hub> --row N`, or a raw file listed on a course/series table: the unit is
    the row (all its files), and finalize ticks it. Rewrites args.raw_path to the row's first file."""
    from . import course
    if getattr(args, "row", None):
        try:
            row = course.resolve_row(args.raw_path, args.row)
        except ValueError as e:
            print(e, file=sys.stderr)
            return None, 2
        hub, n = args.raw_path, int(str(args.row).lstrip("#"))
    else:
        hub, n, row = course.hub_row_for_raw(args.raw_path.replace(os.sep, "/").lstrip("./"))
        if row is None:
            return {}, 0
    args.raw_path = row["raws"][0]
    return {"hub": hub, "row": n, "raws": row["raws"], "label": row["title"]}, 0


def _scope(args):
    """Resolve --row/--pages/--section against the raw file; returns (scope_dict, error_code)."""
    row_scope, code = _row_scope(args)
    if code or row_scope:
        return row_scope, code
    raw_rel = book_mod.verify_for_scope(args.raw_path)
    raw_abs = os.path.join(ROOT, raw_rel)
    rng, label, blocked = book_mod.gate(
        raw_rel, raw_abs,
        getattr(args, "pages", None), getattr(args, "section", None),
        getattr(args, "whole_book", False), getattr(args, "part", None))
    if blocked:
        print(blocked, file=sys.stderr)
        return None, 2
    if not rng:
        return {}, 0
    scope = {"pages": list(rng), "label": label}
    if not getattr(args, "whole_book", False) and book_mod.is_book(raw_abs):
        scope["book"] = book_mod.hub_slug(raw_rel)     # → a type: part page on its book hub
    return scope, 0


def cmd_toc(args):
    """The book's partition (from its hub page, or proposed); --depth 2+ adds the PDF outline."""
    raw_rel = book_mod.verify_for_scope(args.raw_path)
    raw_abs = os.path.join(ROOT, raw_rel)
    rows, total, hub_rel = book_mod.partition_for(raw_rel, raw_abs)
    if rows:
        print(book_mod.format_partition(rows, total, raw_rel, hub_rel))
    if args.depth > 1 or not rows:
        entries, total, source = book_mod.read_toc(raw_abs)
        if not entries:
            print(f"{raw_rel} — {total} pages, no readable table of contents.", file=sys.stderr)
            return 0 if rows else 1
        print("\nPDF outline:\n" + book_mod.format_toc(entries, total, source, raw_rel,
                                                        depth=args.depth))
    return 0


def cmd_full_digest(args):
    scope, code = _scope(args)
    if code:
        return code
    sha = session.begin(args.raw_path, depth="full", scope=scope)
    print(f"\nfull-digest session {sha} — next: extract → claims.json → map → draft → finalize")
    print("See skills/full-digest/SKILL.md")
    return 0


def cmd_deep_digest(args):
    if not args.confirm_heavy:
        print("deep-digest requires --confirm-heavy (heavy LLM tier ~25-40k+ tokens)", file=sys.stderr)
        return 1
    scope, code = _scope(args)
    if code:
        return code
    sha = session.begin(args.raw_path, depth="deep", scope=scope)
    print(f"\ndeep-digest session {sha} — extended neighbor linking in plan.json")
    print("See skills/deep-digest/SKILL.md")
    return 0


def cmd_resolve(args):
    result = resolve_mod.resolve(args.query)
    if args.json:
        print(json.dumps({"status": result.status, "query": result.query, "matches": result.matches},
                         indent=2))
    else:
        print(resolve_mod.format_human(result))
    return resolve_mod.exit_code(result)


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb.ingest", description="Staged vault ingest pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scrap", help="download/copy to raw/inbox/ (0 LLM)")
    sc.add_argument("source")
    sc.add_argument("--type", choices=["articles", "notes", "slides", "web", "blog"], default=None)
    sc.add_argument("--force", action="store_true", help="skip dedup checks")

    sw = sub.add_parser("scrap-wordpress", help="every post of a WordPress.com blog + its figures → raw/inbox/ (0 LLM)")
    sw.add_argument("site", help="gilkalai.wordpress.com or any URL on the blog")
    sw.add_argument("--prefix", default=None, help="clip filename prefix, normally the hub's short: (default: site name)")
    sw.add_argument("--since", default=None, help="YYYY-MM-DD: only posts published on/after this date")
    sw.add_argument("--limit", type=int, default=None, help="stop after N posts (a trial run)")
    sw.add_argument("--no-images", action="store_true", help="keep figures as remote links, download nothing")
    sw.add_argument("--force", action="store_true", help="re-pull posts already in the vault")

    sy = sub.add_parser("scrap-youtube", help="a YouTube lecture/video → raw/inbox/video-<name>/ bundle (0 LLM unless --read)")
    sy.add_argument("url")
    sy.add_argument("--tier", choices=["transcript", "vibe", "frames"], default="vibe",
                    help="transcript only · + 1-3 representative frames (default) · full frame selection")
    sy.add_argument("--read", action="store_true", help="frames tier: a Claude read of each kept frame (LLM, ~2k tokens/frame)")
    sy.add_argument("--per-hour", type=int, default=30, help="frames tier: frame budget per video hour")
    sy.add_argument("--model", default="sonnet", help="model for --read")
    sy.add_argument("--force", action="store_true", help="scrap again although the video is in the vault")

    sm = sub.add_parser("scrap-mail", help="parse .mbox/.eml export, or fetch via IMAP, to raw/inbox/mail-.../ (0 LLM)")
    sm.add_argument("source", nargs="?", default=None, help="path to a local .mbox or .eml export")
    sm.add_argument("--imap-thread", default=None,
                     help="Gmail thread ID (hex, from the Gmail API/MCP) to fetch directly via IMAP")
    sm.add_argument("--account", default=None, help="Gmail address for --imap-thread")
    sm.add_argument("--slug", default=None, help="override the thread folder slug")
    sm.add_argument("--force", action="store_true", help="skip dedup checks / overwrite")

    sg = sub.add_parser("scrap-gdrive", help="pull a mounted Google Drive folder to raw/inbox/ (0 LLM)")
    sg.add_argument("--folder", default=gdrive.DEFAULT_FOLDER, help="My Drive folder name")
    sg.add_argument("--ext", default=",".join(gdrive.DEFAULT_EXTS), help="comma-separated extensions")
    sg.add_argument("--dry-run", action="store_true", help="preview only; downloads nothing")
    sg.add_argument("--warn-mb", type=int, default=gdrive.DEFAULT_WARN_MB, help="warn above this size")
    sg.add_argument("--account", default=None, help="email, when several Drive accounts are mounted")
    sg.add_argument("--force", action="store_true", help="skip dedup checks")

    rv = sub.add_parser("resolve", help="lookup existing raw/wiki entry (0 LLM)")
    rv.add_argument("query")
    rv.add_argument("--json", action="store_true")

    cat = sub.add_parser("catalog", help="inbox → raw/<format>/ + membership (0 LLM)")
    cat.add_argument("inbox_path")
    cat.add_argument("--collection", "--course", default="",
                     help="hub or person slug the file belongs to (course-…, book-…, nadav-cohen)")
    cat.add_argument("--format", default=None, choices=catalog.FORMATS,
                     help="override detection (e.g. presentations for a slide-deck PDF)")
    cat.add_argument("--title", default=None, help="row title on the hub's Contents table")

    di = sub.add_parser("drain-inbox", help="catalog all inbox files (0 LLM)")
    di.add_argument("--collection", "--course", default="")
    di.add_argument("--match", default="", help="only inbox entries whose name starts with this prefix")

    ed = sub.add_parser("easy-digest", help="abstract skim (light LLM)")
    ed.add_argument("target")
    ed.add_argument("--into", default=None, help="existing page that covers this clip too (a series of numbered posts)")
    ed.add_argument("--no-tick", action="store_true", help="batch: leave the hub row for the orchestrator")
    ed.add_argument("--no-lint", action="store_true", help="batch: lint once at the end instead")

    sc = sub.add_parser("easy-spotcheck", help="~5%% of easy digests re-read by a stronger model (0 LLM here)")
    sc_sub = sc.add_subparsers(dest="sc_cmd", required=True)
    sc_pick = sc_sub.add_parser("pick", help="which of these slugs to re-read (deterministic)")
    sc_pick.add_argument("slugs", nargs="+")
    sc_log = sc_sub.add_parser("log", help="record a re-read verdict")
    sc_log.add_argument("slug")
    sc_log.add_argument("--verdict", required=True, choices=("ok", "fix"))
    sc_log.add_argument("--model", default="sonnet")
    sc_log.add_argument("--note", default="")
    sc_sub.add_parser("status", help="verdict counts")
    fd = sub.add_parser("full-digest", help="standard paper note (medium LLM)")
    fd.add_argument("raw_path")
    _add_scope_flags(fd)

    dd = sub.add_parser("deep-digest", help="thesis-critical digest (heavy LLM)")
    dd.add_argument("raw_path")
    dd.add_argument("--confirm-heavy", action="store_true")
    _add_scope_flags(dd)

    bf = sub.add_parser("backfill-authors", help="fill full author lists from arXiv (0 LLM)")
    bf.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    bf.add_argument("--fix-urls", action="store_true",
                    help="re-find pages whose url: is the wrong arXiv paper, by title search")

    rf = sub.add_parser("refetch-raw", help="replace paper PDFs stamped with another arXiv id than "
                        "their page cites (wrong downloads; 0 LLM)")
    rf.add_argument("--apply", action="store_true", help="download and replace; default lists only")

    tc = sub.add_parser("toc", help="a book's page partition (or a proposed one) + outline (0 LLM)")
    tc.add_argument("raw_path")
    tc.add_argument("--depth", type=int, default=1, help="1 = chapters only, 2 = include sections")

    b = sub.add_parser("begin", help="open ingest session for raw file")
    b.add_argument("raw_path")
    _add_scope_flags(b)

    e = sub.add_parser("extract", help="extract PDF text; validate claims.json")
    e.add_argument("session")

    m = sub.add_parser("map", help="build plan.json from claims")
    m.add_argument("session")

    d = sub.add_parser("draft", help="render wiki markdown to staging/")
    d.add_argument("session")

    f = sub.add_parser("finalize", help="promote staging, lint, close session")
    f.add_argument("session")

    a = sub.add_parser("abort", help="rollback session")
    a.add_argument("session")

    sub.add_parser("status", help="list sessions")
    sub.add_parser("backlog", help="list shallow paper digests")

    ir = sub.add_parser("index-researcher", help="index researcher bib + catalog star papers (0 LLM)")
    ir_sub = ir.add_subparsers(dest="ir_cmd", required=True)
    ir_sub.add_parser("status", help="list open researcher sessions")
    ir_b = ir_sub.add_parser("begin", help="fetch Semantic Scholar bibliography")
    ir_b.add_argument("query", help="name, Scholar URL, or SS author id")
    ir_b.add_argument("--author-id", help="Semantic Scholar author id when the name is ambiguous")
    ir_b.add_argument("--slug", help="person page slug to write (default: existing page or the name)")
    ir_v = ir_sub.add_parser("verify", help="print verify status for manifest")
    ir_v.add_argument("slug")
    ir_f = ir_sub.add_parser("finalize", help="write person page + catalog star papers")
    ir_f.add_argument("slug")
    ir_a = ir_sub.add_parser("abort", help="delete researcher session staging")
    ir_a.add_argument("slug")
    ir_r = ir_sub.add_parser("relink", help="turn dangling bibliography links into titles (0 LLM)")
    ir_r.add_argument("slug", help="person slug, e.g. gil-kalai")
    ir_r.add_argument("--dry-run", action="store_true")

    args = p.parse_args(argv)
    net.install()           # one TLS trust setup (truststore / keychain) for every HTTP call below

    if args.cmd == "scrap":
        try:
            scrap.scrap(args.source, kind=args.type, force=args.force)
        except resolve_mod.DuplicateBlocked:
            return 1
        return 0
    if args.cmd == "scrap-gdrive":
        try:
            return gdrive.scrap_gdrive(folder=args.folder, exts=args.ext.split(","),
                                       dry_run=args.dry_run, warn_mb=args.warn_mb,
                                       account=args.account, force=args.force)
        except resolve_mod.DuplicateBlocked:
            return 1
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
    if args.cmd == "scrap-mail":
        try:
            if args.imap_thread:
                if not args.account:
                    print("--imap-thread requires --account", file=sys.stderr)
                    return 1
                mail.scrap_imap_thread(args.imap_thread, args.account,
                                        slug=args.slug, force=args.force)
            elif args.source:
                mail.scrap_mail(args.source, slug=args.slug, force=args.force)
            else:
                print("scrap-mail requires a source path or --imap-thread", file=sys.stderr)
                return 1
        except resolve_mod.DuplicateBlocked:
            return 1
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    if args.cmd == "scrap-youtube":
        from .youtube import bundle
        try:
            bundle.scrap_youtube(args.url, tier=args.tier, force=args.force, read=args.read,
                                 per_hour=args.per_hour, model=args.model)
        except resolve_mod.DuplicateBlocked:
            return 1
        except Exception as e:                       # yt-dlp raises its own DownloadError
            print(f"scrap-youtube failed: {e}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "scrap-wordpress":
        from . import wordpress
        try:
            wordpress.scrap_wordpress(args.site, prefix=args.prefix, since=args.since, limit=args.limit,
                                      images=not args.no_images, force=args.force)
        except (ValueError, OSError) as e:
            print(f"scrap-wordpress failed: {e}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "resolve":
        return cmd_resolve(args)
    if args.cmd == "catalog":
        try:
            catalog.catalog(args.inbox_path, collection=args.collection, fmt=args.format,
                            title=args.title)
        except (ValueError, NotImplementedError, OSError) as e:
            print(f"catalog failed: {e}\n(logged — the dashboard's Ingestion status shows it)", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "drain-inbox":
        catalog.drain_inbox(collection=args.collection, match=args.match)
        return 0
    if args.cmd == "easy-digest":
        easy_digest.easy_digest(args.target, into=args.into, tick=not args.no_tick, lint=not args.no_lint)
        return 0
    if args.cmd == "easy-spotcheck":
        from . import spotcheck
        if args.sc_cmd == "pick":
            for slug in spotcheck.pick(args.slugs):
                print(slug)
        elif args.sc_cmd == "log":
            row = spotcheck.log(args.slug, args.verdict, model=args.model, note=args.note)
            print(f"logged {row['slug']}: {row['verdict']} ({row['model']})")
        else:
            print("  ".join(f"{k} {v}" for k, v in spotcheck.status().items()))
        return 0
    if args.cmd == "full-digest":
        return cmd_full_digest(args)
    if args.cmd == "deep-digest":
        return cmd_deep_digest(args)
    if args.cmd == "toc":
        return cmd_toc(args)
    if args.cmd == "refetch-raw":
        return backfill_mod.refetch_raw(dry_run=not args.apply)
    if args.cmd == "backfill-authors":
        if args.fix_urls:
            return backfill_mod.fix_urls(dry_run=args.dry_run)
        return backfill_mod.backfill_authors(dry_run=args.dry_run)
    if args.cmd == "begin":
        scope, code = _scope(args)
        if code:
            return code
        session.begin(args.raw_path, scope=scope)
        return 0
    if args.cmd == "extract":
        extract.run_extract(args.session)
        return 0
    if args.cmd == "map":
        map.run_map(args.session)
        return 0
    if args.cmd == "draft":
        draft.run_draft(args.session)
        return 0
    if args.cmd == "finalize":
        return session.finalize(args.session)
    if args.cmd == "abort":
        return session.abort(args.session)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "backlog":
        return cmd_backlog(args)
    if args.cmd == "index-researcher":
        if args.ir_cmd == "begin":
            return 0 if researcher.begin(args.query, slug=args.slug, author_id=args.author_id) else 2
        if args.ir_cmd == "verify":
            return researcher.verify(args.slug)
        if args.ir_cmd == "finalize":
            return researcher.finalize(args.slug)
        if args.ir_cmd == "abort":
            return researcher.abort(args.slug)
        if args.ir_cmd == "relink":
            return researcher.relink(args.slug, dry_run=args.dry_run)
        if args.ir_cmd == "status":
            return researcher.status()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

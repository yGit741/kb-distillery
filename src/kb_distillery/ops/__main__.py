"""pixi run ops -- <command>

    status                               version, sessions, hooks, pending
    log [-n 20] [--kb|--infra]           first-parent history (kb-x.y.z / #N)
    snapshots                            list snapshot tags
    begin <op> <target> ["why"]          open a free-form edit session (refine, digest, …)
    commit ["summary"] [--no-push]       commit what changed since begin (pushed right away)
    abort                                close the session without committing
    undo <sha>                           reverse one knowledge step (new kb(undo) commit)
    restore <kb-x.y.z>                   bring wiki/ back to a snapshot (new kb(restore) commit)
    snapshot ["label"]                   tag the newest knowledge step as kb-x.y.z
    sync [--no-push] [--dry-run]         nightly: think/ edits, leftovers, push
    migrate [--check|--dry-run]         run pending schema migrations (infra/* branch, or a kb repo's own main)
    next-version                         print the next kb-x.y.z
    chore <scope> "summary" [paths…]     commit a kb repo's own tooling files (kb.toml, .claude/, CLAUDE.md…) as chore(<scope>)
    record <op> <target> "summary" <paths…>   commit already-modified files as one knowledge op
    adopt-history <bundle> [--checkout P]     fast-forward main to a curated history bundle
    view pin <name> [--spec JSON|--spec-file F] [--id ID]   pin a graph view in meta/views.json (one knowledge step)
    view unpin <id>                      remove a pinned view
    view rename <id> <name>              rename a pinned view
"""
import argparse
import json
import os
import sys

from . import core
from . import migrate as migrate_mod
from kb_distillery.vault.views import ViewsError


def _read_spec(inline, path):
    """The `--spec` / `--spec-file` JSON object ({} when neither is given)."""
    if inline and path:
        raise ViewsError(400, "give --spec or --spec-file, not both")
    try:
        if path:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        else:
            text = inline
        return json.loads(text) if text else {}
    except (OSError, ValueError) as e:
        raise ViewsError(400, f"the spec is not readable JSON: {e}") from None


def main(argv=None):
    p = argparse.ArgumentParser(prog="ops", description="Knowledge operations: one commit per operation")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    lg = sub.add_parser("log")
    lg.add_argument("-n", type=int, default=20)
    lg.add_argument("--kb", action="store_true")
    lg.add_argument("--infra", action="store_true")
    sub.add_parser("snapshots")
    b = sub.add_parser("begin")
    b.add_argument("op")
    b.add_argument("target")
    b.add_argument("summary", nargs="?")
    c = sub.add_parser("commit")
    c.add_argument("summary", nargs="?")
    c.add_argument("--no-push", action="store_true", help="commit only (offline); the nightly sync pushes later")
    sub.add_parser("abort")
    u = sub.add_parser("undo")
    u.add_argument("sha")
    r = sub.add_parser("restore")
    r.add_argument("tag")
    s = sub.add_parser("snapshot")
    s.add_argument("label", nargs="?")
    sy = sub.add_parser("sync")
    sy.add_argument("--no-push", action="store_true")
    sy.add_argument("--dry-run", action="store_true")
    sy.add_argument("--prefer", choices=("local", "origin"),
                    help="diverged main: keep this side's text in conflicting hunks when replaying")
    sy.add_argument("--root", help="sync another checkout (e.g. the primary one, from a worktree)")
    m = sub.add_parser("migrate")
    m.add_argument("--check", action="store_true")
    m.add_argument("--dry-run", action="store_true", help="full preflight (migrate a copy, run lint and okf-check), write nothing")
    sub.add_parser("next-version")
    ch = sub.add_parser("chore")
    ch.add_argument("scope")
    ch.add_argument("summary")
    ch.add_argument("paths", nargs="*")
    ch.add_argument("--no-push", action="store_true")
    rc = sub.add_parser("record")
    rc.add_argument("op")
    rc.add_argument("target")
    rc.add_argument("summary")
    rc.add_argument("paths", nargs="+")
    rc.add_argument("--no-push", action="store_true", help="commit only (offline); the nightly sync pushes later")
    ad = sub.add_parser("adopt-history")
    ad.add_argument("bundle")
    ad.add_argument("--checkout", help="checkout to update (default: this one)")
    ad.add_argument("--dry-run", action="store_true")
    ad.add_argument("--no-push", action="store_true")
    vw = sub.add_parser("view", help="pinned graph views in meta/views.json, one knowledge step each")
    vsub = vw.add_subparsers(dest="view_cmd", required=True)
    vp = vsub.add_parser("pin")
    vp.add_argument("name")
    vp.add_argument("--spec", help="the view's spec as a JSON object (default: {})")
    vp.add_argument("--spec-file", help="read the spec from this JSON file")
    vp.add_argument("--id", help="view id (default: a slug of the name)")
    vu = vsub.add_parser("unpin")
    vu.add_argument("id")
    vr = vsub.add_parser("rename")
    vr.add_argument("id")
    vr.add_argument("name")
    for v_ in (vp, vu, vr):
        v_.add_argument("--no-push", action="store_true", help="commit only (offline); the nightly sync pushes later")
    args = p.parse_args(argv)
    if getattr(args, "no_push", False):
        os.environ["KB_NO_PUSH"] = "1"

    try:
        if args.cmd == "status":
            core.status()
        elif args.cmd == "log":
            core.log(args.n, "kb" if args.kb else ("infra" if args.infra else None))
        elif args.cmd == "snapshots":
            for s in core.snapshots():
                print(f"{s['tag']}  {s['date']}  {s['label']}")
        elif args.cmd == "begin":
            core.begin(args.op, args.target, args.summary)
        elif args.cmd == "commit":
            core.commit(args.summary)
        elif args.cmd == "abort":
            core.abort()
        elif args.cmd == "undo":
            core.undo(args.sha)
        elif args.cmd == "restore":
            core.restore(args.tag)
        elif args.cmd == "snapshot":
            core.snapshot(args.label)
        elif args.cmd == "sync":
            return core.sync(push=not args.no_push, dry_run=args.dry_run, prefer=args.prefer,
                             root=os.path.abspath(args.root) if args.root else core.ROOT)
        elif args.cmd == "migrate":
            try:
                ids = migrate_mod.run(core.ROOT, core.current_branch(), check=args.check, dry_run=args.dry_run)
            except RuntimeError as e:                      # a refusal with a message, not a crash
                raise migrate_mod.MigrateError(str(e)) from None
            print(("pending: " if args.check else "would apply: " if args.dry_run else "applied: ") + (", ".join(ids) or "none"))
        elif args.cmd == "chore":
            if not core.chore(args.scope, args.summary, args.paths or None, root=core.ROOT):
                print("no kb tooling file changed")
        elif args.cmd == "next-version":
            print("kb-" + core.cp.fmt_version(core.cp.next_version(core.ROOT, "main")))
        elif args.cmd == "record":
            paths = []
            for p_ in args.paths:
                full = os.path.join(core.ROOT, p_)
                if os.path.isdir(full):
                    paths += [x for x in core.changed_paths(core.ROOT)["knowledge"] if x.startswith(p_.rstrip("/") + "/")]
                else:
                    paths.append(p_)
            if not core.commit_op(args.op, args.target, args.summary, paths=paths, root=core.ROOT):
                print("nothing to commit for those paths")
        elif args.cmd == "adopt-history":
            from .adopt import adopt
            adopt(args.bundle, os.path.abspath(args.checkout or core.ROOT), push=not args.no_push, dry_run=args.dry_run)
        elif args.cmd == "view":
            from . import view as view_mod
            if args.view_cmd == "pin":
                spec = _read_spec(args.spec, args.spec_file)
                out = view_mod.pin(args.name, spec, view_id=args.id, root=core.ROOT)
                print(f"pinned view {out['view']['id']} ({out['version'] or 'no step'})")
            elif args.view_cmd == "unpin":
                out = view_mod.unpin(args.id, root=core.ROOT)
                print(f"unpinned view {args.id} ({out['version'] or 'no step'})")
            else:
                out = view_mod.rename(args.id, args.name, root=core.ROOT)
                print(f"renamed view {args.id} ({out['version'] or 'unchanged'})")
    except core.OpsError as e:
        print(f"ops: {e}", file=sys.stderr)
        return 1
    except migrate_mod.MigrateError as e:
        print(f"ops: {e}", file=sys.stderr)
        return 1
    except ViewsError as e:
        print(f"ops: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

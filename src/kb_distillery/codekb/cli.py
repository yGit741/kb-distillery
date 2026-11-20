"""distill code: a deterministic IR of a code base, cut into citable cards.

    distill code build [<project>]       parse the repos -> <out>/ir.json + ir.db (+ drift warnings)
    distill code cards [<project>]       <out>/cards/*.md + index.json: one fact per row, stable fact ids
    distill code stale <old_out> <new_out>   which card facts changed between two builds (wiki claims to recheck)

Into the selected knowledge base (--kb <id|path>; its [code] table in kb.toml is the project unless a <project> file is given):
    distill code export [<project>]      cards -> <kb>/raw/printed-docs/ir-*.md as one kb(catalog) step; artifact graph -> <kb>/artifacts/graph.json
    distill code kb [<project>]          build + cards + export + check-cites
    distill code cite --check [page ...] [--refresh]   {{card:Fid}} placeholders in wiki pages: what they would expand to
    distill code check-cites             every cited fact still exists in its card

<project> is a YAML or TOML file (see kb_distillery.codekb.generic.project). No model and no network: the same commits
always give the same output. C++ needs the optional tree-sitter: pip install "kb-distillery[code]".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kb_distillery.codekb.generic import project as projects
from kb_distillery.config import kb as _kbconfig  # noqa: F401 -- strips `--kb <id|path>` from argv before argparse sees it


def _project(args, need_checkouts: bool = True) -> projects.Project:
    if args.project:
        p = projects.load(args.project)
    else:
        p = projects.load_kb(_kb_root())
    if need_checkouts:
        projects.check_checkouts(p)
    return p


def _kb_root() -> Path:
    from kb_distillery.config.paths import vault_root          # lazy: `--help` and `build` need no knowledge base
    return Path(vault_root()).resolve()


def cmd_build(args) -> int:
    from kb_distillery.codekb import pipeline
    from kb_distillery.codekb.cpp.parser import MissingParser
    try:
        pipeline.build(_project(args), quiet=args.quiet)
    except MissingParser as exc:
        raise SystemExit(str(exc)) from None
    return 0


def cmd_cards(args) -> int:
    from kb_distillery.codekb import pipeline
    p = _project(args, need_checkouts=False)
    if not (p.out / "ir.json").is_file():
        raise SystemExit(f"{p.out}/ir.json not found: run `distill code build` first")
    pipeline.cards(p)
    return 0


def cmd_stale(args) -> int:
    from kb_distillery.codekb.generic.staleness import main
    main(Path(args.old), Path(args.new))
    return 0


def cmd_export(args) -> int:
    from kb_distillery.codekb import export as ex
    from kb_distillery.codekb.generic import artifacts
    p, root = _project(args, need_checkouts=False), _kb_root()
    _writable(root)
    try:
        r = ex.export(p.out / "cards", str(root), summary=args.summary)
    except ex.ExportError as exc:
        raise SystemExit(str(exc)) from None
    for key in ("added", "updated", "unchanged"):
        print(f"  {key}: {len(r[key])}" + (f" ({', '.join(r[key][:5])}{' ...' if len(r[key]) > 5 else ''})" if r[key] and key != "unchanged" else ""))
    for name in r["gone"]:
        print(f"  no longer built (kept; pages citing it fail check-cites): {name}")
    if r["commit"]:
        print(f"  committed {r['commit'][:8]}")
    elif r["added"] or r["updated"]:
        print("  warning: the cards were written but no knowledge step was committed (lint or the OKF gate may have refused: run `distill ops status`)")
    if not args.no_graph:
        dest = Path(args.graph) if args.graph else root / ex.GRAPH
        s = artifacts.export(p, dest)
        print(f"  artifact graph: {s['nodes']} nodes, {s['links']} links, {s['cards']} cards mapped, {s['bytes'] // 1024} KB -> {dest}")
        print("    types: " + ", ".join(f"{k} {v}" for k, v in s["types"].items()))
        print("    relations: " + ", ".join(f"{k} {v}" for k, v in s["relations"].items()))
    return 0


def _writable(root) -> None:
    try:
        _kbconfig.require_writable(str(root))
    except _kbconfig.ReadOnlyError as exc:
        raise SystemExit(str(exc)) from None


def cmd_kb(args) -> int:
    _writable(_kb_root())
    if not args.no_build:
        cmd_build(args)
        cmd_cards(args)
    cmd_export(args)
    if any((_kb_root() / "wiki").glob("*.md")):
        from kb_distillery.codekb import cites
        return cites.check_cites(_kb_root())
    return 0


def cmd_cite(args) -> int:
    from kb_distillery.codekb import cites
    return cites.cite(_kb_root(), args.pages, check=args.check, refresh=args.refresh)


def cmd_check_cites(args) -> int:
    from kb_distillery.codekb import cites
    return cites.check_cites(_kb_root())


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="distill code", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, project=True):
        s = sub.add_parser(name, help=help_)
        if project:
            s.add_argument("project", nargs="?", help="project file (YAML or TOML); default: the [code] table of the selected kb's kb.toml")
        s.set_defaults(func=fn)
        return s

    add("build", cmd_build, "parse the repos into <out>/ir.json + ir.db").add_argument("--quiet", action="store_true")
    add("cards", cmd_cards, "cut the built IR into <out>/cards/*.md")
    s = add("stale", cmd_stale, "which card facts changed between two builds", project=False)
    s.add_argument("old")
    s.add_argument("new")
    for name, fn, help_ in (("export", cmd_export, "cards -> raw/printed-docs/ir-*.md (one kb(catalog) step), artifact graph"),
                            ("kb", cmd_kb, "build + cards + export + check-cites for the selected kb")):
        s = add(name, fn, help_)
        s.add_argument("--summary", help="commit summary of the knowledge step")
        s.add_argument("--graph", help="where to write the artifact graph (default: <kb>/artifacts/graph.json)")
        s.add_argument("--no-graph", action="store_true", help="skip the artifact graph")
        if name == "kb":
            s.add_argument("--no-build", action="store_true", help="export the IR and cards already in the output folder")
            s.add_argument("--quiet", action="store_true")
    s = add("cite", cmd_cite, "{{card:Fid}} placeholders in wiki pages: what they would expand to (--check only)", project=False)
    s.add_argument("pages", nargs="*")
    s.add_argument("--check", action="store_true", help="report what would change, write nothing (writing is not shipped yet)")
    s.add_argument("--refresh", action="store_true", help="re-point every cited fact at its current anchors")
    add("check-cites", cmd_check_cites, "every cited fact exists in its card and its links are that fact's anchors", project=False)
    return ap


def main_args(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    return args.func(args) or 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(main_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    main()

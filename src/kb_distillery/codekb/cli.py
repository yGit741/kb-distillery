"""distill code: a deterministic IR of a code base, cut into citable cards.

    distill code build [<project>]       parse the repos -> <out>/ir.json + ir.db (+ drift warnings)
    distill code cards [<project>]       <out>/cards/*.md + index.json: one fact per row, stable fact ids

<project> is a YAML or TOML file (see kb_distillery.codekb.generic.project); without one, the [code] table of the selected
knowledge base's kb.toml (--kb <id|path>) is the project. No model and no network: the same commits always give the same
output. C++ needs the optional tree-sitter: pip install "kb-distillery[code]".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kb_distillery.codekb.generic import project as projects
from kb_distillery.config import kb as _kbconfig  # noqa: F401 -- strips `--kb <id|path>` from argv before argparse sees it


def _kb_root() -> Path:
    from kb_distillery.config.paths import vault_root          # lazy: `--help` needs no knowledge base
    return Path(vault_root()).resolve()


def _project(args, need_checkouts: bool = True) -> projects.Project:
    p = projects.load(args.project) if args.project else projects.load_kb(_kb_root())
    if need_checkouts:
        projects.check_checkouts(p)
    return p


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
    pipeline.cards(_project(args, need_checkouts=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="distill code", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("project", nargs="?", help="project file (YAML or TOML); default: the [code] table of the selected kb's kb.toml")
        s.set_defaults(func=fn)
        return s

    add("build", cmd_build, "parse the repos into <out>/ir.json + ir.db").add_argument("--quiet", action="store_true")
    add("cards", cmd_cards, "cut the built IR into <out>/cards/*.md")
    return ap


def main_args(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    return args.func(args) or 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(main_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    main()

"""The `distill` command tree: what each command runs, the help text, and the dispatcher.

    distill <command> [args…]        e.g.  distill kb list   ·   distill lint --kb demo   ·   distill send <note> --to a,b

Every command delegates to the module (or script) that already does the work, with the rest of the command line handed
over untouched, so `--kb <id|path>` goes after the command. Dispatch is by hand and only the help is argparse: the
arguments after a command belong to that module, and `argparse.REMAINDER` mangles a leading option such as `--kb`.

This package imports nothing from `kb_distillery` except `config.resources` and `config.userdir` (neither imports a kb
module): `kbconfig` strips `--kb` from `sys.argv` the moment it is imported, and `distill --help` must work with no
knowledge base selected.
"""
from __future__ import annotations

import argparse
import os
import runpy
import subprocess
import sys
from dataclasses import dataclass, field

from kb_distillery.config import userdir
from kb_distillery.config.resources import NotInCheckout, repo_root, require_repo_root

PROG = "distill"


@dataclass(frozen=True)
class Cmd:
    """One command. kind: "module" (python -m target), "script" (bash target, from a checkout), "launch" (see run) or
    "group" (sub holds the subcommands). forward_help: `--help` goes to the module, which must be argparse-based; for
    the others `--help` is answered here, since a module that ignores it would run (the linter does)."""
    help: str
    kind: str = "module"
    target: str = ""
    fixed: tuple[str, ...] = ()
    forward_help: bool = False
    checkout_only: bool = False         # hidden from --help and refused when the package runs outside a checkout
    config_check: bool = True           # refuse while only the old ~/.config/thesis-kb exists (userdir.check)
    sub: dict[str, "Cmd"] = field(default_factory=dict)


COMMANDS: dict[str, Cmd] = {
    "init": Cmd("create a first knowledge base from a template (own git repo), then run doctor", target="kb_distillery.init_kb",
                forward_help=True),
    "doctor": Cmd("check the environment and a kb, with a fix for each problem (--json)", target="kb_distillery.doctor",
                  forward_help=True, config_check=False),
    "kb": Cmd("knowledge bases", "group", sub={
        "list": Cmd("every knowledge base and where it is", target="kb_distillery.kbconfig", fixed=("list",)),
        "show": Cmd("the selected knowledge base, resolved", target="kb_distillery.kbconfig", fixed=("show",)),
    }),
    "launch": Cmd("restart the app detached and open it (outside a checkout: serve it in the foreground)", "launch",
                  "scripts/launch.sh"),
    "hooks": Cmd("git and Claude Code hooks", "group", sub={
        "install": Cmd("install the git + Claude Code hooks into a kb", "script", "scripts/install-kb-hooks.sh",
                       checkout_only=True),
    }),
    "hook": Cmd("stable entry for the kb-side hooks (git hooks and Claude Code guards call these)", "group", sub={
        "guard": Cmd("Claude Code write guard: may this file be edited?", target="kb_distillery.git.guard", config_check=False),
        "git-guard": Cmd("Claude Code Bash guard: block ad-hoc git writes", target="kb_distillery.git.git_guard",
                         config_check=False),
        "pre-commit": Cmd("git pre-commit: the linter is the schema", target="kb_distillery.lint.lint", config_check=False),
        "commit-msg": Cmd("git commit-msg: kb(op) conventional commits", target="kb_distillery.git.commit_policy",
                          fixed=("msg",), config_check=False),
        "pre-push": Cmd("git pre-push: main only moves forward by kb steps", target="kb_distillery.git.commit_policy",
                        fixed=("push",), config_check=False),
    }),
    "ops": Cmd("knowledge operations: sessions, snapshots, undo, restore, status, migrate", target="kb_distillery.ops",
               forward_help=True),
    "ship": Cmd("ship tooling through infra/* branches (start, commit, pr, merge, …)", target="kb_distillery.git.ship",
                forward_help=True, checkout_only=True, config_check=False),
    "ingest": Cmd("scrap, catalog and digest sources (scrap, catalog, resolve, status, …)", target="kb_distillery.ingest",
                  forward_help=True),
    "digest": Cmd("digest a source page: easy, full or deep", "group", sub={
        "easy": Cmd("abstract skim (light LLM)", target="kb_distillery.ingest", fixed=("easy-digest",), forward_help=True),
        "full": Cmd("standard paper note (medium LLM)", target="kb_distillery.ingest", fixed=("full-digest",), forward_help=True),
        "deep": Cmd("thesis-critical digest (heavy LLM)", target="kb_distillery.ingest", fixed=("deep-digest",), forward_help=True),
        "many": Cmd("batch-fill claims for many sources, then full-digest them one by one (LLM)",
                    target="kb_distillery.ingest", fixed=("digest-many",), forward_help=True),
        "instructions": Cmd("the digest focus of the selected kb", target="kb_distillery.core.digest"),
    }),
    "send": Cmd("send a think note into knowledge bases: distill send <note> --to a,b", target="kb_distillery.distill.send",
                forward_help=True),
    "lint": Cmd("lint the selected knowledge base (the schema is the linter); --health adds the summary",
                target="kb_distillery.lint.lint"),
    "llm": Cmd("the one door to Claude: ask, submit, status, collect", target="kb_distillery.llm", forward_help=True),
    "share": Cmd("publish the wiki graph + explorer as a site (build, snapshot, status, …)", target="kb_distillery.share",
                 forward_help=True),
    "propose": Cmd("typed relation proposals between wiki pages: submit, collect, review, apply", target="kb_distillery.graph.propose",
                   forward_help=True),
}

# commands whose --help is answered by the module (forward_help) or here; "help" is the only word handled before lookup
HELP_WORDS = ("-h", "--help")


def visible(commands: dict[str, Cmd] | None = None) -> dict[str, Cmd]:
    """The commands `--help` lists: `ship` only inside a checkout."""
    commands = COMMANDS if commands is None else commands
    inside = repo_root() is not None
    return {n: c for n, c in commands.items() if inside or not c.checkout_only}


def _fill(parser: argparse.ArgumentParser, commands: dict[str, Cmd], trail: tuple[str, ...]) -> None:
    sub = parser.add_subparsers(dest="/".join(trail) or "command",
                                title="commands" if not trail else "subcommands")
    for name, cmd in commands.items():
        p = sub.add_parser(name, help=cmd.help, description=cmd.help, add_help=False, formatter_class=_Help,
                           prog=" ".join((PROG, *trail, name)))
        if cmd.kind == "group":
            p.usage = f"{PROG} {' '.join((*trail, name))} <subcommand> [args…]"
            _fill(p, cmd.sub, (*trail, name))
        else:
            p.usage = f"{PROG} {' '.join((*trail, name))} [args…]"
            where = (f"python -m {cmd.target}" if cmd.kind == "module" else f"bash {cmd.target}") + \
                    (f" {' '.join(cmd.fixed)}" if cmd.fixed else "")
            p.epilog = (f"Everything after the command goes to `{where}` unchanged; pass --kb <id|path> after the command"
                        + ("; `--help` shows that module's own options." if cmd.forward_help else "."))


class _Help(argparse.RawDescriptionHelpFormatter):
    """Lists the commands without the subparsers action's own (empty) line."""

    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            return "".join(self._format_action(a) for a in action._get_subactions())
        return super()._format_action(action)


def build_parser(only_visible: bool = True) -> argparse.ArgumentParser:
    """The argparse tree used for help text (every command and subcommand has a parser, so `--help` is generated, not typed)."""
    top = argparse.ArgumentParser(prog=PROG, usage=f"{PROG} <command> [args…]", description="distill: build and tend knowledge bases.",
                                  epilog="Pass --kb <id|path> after a command to pick a knowledge base (see: distill kb list).",
                                  formatter_class=_Help, add_help=False)
    _fill(top, visible() if only_visible else COMMANDS, ())
    return top


def _find_parser(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> argparse.ArgumentParser:
    for name in path:
        action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        parser = action.choices[name]
    return parser


def help_text(path: tuple[str, ...] = ()) -> str:
    """The help of the whole tree (visible commands only) or of one command / group, which is shown even when hidden."""
    return _find_parser(build_parser(only_visible=not path), path).format_help()


def resolve(argv: list[str]) -> tuple[tuple[str, ...], Cmd, list[str]] | None:
    """(command path, leaf command, remaining arguments) or None when a group has no / an unknown subcommand."""
    cmds, path, cmd = COMMANDS, (), None
    rest = list(argv)
    while True:
        if not rest or rest[0] not in cmds:
            return None if cmd is None or cmd.kind == "group" else (path, cmd, rest)
        cmd = cmds[rest[0]]
        path, rest = (*path, rest[0]), rest[1:]
        if cmd.kind != "group":
            return path, cmd, rest
        cmds = cmd.sub


def run(path: tuple[str, ...], cmd: Cmd, rest: list[str]) -> int:
    """Run one leaf command and return its exit code."""
    prog = " ".join((PROG, *path))
    if cmd.checkout_only:
        try:
            require_repo_root(prog)             # repository tooling, not package data
        except NotInCheckout as e:
            sys.stderr.write(f"{PROG}: {e}\n")
            return 2
    if cmd.config_check and rest[:1] not in (["-h"], ["--help"]):          # help never depends on the config folder
        problem = userdir.check()
        if problem:
            sys.stderr.write(problem + "\n")
            return 1
    kind, target = cmd.kind, cmd.target
    if kind == "launch":
        if repo_root() is None:                 # an installed package has no scripts/: serve the app in the foreground
            kind, target = "module", "kb_distillery.api"
            if "--port" not in rest:
                rest = ["--port", "8765", *rest]
        else:
            kind = "script"
    if kind == "script":
        try:
            root = require_repo_root(prog)
        except NotInCheckout as e:
            sys.stderr.write(f"{PROG}: {e}\n")
            return 2
        return subprocess.call(["bash", os.path.join(root, target), *cmd.fixed, *rest])
    sys.argv = [prog, *cmd.fixed, *rest]
    try:
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in (*HELP_WORDS, "help"):
        if argv[:1] == ["help"] and argv[1:2] and argv[1] in COMMANDS:    # distill help kb list
            found = resolve(argv[1:])
            sys.stdout.write(help_text(found[0] if found else (argv[1],)))
            return 0
        sys.stdout.write(help_text())
        return 0
    found = resolve(argv)
    if found is None:
        name = argv[0]
        if name in COMMANDS:                                           # a group without (or with an unknown) subcommand
            if len(argv) > 1 and argv[1] in HELP_WORDS:
                sys.stdout.write(help_text((name,)))
                return 0
            sys.stderr.write(f"{PROG}: {name}: " + ("unknown subcommand " + repr(argv[1]) if len(argv) > 1 else "needs a subcommand")
                             + "\n\n" + help_text((name,)))
            return 2
        sys.stderr.write(f"{PROG}: unknown command {name!r}\n\n{help_text()}")
        return 2
    path, cmd, rest = found
    if rest[:1] and rest[0] in HELP_WORDS and not cmd.forward_help:
        sys.stdout.write(help_text(path))
        return 0
    return run(path, cmd, rest)

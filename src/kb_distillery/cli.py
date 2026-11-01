"""kbd: one front door to the engine's commands.

    kbd <command> [args…]        e.g.  kbd kb-list   ·   kbd lint --kb demo   ·   kbd app --port 8766

Each command runs the module (or script) the matching `pixi run <task>` runs, with the rest of the command line
handed over untouched, so `--kb <id|path>` goes after the command. This file imports nothing from `kb` on purpose
but `kb_distillery.config.resources` (which imports no kb module): `kbconfig` strips `--kb` from `sys.argv` the moment
it is imported, and `kbd --help` must work with no kb selected.

Entry points (pyproject.toml): `distill` and `kbd` both run `main` today; Lane D gives `distill` its own command tree.
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys

# name → (kind, target, arguments put before the user's, help). kind: "module" (python -m) or "script" (bash).
COMMANDS: dict[str, tuple[str, str, tuple[str, ...], str]] = {
    "kb-list": ("module", "kb_distillery.kbconfig", ("list",), "every knowledge base and where it is"),
    "kb-show": ("module", "kb_distillery.kbconfig", ("show",), "the selected knowledge base, resolved"),
    "lint": ("module", "kb_distillery.lint.lint", (), "lint the selected knowledge base (the schema is the linter)"),
    "health": ("module", "kb_distillery.lint.lint", ("--health",), "lint, with the health summary"),
    "app": ("module", "kb_distillery.api", (), "serve the app (API + React shell), default port 8765"),
    "ship": ("module", "kb_distillery.git.ship", (), "ship tooling through infra/* branches (start, commit, merge, tag, …)"),
    "ops": ("module", "kb_distillery.ops", (), "knowledge operations: sessions, snapshots, undo, restore, status"),
    "distill": ("module", "kb_distillery.distill.send", (), "send a think note into kbs: kbd distill <note> --to a,b"),
    "init": ("module", "kb_distillery.init_kb", (), "create a first knowledge base from a template (own git repo), then run doctor"),
    "doctor": ("module", "kb_distillery.doctor", (), "check the environment and a kb, with a fix for each problem (--json)"),
    "launch": ("script", "scripts/launch.sh", (), "restart the app detached and open it"),
    "install-kb-hooks": ("script", "scripts/install-kb-hooks.sh", (), "install the git + Claude Code hooks into a kb"),
}


def _help() -> str:
    width = max(map(len, COMMANDS))
    rows = "\n".join(f"  {name:<{width}}  {spec[3]}" for name, spec in COMMANDS.items())
    return (f"usage: kbd <command> [args…]\n\ncommands:\n{rows}\n\n"
            "Pass --kb <id|path> after the command to pick a knowledge base (see: kbd kb-list).\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_help())
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        sys.stderr.write(f"kbd: unknown command {name!r}\n\n{_help()}")
        return 2
    kind, target, fixed, _ = COMMANDS[name]
    if name == "app" and "--port" not in rest:
        rest = ["--port", "8765", *rest]
    if kind == "script":
        from kb_distillery.config.resources import NotInCheckout, require_repo_root
        try:
            root = require_repo_root(f"kbd {name}")      # the scripts are repository tooling, not package data
        except NotInCheckout as e:
            sys.stderr.write(f"kbd: {e}\n")
            return 2
        return subprocess.call(["bash", os.path.join(root, target), *fixed, *rest])
    sys.argv = [f"kbd {name}", *fixed, *rest]
    try:
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


def kbd_main(argv: list[str] | None = None) -> int:
    """The `kbd` entry point (Lane D turns it into a deprecation forwarder to `distill`)."""
    return main(argv)


if __name__ == "__main__":
    sys.exit(main())

"""kbd: one front door to the engine's commands.

    kbd <command> [args…]        e.g.  kbd kb-list   ·   kbd lint --kb demo   ·   kbd app --port 8766

Each command runs the module (or script) the matching `pixi run <task>` runs, with the rest of the command line
handed over untouched, so `--kb <id|path>` goes after the command. This file imports nothing from `kb` on purpose:
`kbconfig` strips `--kb` from `sys.argv` the moment it is imported, and `kbd --help` must work with no kb selected.
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys

CHECKOUT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# name → (kind, target, arguments put before the user's, help). kind: "module" (python -m) or "script" (bash).
COMMANDS: dict[str, tuple[str, str, tuple[str, ...], str]] = {
    "kb-list": ("module", "kb.kbconfig", ("list",), "every knowledge base and where it is"),
    "kb-show": ("module", "kb.kbconfig", ("show",), "the selected knowledge base, resolved"),
    "lint": ("module", "kb.lint.lint", (), "lint the selected knowledge base (the schema is the linter)"),
    "health": ("module", "kb.lint.lint", ("--health",), "lint, with the health summary"),
    "app": ("module", "kb.api", (), "serve the app (API + React shell), default port 8765"),
    "ship": ("module", "kb.git.ship", (), "ship tooling through infra/* branches (start, commit, merge, tag, …)"),
    "ops": ("module", "kb.ops", (), "knowledge operations: sessions, snapshots, undo, restore, status"),
    "distill": ("module", "kb.distill.send", (), "send a think note into kbs: kbd distill <note> --to a,b"),
    "init": ("module", "kb.init_kb", (), "create a first knowledge base from a template (own git repo), then run doctor"),
    "doctor": ("module", "kb.doctor", (), "check the environment and a kb, with a fix for each problem (--json)"),
    "launch": ("script", "tools/launch.sh", (), "restart the app detached and open it"),
    "install-kb-hooks": ("script", "tools/install-kb-hooks.sh", (), "install the git + Claude Code hooks into a kb"),
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
        return subprocess.call(["bash", os.path.join(CHECKOUT_ROOT, target), *fixed, *rest])
    sys.argv = [f"kbd {name}", *fixed, *rest]
    try:
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

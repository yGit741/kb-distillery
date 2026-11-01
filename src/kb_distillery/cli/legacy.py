"""`kbd`: the old front door, kept for one release as a forwarder to `distill`.

Every old command is mapped to its `distill` form (`KBD_MAP`); running one prints a one-line deprecation on stderr and
then runs the new command with the rest of the line untouched. Remove this module (and the `kbd` entry point) after the
release that announces it.
"""
from __future__ import annotations

import sys

from kb_distillery.cli import tree

# old command -> the distill command line that replaces it
KBD_MAP: dict[str, tuple[str, ...]] = {
    "kb-list": ("kb", "list"),
    "kb-show": ("kb", "show"),
    "lint": ("lint",),
    "health": ("lint", "--health"),
    "app": ("launch",),
    "launch": ("launch",),
    "ship": ("ship",),
    "ops": ("ops",),
    "distill": ("send",),
    "init": ("init",),
    "doctor": ("doctor",),
    "install-kb-hooks": ("hooks", "install"),
}


def _help() -> str:
    width = max(map(len, KBD_MAP))
    rows = "\n".join(f"  kbd {old:<{width}}  ->  distill {' '.join(new)}" for old, new in KBD_MAP.items())
    return ("kbd is deprecated: use `distill` (same commands, new names). Each kbd command forwards to its distill form.\n\n"
            f"{rows}\n")


def kbd_main(argv: list[str] | None = None) -> int:
    """The `kbd` entry point."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_help())
        return 0
    old, rest = argv[0], argv[1:]
    if old not in KBD_MAP:
        sys.stderr.write(f"kbd: unknown command {old!r}\n\n{_help()}")
        return 2
    new = KBD_MAP[old]
    sys.stderr.write(f"kbd {old} is deprecated; use: distill {' '.join(new)}\n")
    return tree.main([*new, *rest])


if __name__ == "__main__":
    sys.exit(kbd_main())

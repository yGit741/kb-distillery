"""distill: the command line of kb-distillery, and `kbd`, its deprecated old name.

    distill <command> [args…]       see `distill --help` (tree.py: the command table, help and dispatch)
    kbd <command> [args…]           forwards to distill with a one-line deprecation (legacy.py: the mapping table)

Entry points (pyproject.toml): `distill = kb_distillery.cli:main`, `kbd = kb_distillery.cli:kbd_main`. Importing this
package loads no knowledge-base code (`kbconfig` strips `--kb` from `sys.argv` the moment it is imported).
"""
from kb_distillery.cli.legacy import KBD_MAP, kbd_main
from kb_distillery.cli.tree import COMMANDS, main

__all__ = ["COMMANDS", "KBD_MAP", "kbd_main", "main"]

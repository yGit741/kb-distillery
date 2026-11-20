"""usage: distill mcp [--kb <path>]…

Serve the local knowledge bases over MCP on stdio (read-only). The bases dir is `$KB_DISTILLERY_HOME` (default
~/knowledge); each `--kb <path>` adds one more kb folder.

`--kb` may repeat; it is read here, before any module imports `kbconfig` (which would take only the first one).
"""
from __future__ import annotations

import sys


def _take_kbs(argv: list[str]) -> list[str]:
    kbs, rest, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--kb" and i + 1 < len(argv):
            kbs.append(argv[i + 1])
            i += 2
            continue
        if a == "--kb":
            raise SystemExit("distill mcp: --kb needs a folder")
        if a.startswith("--kb="):
            kbs.append(a[len("--kb="):])
        else:
            rest.append(a)
        i += 1
    argv[:] = rest
    return kbs


def main() -> int:
    kbs = _take_kbs(sys.argv[1:])
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__.strip())
        return 0
    from kb_distillery.kb_mcp import server
    from kb_distillery.kb_mcp.library import Library
    server.build(Library(kbs)).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Which engine modules reach `raw/` directly instead of through a storage connector (kb.storage).

    python -m kb.lint.raw_access            # table of modules and how many lines match
    python -m kb.lint.raw_access --names    # just the module paths, the format of the baseline file

A line matches when it names the raw tree: `RAW_PATH` / `RAW_DIR`, or a string that starts with `raw/` or is `raw`.
The check is deliberately broad (a rule path or a doc string also matches): the baseline file lists the modules
allowed to match today, `backend/tests/storage/test_raw_access_ratchet.py` fails on a module that is not listed and
on a listed module that no longer matches, so the list only shrinks. Exempt: the connectors themselves, migrations
(they rewrite old layouts on purpose) and the two files that define the raw constants.
"""
from __future__ import annotations

import os
import re
import sys

PATTERN = re.compile(r"""\bRAW_PATH\b|\bRAW_DIR\b|["']raw/|["']raw["']""")
EXEMPT_DIRS = ("storage/", "migrations/")
EXEMPT_FILES = frozenset({"paths.py", "core/schema.py", "lint/raw_access.py"})


def src_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # backend/src/kb


def scan(root: str | None = None) -> dict[str, int]:
    """{module path relative to backend/src/kb: number of matching lines}, exempt modules left out."""
    root = root or src_root()
    out: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            if rel in EXEMPT_FILES or rel.startswith(EXEMPT_DIRS):
                continue
            with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                n = sum(1 for line in f if PATTERN.search(line))
            if n:
                out[rel] = n
    return out


def main(argv=None) -> int:
    found = scan()
    if "--names" in (argv if argv is not None else sys.argv[1:]):
        print("\n".join(sorted(found)))
        return 0
    width = max((len(m) for m in found), default=0)
    for module, n in sorted(found.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{module:<{width}}  {n:>3}")
    print(f"{len(found)} module(s) reach raw/ directly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Which engine modules reach `raw/` directly instead of through a storage connector (kb_distillery.storage).

    python -m kb_distillery.lint.raw_access            # table of modules and how many lines match
    python -m kb_distillery.lint.raw_access --names    # just the module paths, the format of the baseline file

A module is flagged when it
  * uses the raw-tree constants `RAW_PATH` / `RAW_DIR` (it builds raw paths itself), or
  * has a line that names the raw tree (a string starting with `raw/`, or `raw`) next to a filesystem call
    (`open(`, `os.path.*`, `os.listdir`, `Path(`, `shutil.`, `subprocess`, ...).
A frontmatter key `"raw"`, a docstring or a path rule is not access and does not match. The check is a floor, not a
proof: indirect access through a variable that holds a raw path is invisible to it, so migrating a module means
replacing all of its raw I/O, not only the flagged lines.

`tests/storage/raw_access_baseline.txt` lists the modules allowed to match today;
`tests/storage/test_raw_access_ratchet.py` fails on a module that is not listed and on a listed module that no
longer matches, so the list only shrinks. Exempt: the connectors themselves, migrations (they rewrite old layouts on
purpose) and the files that define the raw constants.
"""
from __future__ import annotations

import os
import re
import sys

CONSTANT = re.compile(r"\bRAW_PATH\b|\bRAW_DIR\b")
RAW_LITERAL = re.compile(r"""["']raw/|["']raw["']""")
FS_CALL = re.compile(r"""\bopen\(|os\.(path\.(join|isfile|isdir|exists|getsize|getmtime|relpath|realpath)|listdir|walk|scandir|stat|makedirs|remove|rename|replace)|\bPath\(|shutil\.|glob\.|\.read_text|\.read_bytes|\.write_text|\.write_bytes|subprocess|\bsha1\(""")
EXEMPT_DIRS = ("storage/", "migrations/")
EXEMPT_FILES = frozenset({"config/paths.py", "config/layout.py", "vault/schema.py", "lint/raw_access.py"})


def src_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # src/kb_distillery


def matches(line: str) -> bool:
    return bool(CONSTANT.search(line) or (RAW_LITERAL.search(line) and FS_CALL.search(line)))


def scan(root: str | None = None) -> dict[str, int]:
    """{module path relative to src/kb_distillery: number of matching lines}, exempt modules left out."""
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
                n = sum(1 for line in f if matches(line))
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

"""Flag test matrix: every flag in meta/flags.toml needs a test for both states (on and off).

A test declares the state it runs in with
  pytest  `@pytest.mark.flag("name", True|False)` (backend/tests, conftest applies kb.flags.override)
  vitest  `withFlag("name", true|false, fn)` from `@/flags/testing` (frontend/src/**/*.test.ts(x))
`python -m kb.flags.coverage` (part of `pixi run flags-check`) exits 1 listing each flag/state with no test.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from kb.flags.registry import FLAGS_TOML, FlagError, load
from kb.paths import ROOT

PY_RE = re.compile(r"""mark\.flag\(\s*["']([^"']+)["']\s*,\s*(True|False)\b""")
TS_RE = re.compile(r"""withFlag\(\s*["']([^"']+)["']\s*,\s*(true|false)\b""")


def test_files(root: Path):
    for p in sorted((root / "backend" / "tests").rglob("test_*.py")):
        yield p, PY_RE
    src = root / "frontend" / "src"
    for pat in ("*.test.ts", "*.test.tsx"):
        for p in sorted(src.rglob(pat)):
            if "node_modules" not in p.parts:
                yield p, TS_RE


def scan(root: Path) -> dict[str, dict[bool, list[str]]]:
    """{flag: {True: [files], False: [files]}} for every flag-state a test declares."""
    found: dict[str, dict[bool, list[str]]] = {}
    for p, rx in test_files(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        for name, state in rx.findall(text):
            on = state.lower() == "true"
            files = found.setdefault(name, {True: [], False: []})[on]
            rel = str(p.relative_to(root))
            if rel not in files:
                files.append(rel)
    return found


def missing(names, found) -> list[str]:
    """['screen.share: off', …] — each flag-state with no test."""
    return [f"{n}: {'on' if on else 'off'}" for n in names for on in (True, False)
            if not found.get(n, {}).get(on)]


def main(argv=None, root: Path | str = ROOT) -> int:
    root = Path(root)
    ap = argparse.ArgumentParser(prog="kb.flags.coverage", description=__doc__.splitlines()[0])
    ap.add_argument("--flags", default=None, help="registry path (default meta/flags.toml)")
    args = ap.parse_args(argv)
    try:
        reg = load(args.flags or (root / FLAGS_TOML.relative_to(Path(ROOT))))
    except FlagError as e:
        print(e, file=sys.stderr)
        return 2
    found = scan(root)
    gaps = missing(reg.names(), found)
    unknown = sorted(set(found) - set(reg.names()))
    if unknown:
        print("flags coverage: note: tests name flag(s) not in the registry (fixtures, or a removed flag's "
              "leftover tests): " + ", ".join(unknown), file=sys.stderr)
    if gaps:
        print("flags coverage: no test for " + "; ".join(gaps) + " — mark one with "
              '@pytest.mark.flag("<name>", True|False) or withFlag("<name>", true|false, …)', file=sys.stderr)
        return 1
    print(f"flags coverage: {len(reg.flags)} flag(s), on + off tested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

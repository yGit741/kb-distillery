"""Which files of the engine repo carry personal strings, so the repo can be made public without leaking them.

    python -m kb.lint.privacy            # table of files and how many lines match
    python -m kb.lint.privacy --names    # just the file paths, the format of the baseline file

A line matches when it holds the owner's local path or handles, the private site's name, or a token-shaped string
(an Anthropic, AWS, GitHub or Slack key, a Google API key, a private-key header). Knowledge never lives here (the
kbs are their own repos and `kbs/` is skipped), so a match is code, a test, a doc or a config naming a person.

`backend/tests/lint/privacy_baseline.txt` lists the files allowed to match today. The ratchet test fails on a file
that is not listed (new personal text) and on a listed file that no longer matches (delete its line), so the list only
shrinks until Phase 7 empties it or moves each remaining name behind configuration. Fake keys used as test fixtures
match the token shapes on purpose: they are listed with the rest, and a reviewer decides per file.
"""
from __future__ import annotations

import os
import re
import sys

# `workers.dev` alone is Cloudflare's own domain, not personal: the owner's site is caught by its name (yonatan-magen).
PERSONAL = re.compile(r"/Users/yonatanm|yonatanm|ygreenshpan|yGit741|yonatan-magen|yonatan-thesis-kb")
SECRET = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[bpoa]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_-]{30,}")
SKIP_DIRS = {".git", ".pixi", "node_modules", "dist", "_quarantine", ".cache", ".backlog", "__pycache__", ".claude",
             ".vitest-cache", ".vite", "kbs"}
SKIP_FILES = {"backend/src/kb/lint/privacy.py", "backend/tests/lint/privacy_baseline.txt",
              "backend/tests/lint/test_privacy_ratchet.py",          # the scanner and its fixtures name what they look for
              "docs/phase-7-audit.md"}                               # the audit names the owner on purpose; not for the public repo
SKIP_PREFIXES = ("docs/plans/", "frontend/dist/")
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".md", ".yml", ".yaml", ".sh", ".txt",
            ".css", ".html", ".plist", ".cfg", ".ini", ".mdc"}


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))        # backend/src/kb/lint -> repo


def matches(line: str) -> bool:
    return bool(PERSONAL.search(line) or SECRET.search(line))


def scan(root: str | None = None) -> dict[str, int]:
    """{path relative to the repo root: number of matching lines} for every text file outside the skipped folders."""
    root = root or repo_root()
    out: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES):
                continue
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT and fn not in {".gitignore", "LICENSE"}:
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    n = sum(1 for line in f if matches(line))
            except (OSError, UnicodeDecodeError):
                continue
            if n:
                out[rel] = n
    return out


def main(argv=None) -> int:
    found = scan()
    if "--names" in (argv if argv is not None else sys.argv[1:]):
        print("\n".join(sorted(found)))
        return 0
    width = max((len(m) for m in found), default=0)
    for path, n in sorted(found.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{path:<{width}}  {n:>3}")
    print(f"{len(found)} file(s) carry personal strings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

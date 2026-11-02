"""Which files of the engine repo carry personal strings, so the repo can be made public without leaking them.

    python -m kb_distillery.lint.privacy            # table of files and how many lines match
    python -m kb_distillery.lint.privacy --names    # just the file paths, the format of the baseline file

A line matches when it holds one of YOUR terms (a name, a handle, an email, a private site's name, a local path) or a
token-shaped string (an Anthropic, AWS, GitHub or Slack key, a Google API key, a private-key header). The terms are not
in this repo, because naming them here would leak them: they are read, first match wins, from

1. `$KB_PRIVACY_TERMS`, a comma- or pipe-separated list (CI sets it from a repository secret), else
2. `~/.config/kb-distillery/privacy.toml`, `terms = ["...", "..."]`.

With neither there are no terms: only token shapes are checked, so the ratchet passes on a fresh clone and still checks
every term you configure. Terms match case-insensitively as plain text. Knowledge never lives here (the kbs are their
own repos and `kbs/` is skipped), so a match is code, a test, a doc or a config naming a person.

`tests/lint/privacy_baseline.txt` lists the files allowed to match today. The ratchet test fails on a file that is not
listed (new personal text) and, when terms are configured, on a listed file that no longer matches (delete its line), so
the list only shrinks. Fake keys used as test fixtures match the token shapes on purpose: they are listed with the rest,
and a reviewer decides per file.
"""
from __future__ import annotations

import os
import re
import sys
import tomllib

ENV_TERMS = "KB_PRIVACY_TERMS"
TERMS_FILE = "privacy.toml"
SECRET = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[bpoa]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_-]{30,}")
SKIP_DIRS = {".git", ".pixi", "node_modules", "dist", "_quarantine", ".cache", ".backlog", "__pycache__", ".claude",
             ".vitest-cache", ".vite", "kbs"}
SKIP_FILES = {"src/kb_distillery/lint/privacy.py", "tests/lint/privacy_baseline.txt",
              "tests/lint/test_privacy_ratchet.py",          # the scanner and its fixtures name what they look for
              "docs/phase-7-audit.md"}                               # the audit names the owner on purpose; not for the public repo
SKIP_PREFIXES = ("docs/plans/", "src/kb_distillery/_webapp/")
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".md", ".yml", ".yaml", ".sh", ".txt",
            ".css", ".html", ".plist", ".cfg", ".ini", ".mdc"}


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))        # src/kb_distillery/lint -> repo


def terms_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "kb-distillery", TERMS_FILE)


def load_terms() -> list[str]:
    """The configured personal terms: `$KB_PRIVACY_TERMS` (comma or pipe list), else `terms` in privacy.toml, else []."""
    raw = os.environ.get(ENV_TERMS, "")
    if raw.strip():
        found = re.split(r"[,|]", raw)
    else:
        try:
            with open(terms_path(), "rb") as f:
                value = tomllib.load(f).get("terms") or []
        except (OSError, tomllib.TOMLDecodeError):
            value = []
        found = value if isinstance(value, list) else [value]
    return sorted({t.strip() for t in found if isinstance(t, str) and t.strip()})


def personal_pattern(terms: list[str] | None = None) -> re.Pattern | None:
    """One case-insensitive pattern for the terms, None when there are none (then nothing personal can match)."""
    terms = load_terms() if terms is None else terms
    return re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.I) if terms else None


def matches(line: str, personal: re.Pattern | None = None) -> bool:
    return bool((personal and personal.search(line)) or SECRET.search(line))


def scan(root: str | None = None, terms: list[str] | None = None) -> dict[str, int]:
    """{path relative to the repo root: number of matching lines} for every text file outside the skipped folders.
    `terms` default to the configured ones (`load_terms`)."""
    root = root or repo_root()
    personal = personal_pattern(terms)
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
                    n = sum(1 for line in f if matches(line, personal))
            except (OSError, UnicodeDecodeError):
                continue
            if n:
                out[rel] = n
    return out


def main(argv=None) -> int:
    if not load_terms():
        print(f"note: no personal terms configured (${ENV_TERMS} or {terms_path()}): checking token shapes only", file=sys.stderr)
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

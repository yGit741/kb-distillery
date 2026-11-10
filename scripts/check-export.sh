#!/usr/bin/env bash
# Public-readiness check of what `git archive HEAD` (the public export) ships.
#   bash scripts/check-export.sh [repo-dir]
# 1. The owner-only paths are marked `export-ignore` in .gitattributes (OWNER_ONLY below, one per line).
# 2. `git archive HEAD` holds none of them.
# 3. The privacy ratchet (kb_distillery.lint.privacy) finds no personal string in the archive beyond the files listed
#    in tests/lint/privacy_baseline.txt. The terms are read from $KB_PRIVACY_TERMS or ~/.config/kb-distillery/privacy.toml
#    and are never in this script; with neither (CI), that sub-check is skipped with a message and only the
#    token shapes (API keys, private keys) are checked. OWNER_ONLY names real tracked files (a missing path is skipped,
#    so a made-up one would never be tested).
# Exit 0 when every check that ran passed.
set -euo pipefail
engine="$(cd "$(dirname "$0")/.." && pwd)"      # where kb_distillery.lint.privacy lives
repo="$(cd "${1:-$engine}" && pwd)"
cd "$repo"

OWNER_ONLY="CLAUDE.md
.claude
.claude/settings.json
.integrator.toml
.github/workflows/deploy-main.yml
examples/launchd/switch.sh
docs/archive/ROADMAP.md"

fail=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL: $*" >&2; fail=1; }

say "[1/3] export-ignore attributes"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  # A path absent from this tree has nothing to leak; one that exists must be marked.
  if [ -e "$path" ] || git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    attr="$(git check-attr export-ignore -- "$path" | sed 's/.*: //')"
    if [ "$attr" = "set" ]; then say "  ok  $path"; else bad "$path is not export-ignored (add it to .gitattributes)"; fi
  fi
done <<PATHS
$OWNER_ONLY
PATHS

say "[2/3] git archive HEAD contents"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git archive HEAD | tar -x -C "$work"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ -e "$work/$path" ]; then bad "$path is in the archive"; else say "  ok  $path absent"; fi
done <<PATHS
$OWNER_ONLY
PATHS

say "[3/3] privacy ratchet over the archive"
if [ -z "${KB_PRIVACY_TERMS:-}" ] && [ ! -s "$HOME/.config/kb-distillery/privacy.toml" ]; then
  say "  no privacy terms found (\$KB_PRIVACY_TERMS or ~/.config/kb-distillery/privacy.toml): skipping the term check, token shapes only"
fi
scan='
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "src"))
from kb_distillery.lint import privacy
root = sys.argv[2]
try:
    with open(os.path.join(root, "tests/lint/privacy_baseline.txt"), encoding="utf-8") as f:
        allowed = {l.strip() for l in f if l.strip() and not l.startswith("#")}
except OSError:
    allowed = set()
print("  terms loaded: " + str(len(privacy.load_terms())), file=sys.stderr)
for rel, n in sorted(privacy.scan(root).items()):
    if rel not in allowed:
        print(rel + " (" + str(n) + " line(s))")
'
py="${PYTHON:-}"
if [ -z "$py" ]; then
  for c in python3 python3.13 python3.12 python3.11; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import tomllib' 2>/dev/null; then py="$c"; break; fi
  done
fi
if [ -z "$py" ]; then bad "no Python 3.11+ found (set PYTHON=...)"; py=false; fi
if ! leaks="$("$py" -I -c "$scan" "$engine" "$work")"; then
  [ "$py" = false ] || bad "the privacy scan could not run"
  leaks=""
fi
if [ -n "$leaks" ]; then
  bad "personal strings or secrets in the public export:"
  printf '%s\n' "$leaks" | sed 's/^/    /' >&2
else
  say "  ok  no file outside the baseline matches"
fi

if [ "$fail" -ne 0 ]; then say "check-export: FAILED" >&2; exit 1; fi
say "check-export: ok"

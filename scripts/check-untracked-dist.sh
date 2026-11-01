#!/usr/bin/env bash
# Fail when build output is tracked: src/kb_distillery/_webapp is generated (kb_distillery.api and share build it from source),
# and a committed copy goes stale on merges and silently drops features from the served app.
set -euo pipefail
cd "$(dirname "$0")/.."
tracked=$(git ls-files -- src/kb_distillery/_webapp web/dist-share | head -5)
if [[ -n "$tracked" ]]; then
  echo "src/kb_distillery/_webapp is build output and must stay untracked; found tracked files:" >&2
  echo "$tracked" >&2
  echo "fix: remove them from the index (the PR's commit drops them) — they are rebuilt from source" >&2
  exit 1
fi

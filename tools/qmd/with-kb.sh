#!/usr/bin/env bash
# Run a tools/qmd script against the selected knowledge base: resolves --kb <id|path> / $KB
# through `python -m kb.kbconfig root` and hands node the folder as $KB_ROOT (tools/qmd/kbroot.mjs).
# Usage: bash tools/qmd/with-kb.sh <script.mjs> [--kb <id|path>] [args...]   ($KB_ROOT already set wins)
set -euo pipefail

script="$1"; shift
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kb) export KB="$2"; shift 2 ;;
    --kb=*) export KB="${1#--kb=}"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
if [[ -z "${KB_ROOT:-}" ]]; then
  KB_ROOT="$(python -m kb.kbconfig root)" || exit 1
  export KB_ROOT
fi
echo "knowledge base: ${KB:-default} ($KB_ROOT)" >&2
exec node --disable-warning=ExperimentalWarning "$script" ${args[@]+"${args[@]}"}

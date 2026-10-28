#!/bin/bash
# Shared by the knowledge-base git hooks: find the explorer (the engine) from inside a knowledge base repo
# and run its code against this repo as the vault. Sourced, not executed.
#   KB_EXPLORER_DIR  the explorer checkout (default: ../../knowledge-base-explorer next to knowledge-bases/)
#   KB_ROOT          this knowledge base (the repo the hook runs in)
kb_root="$(git rev-parse --show-toplevel)"
explorer="${KB_EXPLORER_DIR:-$(cd "$kb_root/../.." 2>/dev/null && pwd)/knowledge-base-explorer}"
if [ ! -d "$explorer/backend/src/kb" ]; then
  echo "kb hook: explorer not found at $explorer — set KB_EXPLORER_DIR" >&2
  exit 1
fi
py="$explorer/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
export KB_ROOT="$kb_root"
export PYTHONPATH="$explorer/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export KB_EXPLORER_DIR="$explorer"

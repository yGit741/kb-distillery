#!/bin/bash
# Shared by the knowledge-base git hooks: find the engine (kb-distillery) from inside a knowledge base repo
# and run its code against this repo as the vault. Sourced, not executed.
#   KBD_DIR  the engine checkout (default: ../.. — a knowledge base lives at <engine>/kbs/<id>)
#   KB_ROOT  this knowledge base (the repo the hook runs in)
kb_root="$(git rev-parse --show-toplevel)"
engine="${KBD_DIR:-$(cd "$kb_root/../.." 2>/dev/null && pwd)}"
if [ ! -d "$engine/backend/src/kb" ]; then
  echo "kb hook: engine not found at $engine — set KBD_DIR" >&2
  exit 1
fi
py="$engine/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
export KB_ROOT="$kb_root"
export PYTHONPATH="$engine/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export KBD_DIR="$engine"

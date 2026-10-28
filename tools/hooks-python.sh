#!/bin/bash
# The explorer's own Claude Code hooks: run a kb module with pixi's python (tomllib needs >= 3.11), else python3.
# Usage: bash tools/hooks-python.sh kb.git.guard
root="$(cd "$(dirname "$0")/.." && pwd)"
py="$root/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
PYTHONPATH="$root/backend/src${PYTHONPATH:+:$PYTHONPATH}" exec "$py" -m "$@"

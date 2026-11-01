#!/bin/bash
# The explorer's own Claude Code hooks: run a kb module with pixi's python (tomllib needs >= 3.11), else python3.
# Usage: bash scripts/hooks-python.sh kb_distillery.git.guard
root="$(cd "$(dirname "$0")/.." && pwd)"
py="$root/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
"$py" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' "$1" >/dev/null 2>&1 || {
  echo "hook: cannot import $1 (python: $py) - refusing (fail closed)" >&2
  exit 2
}
exec "$py" -m "$@"

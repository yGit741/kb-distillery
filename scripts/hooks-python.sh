#!/bin/bash
# Run a kb_distillery module as a hook with the checkout's python (tomllib needs >= 3.11), else python3. Never fails open:
# Claude Code blocks a tool call only on exit 2, so an import failure exits 2.
# Usage: bash scripts/hooks-python.sh kb_distillery.git.guard [args]
#
# The hook always runs the code of the checkout it belongs to: when this checkout has src/kb_distillery it is put first
# on the path (a worktree's hooks must not enforce the primary's, possibly stale, installed copy, and a missing or
# stale editable install must not lock a session out of its own tools). Outside a checkout the module must import from
# the installed package. A module that imports from neither exits 2.
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ -d "$root/src/kb_distillery" ]; then
  export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi
py="$root/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
can_import() { "$py" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' "$1" >/dev/null 2>&1; }
can_import "$1" || {
  echo "hook: cannot import $1 (python: $py) - refusing (fail closed)" >&2
  exit 2
}
exec "$py" -m "$@"

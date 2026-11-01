#!/bin/bash
# Run a kb_distillery module as a hook with the checkout's python (tomllib needs >= 3.11), else python3. Never fails open:
# Claude Code blocks a tool call only on exit 2, so an import failure exits 2.
# Usage: bash scripts/hooks-python.sh kb_distillery.git.guard [args]
#
# No PYTHONPATH is set: the module must import from the installed package (the env's editable install of this
# repository, `pixi install`). Only when it does NOT import, and this checkout has the source, the checkout's src/ is
# put on the path as a bootstrap, so a stale or missing editable install cannot lock every session out of its own
# tools. A module that imports from neither exits 2.
root="$(cd "$(dirname "$0")/.." && pwd)"
py="$root/.pixi/envs/default/bin/python"
[ -x "$py" ] || py=python3
can_import() { "$py" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' "$1" >/dev/null 2>&1; }
if ! can_import "$1"; then
  if [ -d "$root/src/kb_distillery" ]; then
    export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
  fi
  can_import "$1" || {
    echo "hook: cannot import $1 (python: $py) - refusing (fail closed)" >&2
    exit 2
  }
fi
exec "$py" -m "$@"

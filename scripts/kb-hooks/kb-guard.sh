#!/bin/bash
# Claude Code PreToolUse (Write|Edit) inside a knowledge base: the engine's write guard, this repo as the vault.
cd "$CLAUDE_PROJECT_DIR" || exit 0
. "$(dirname "$0")/env.sh"
exec "$py" -m kb_distillery.git.guard

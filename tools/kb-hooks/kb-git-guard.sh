#!/bin/bash
# Claude Code PreToolUse (Bash) inside a knowledge base: block ad-hoc git writes (the engine's git_guard).
cd "$CLAUDE_PROJECT_DIR" || exit 0
. "$(dirname "$0")/env.sh"
exec "$py" -m kb.git.git_guard

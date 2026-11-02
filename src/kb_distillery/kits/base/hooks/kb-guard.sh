#!/bin/bash
# Claude Code PreToolUse (Write|Edit) inside a knowledge base: the write guard, this folder as the vault.
# Claude Code blocks a tool call only on exit 2, so every failure here (no `distill`, no project dir, a crash) is 2.
command -v distill >/dev/null 2>&1 || {
  echo "kb hook guard: 'distill' is not on PATH - refusing (fail closed). Install kb-distillery (pip install kb-distillery) or put its bin folder on PATH." >&2
  exit 2
}
[ -n "$CLAUDE_PROJECT_DIR" ] || { echo "kb hook: CLAUDE_PROJECT_DIR is not set - refusing (fail closed)" >&2; exit 2; }
cd "$CLAUDE_PROJECT_DIR" || exit 2
# the project dir is the kb when it holds a kb.toml (also a kb nested in another repo); else the repo it sits in
if [ -f kb.toml ]; then KB_ROOT="$PWD"; else KB_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || KB_ROOT="$PWD"; fi
export KB_ROOT
distill hook guard || exit 2

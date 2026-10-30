#!/usr/bin/env bash
# Install the engine's hooks into a knowledge base: git hooks (core.hooksPath → tools/kb-hooks, local config,
# nothing committed) and Claude Code hooks (.claude/settings.json + .claude/hooks/ pointing back at the engine).
# Usage: kbd install-kb-hooks --kb <id|path>      (or: pixi run install-kb-hooks -- --kb <id|path>)
# For a kb at <engine>/kbs/<id> the hooks path is relative (../../tools/kb-hooks), so it survives renaming the engine.
set -euo pipefail
cd "$(dirname "$0")/.."
engine="$(pwd -P)"
kb_root="$(python -m kb.kbconfig show "$@" | sed -n 's/^root  *//p')"
[ -d "$kb_root" ] || { echo "no knowledge base root (pass --kb <id|path>)" >&2; exit 1; }
mkdir -p "$kb_root/.claude/hooks"
cp tools/kb-hooks/env.sh tools/kb-hooks/kb-guard.sh tools/kb-hooks/kb-git-guard.sh "$kb_root/.claude/hooks/"
[ -f "$kb_root/.claude/settings.json" ] && { echo "note: replacing $kb_root/.claude/settings.json (previous copy: settings.json.bak)"; cp "$kb_root/.claude/settings.json" "$kb_root/.claude/settings.json.bak"; }
cp tools/kb-hooks/claude-settings.json "$kb_root/.claude/settings.json"
chmod +x tools/kb-hooks/*.sh tools/kb-hooks/pre-commit tools/kb-hooks/commit-msg tools/kb-hooks/pre-push "$kb_root/.claude/hooks/"*.sh
if [ -d "$kb_root/.git" ]; then
  hooks_path="$(python -c 'import sys, kb.kbconfig as k; print(k.hooks_path_for(sys.argv[1]))' "$kb_root")"
  git -C "$kb_root" config core.hooksPath "$hooks_path"
  echo "git hooks: $kb_root core.hooksPath → $hooks_path"
else
  echo "git hooks: $kb_root is not a git repository — only the Claude Code hooks were installed"
fi
echo "claude hooks: $kb_root/.claude/settings.json (guard + git guard run the engine's code from $engine with KB_ROOT=$kb_root)"

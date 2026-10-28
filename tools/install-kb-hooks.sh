#!/usr/bin/env bash
# Install the explorer's hooks into a knowledge base: git hooks (core.hooksPath → tools/kb-hooks, local config,
# nothing committed) and Claude Code hooks (.claude/settings.json + .claude/hooks/ pointing back at the explorer).
# Usage: pixi run install-kb-hooks -- --kb <id>
set -euo pipefail
cd "$(dirname "$0")/.."
explorer="$PWD"
kb_root="$(python -m kb.kbconfig show "$@" | sed -n 's/^root  *//p')"
[ -d "$kb_root" ] || { echo "no knowledge base root (pass --kb <id>)" >&2; exit 1; }
mkdir -p "$kb_root/.claude/hooks"
cp tools/kb-hooks/env.sh tools/kb-hooks/kb-guard.sh tools/kb-hooks/kb-git-guard.sh "$kb_root/.claude/hooks/"
[ -f "$kb_root/.claude/settings.json" ] && { echo "note: replacing $kb_root/.claude/settings.json (previous copy: settings.json.bak)"; cp "$kb_root/.claude/settings.json" "$kb_root/.claude/settings.json.bak"; }
cp tools/kb-hooks/claude-settings.json "$kb_root/.claude/settings.json"
chmod +x tools/kb-hooks/*.sh tools/kb-hooks/pre-commit tools/kb-hooks/commit-msg tools/kb-hooks/pre-push "$kb_root/.claude/hooks/"*.sh
if [ -d "$kb_root/.git" ]; then
  git -C "$kb_root" config core.hooksPath "$explorer/tools/kb-hooks"
  echo "git hooks: $kb_root core.hooksPath → $explorer/tools/kb-hooks"
else
  echo "git hooks: $kb_root is not a git repository — only the Claude Code hooks were installed"
fi
echo "claude hooks: $kb_root/.claude/settings.json (guard + git guard run the explorer's code with KB_ROOT=$kb_root)"

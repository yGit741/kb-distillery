#!/bin/bash
# Block ad-hoc agent git writes; allow only the lane entry points (daily-sync, ship).
# Shared by Cursor (beforeShellExecution: {"command": ...}, JSON verdict on stdout)
# and Claude Code (PreToolUse Bash: {"tool_input": {"command": ...}}, exit 2 to deny).
input=$(cat)
read -r client command < <(echo "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ti = d.get('tool_input')
cmd = (ti or {}).get('command') if isinstance(ti, dict) else d.get('command', '')
print('claude' if isinstance(ti, dict) else 'cursor', (cmd or '').replace('\n', ' '))
")

allow() {
  [[ "$client" == cursor ]] && echo '{"permission": "allow"}'
  exit 0
}

if echo "$command" | grep -qE 'pixi run (daily-sync|ship|lanes)|meta/daily_sync|meta\.daily_sync|meta/ship\.py'; then
  allow
fi

if echo "$command" | grep -qE 'git (commit|push|merge|rebase|cherry-pick|tag )|gh pr'; then
  msg="Git write blocked — knowledge syncs nightly (pixi run daily-sync); tooling ships via pixi run ship -- <msg> when the user asks."
  if [[ "$client" == claude ]]; then
    echo "$msg" >&2
    exit 2
  fi
  echo "{\"permission\": \"deny\", \"user_message\": \"$msg\", \"agent_message\": \"Do not run git commit/push. Use pixi run daily-sync or pixi run ship only.\"}"
  exit 0
fi

allow

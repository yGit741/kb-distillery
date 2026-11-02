#!/usr/bin/env bash
# Install (or reinstall) the deploy owner (kb_distillery.publish.cloudflare.owner run) as a user launchd agent: KeepAlive,
# the one process that builds + deploys main to the private site. Everything else only nudges it.
# Usage: pixi run install-deploy-owner            uninstall: pixi run install-deploy-owner -- --uninstall
set -euo pipefail

# capture_env PLIST — copy the invoking shell's proxy/CA env (names below, if set) and a PATH with the
# pixi/node/homebrew bins into PLIST's EnvironmentVariables, so node/wrangler under launchd trust the
# corporate proxy CA. Never copies secrets (*TOKEN*, *KEY*, *SECRET*, CLOUDFLARE_*). Prints names only.
CAPTURE_VARS=(NODE_EXTRA_CA_CERTS SSL_CERT_FILE REQUESTS_CA_BUNDLE CURL_CA_BUNDLE
  HTTPS_PROXY HTTP_PROXY NO_PROXY ALL_PROXY https_proxy http_proxy no_proxy all_proxy)
capture_env() {
  local plist="$1" name val dir captured=()
  plutil -replace EnvironmentVariables -json '{}' "$plist"
  for name in "${CAPTURE_VARS[@]}"; do
    case "$name" in *TOKEN*|*KEY*|*SECRET*|CLOUDFLARE_*) continue ;; esac
    val="${!name:-}"
    [[ -n "$val" ]] || continue
    [[ "$val" == *@* ]] && { echo "skipped $name (contains credentials)"; continue; }
    plutil -replace "EnvironmentVariables.$name" -string "$val" "$plist"
    captured+=("$name")
  done
  local path_out=""
  for dir in "$HOME/.pixi/bin" "$(dirname "$(command -v pixi 2>/dev/null || echo /nonexistent/x)")" \
             "$(dirname "$(command -v node 2>/dev/null || echo /nonexistent/x)")" \
             /opt/homebrew/bin /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
    [[ -d "$dir" && ":$path_out:" != *":$dir:"* ]] && path_out="${path_out:+$path_out:}$dir"
  done
  plutil -replace EnvironmentVariables.PATH -string "$path_out" "$plist"
  captured+=(PATH)
  echo "launchd env captured: ${captured[*]}"
}
[[ "${BASH_SOURCE[0]}" == "$0" ]] || return 0  # sourced (tests): only define capture_env

cd "$(dirname "$0")/../.."
LABEL=com.kb-distillery.deploy-owner
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/kb-distillery-deploy-owner.log"
PIXI="$(command -v pixi || echo "$HOME/.pixi/bin/pixi")"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
# the pre-rename label (installed by older checkouts): stop it and remove its plist
OLD="com.thesis-kb.deploy-owner"
launchctl bootout "gui/$(id -u)/$OLD" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$OLD.plist"
if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$DEST"
  echo "uninstalled $LABEL"
  exit 0
fi

mkdir -p "$(dirname "$DEST")" "$(dirname "$LOG")"
sed -e "s|__ROOT__|$PWD|g" -e "s|__PIXI__|$PIXI|g" -e "s|__LOG__|$LOG|g" \
  examples/launchd/$LABEL.plist >"$DEST"
capture_env "$DEST"
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $LABEL → always on, log: $LOG"
echo "state: pixi run python -m kb_distillery.publish.cloudflare.owner status"

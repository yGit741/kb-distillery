#!/usr/bin/env bash
# One-script install for macOS, Linux and WSL2: installs pixi if needed, sets up the environment, creates a default
# knowledge base when there is none, checks the setup and opens the app. No questions, no model key.
# Usage: ./install.sh [--no-open] [--kb-id <id>] [--kit base|research] [--dir <parent>] [--yes] [--dry-run]
set -euo pipefail

START_DIR="$(pwd)"
cd "$(dirname "$0")"
OPEN=1
DRY=0
KB_ID_ARG=""
KIT="base"
DIR_ARG=""
STEP="start"

usage() { sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --no-open) OPEN=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --yes|-y) shift ;;  # accepted for scripts; the installer never asks
    --kb-id) KB_ID_ARG="${2:?--kb-id needs a value}"; shift 2 ;;
    --kb-id=*) KB_ID_ARG="${1#--kb-id=}"; shift ;;
    --kit) KIT="${2:?--kit needs a value}"; shift 2 ;;
    --kit=*) KIT="${1#--kit=}"; shift ;;
    --dir) DIR_ARG="${2:?--dir needs a value}"; shift 2 ;;
    --dir=*) DIR_ARG="${1#--dir=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$KIT" in base|research) ;; *) echo "install.sh: --kit must be base or research" >&2; exit 2 ;; esac

on_error() {
  echo "install.sh: step '$STEP' failed. Fix the message above, then retry: ./install.sh" >&2
}
trap on_error ERR

say() { echo "install.sh: $*"; }
# Run a command, or only print it with --dry-run.
run() {
  if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi
}

# (a) OS
STEP="detect OS"
case "$(uname -s)" in
  Darwin) OS="macOS" ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null; then OS="WSL2"; else OS="Linux"; fi ;;
  *)
    echo "install.sh: unsupported system '$(uname -s)'. On Windows install WSL2 with Ubuntu and run this inside it: see docs/getting-started.md (Windows (WSL2))." >&2
    exit 2 ;;
esac
say "[1/7] system: $OS"

# (b) pixi
STEP="install pixi"
if command -v pixi >/dev/null 2>&1; then
  say "[2/7] pixi: found"
else
  say "[2/7] pixi: missing, installing with the official installer (https://pixi.sh/install.sh)"
  if [ "$DRY" = 1 ]; then
    echo "+ curl -fsSL https://pixi.sh/install.sh | bash"
  else
    curl -fsSL https://pixi.sh/install.sh | bash
  fi
  export PATH="$HOME/.pixi/bin:$PATH"
  say "added \$HOME/.pixi/bin to PATH for this run only; the pixi installer may have edited your shell profile, open a new terminal to use pixi later"
  if [ "$DRY" = 0 ] && ! command -v pixi >/dev/null 2>&1; then
    echo "install.sh: pixi is still not on PATH after installing" >&2
    false
  fi
fi

# (c) environment
STEP="pixi install"
say "[3/7] environment"
run pixi install

# (d) doctor before creating anything
STEP="doctor (before)"
say "[4/7] doctor"
if [ "$DRY" = 1 ]; then echo "+ pixi run distill doctor"; else pixi run distill doctor || say "doctor reported problems (no knowledge base yet is expected); continuing"; fi

# (e) knowledge base
STEP="knowledge base"
BASES="${DIR_ARG:-${KB_DISTILLERY_HOME:-$HOME/knowledge}}"
case "$BASES" in "~"|"~/"*) BASES="$HOME${BASES#"~"}" ;; esac
case "$BASES" in /*) ;; *) BASES="$START_DIR/$BASES" ;; esac
if [ -n "$DIR_ARG" ]; then export KB_DISTILLERY_HOME="$BASES"; fi
KB_ID=""
if [ -n "$KB_ID_ARG" ] && [ -f "$BASES/$KB_ID_ARG/kb.toml" ]; then
  KB_ID="$KB_ID_ARG"
elif [ -z "$KB_ID_ARG" ] && [ -f "$BASES/my-kb/kb.toml" ]; then
  KB_ID="my-kb"
elif [ -z "$KB_ID_ARG" ] && [ -d "$BASES" ]; then
  for f in "$BASES"/*/kb.toml; do
    [ -f "$f" ] || continue
    KB_ID="$(basename "$(dirname "$f")")"
    break
  done
fi
if [ -n "$KB_ID" ]; then
  say "[5/7] knowledge base: using existing '$KB_ID' in $BASES"
else
  KB_ID="${KB_ID_ARG:-my-kb}"
  say "[5/7] knowledge base: creating '$KB_ID' ($KIT) in $BASES"
  run pixi run distill init --kb-id "$KB_ID" --name "My knowledge base" --kit "$KIT" --dir "$BASES" --yes
fi

# (f) doctor on the kb
STEP="doctor (kb)"
say "[6/7] doctor for '$KB_ID'"
run pixi run distill doctor --kb "$KB_ID"

# (g) open
STEP="launch"
if [ "$OPEN" = 1 ]; then
  say "[7/7] opening the app (first launch fetches or builds the web bundle and can take a few minutes)"
  run pixi run distill launch --kb "$KB_ID"
else
  say "[7/7] skipped (--no-open). Open it later: pixi run distill launch --kb $KB_ID"
fi
say "done"

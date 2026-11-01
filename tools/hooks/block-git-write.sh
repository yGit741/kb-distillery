#!/bin/bash
# Forwarding stub (removed in Phase 9): older settings.json copies still name tools/hooks/block-git-write.sh.
exec bash "$(dirname "$0")/../../scripts/hooks/block-git-write.sh" "$@"

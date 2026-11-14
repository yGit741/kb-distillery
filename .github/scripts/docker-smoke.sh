#!/usr/bin/env bash
# Runs a built kb-distillery image the way a self-hoster would and checks its HEALTHCHECK:
#   1. with the proxy identity env, the container must report `healthy`;
#   2. with the server replaced by `sleep` (setup fine, nothing listening on 8765), it must report `unhealthy`.
# Usage: .github/scripts/docker-smoke.sh [image]   (default kb-distillery:ci; CI and a local Colima/Docker run use the same script)
# The health interval is shortened with --health-* flags so the check runs in seconds; the command itself is the image's.
set -euo pipefail

IMAGE="${1:-kb-distillery:ci}"
TIMEOUT="${KB_DOCKER_SMOKE_TIMEOUT:-120}"
IDENTITY=(-e KB_AUTH_EMAIL=ci@example.com -e KB_AUTH_JWKS_URL=https://proxy.example.com/keys -e KB_AUTH_AUDIENCE=ci)
FAST=(--health-interval=3s --health-timeout=30s --health-start-period=5s --health-retries=3)
NAMES=()

cleanup() { for n in ${NAMES[@]+"${NAMES[@]}"}; do docker rm -f "$n" >/dev/null 2>&1 || true; done; }
trap cleanup EXIT

# wait_for <container> <wanted status>: polls until the health status is the wanted one, fails on timeout or exit
wait_for() {
  local name="$1" want="$2" status running end=$((SECONDS + TIMEOUT))
  while [ "$SECONDS" -lt "$end" ]; do
    running="$(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || echo gone)"
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo gone)"
    if [ "$status" = "$want" ]; then
      echo "docker-smoke: $name is $status"
      return 0
    fi
    if [ "$want" = healthy ] && [ "$status" = unhealthy ]; then
      echo "docker-smoke: $name is unhealthy" >&2
      break
    fi
    if [ "$running" != true ]; then
      echo "docker-smoke: $name exited before it was $want (status $status)" >&2
      break
    fi
    sleep 2
  done
  echo "docker-smoke: $name did not become $want within ${TIMEOUT}s (last status: ${status:-unknown})" >&2
  echo "--- health log ---" >&2
  docker inspect --format '{{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}' "$name" >&2 || true
  echo "--- container log ---" >&2
  docker logs "$name" >&2 || true
  return 1
}

run() {  # run <name> <docker run args...>
  local name="$1"; shift
  NAMES+=("$name")
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" "$@" >/dev/null
}

UP="kb-smoke-up-$$" DOWN="kb-smoke-down-$$"
run "$UP" "${IDENTITY[@]}" "${FAST[@]}" "$IMAGE"
wait_for "$UP" healthy

run "$DOWN" "${IDENTITY[@]}" "${FAST[@]}" "$IMAGE" sleep 600
wait_for "$DOWN" unhealthy

echo "docker-smoke: ok ($IMAGE)"

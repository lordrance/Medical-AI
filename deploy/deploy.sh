#!/usr/bin/env bash
# Server-side update & restart script.
# Called by deploy.ps1 from your local machine, or run manually on the server.
#
# Usage (on server):  bash deploy/deploy.sh
set -euo pipefail

GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
log()  { echo "${GREEN}[deploy]${RESET} $*"; }
warn() { echo "${YELLOW}[deploy]${RESET} $*"; }

BRANCH="${1:-V4}"

log "pulling latest ${BRANCH}..."
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

log "rebuilding & restarting containers..."
docker compose -f docker-compose.prod.yml up -d --build

log "waiting for backend healthy (max 120s)..."
for i in $(seq 1 60); do
  cid=$(docker compose -f docker-compose.prod.yml ps -q backend 2>/dev/null || true)
  if [ -n "$cid" ]; then
    status=$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)
    if [ "$status" = "healthy" ]; then
      log "${BOLD}backend healthy${RESET}"
      break
    fi
  fi
  sleep 2
done

echo
log "${BOLD}deploy complete${RESET}"
docker compose -f docker-compose.prod.yml ps
echo
log "worker count: $(docker compose -f docker-compose.prod.yml logs backend 2>/dev/null | grep -c 'Booting worker' || echo 0)"
log "last 3 commits:"
git log --oneline -3

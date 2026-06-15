#!/usr/bin/env bash
# Medical-AI auto-deploy script — run by GitHub Actions via SSH.
#
# Pulls pre-built images from ghcr.io and restarts the stack without
# re-building locally.  Designed to be idempotent: re-running this script
# is safe and just re-pulls + re-creates changed containers.
#
# Prerequisites on the server (set up once by deploy/setup.sh):
#   - Docker + docker compose v2
#   - .env at the repo root (with SITE_DOMAIN, ADMIN_TOKEN, POSTGRES_PASSWORD)
#   - Logged into ghcr.io (docker login ghcr.io -u <user> --password-stdin < <token>)

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
POLL_INTERVAL=5
MAX_RETRIES=24   # 24 * 5 = 120 seconds max wait

# --- colors (same scheme as setup.sh) ---
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
log()  { echo "${BLUE}[deploy]${RESET} $*"; }
warn() { echo "${YELLOW}[deploy]${RESET} $*"; }
fail() { echo "${RED}[deploy]${RESET} $*" >&2; exit 1; }
ok()   { echo "${GREEN}[deploy]${RESET} $*"; }

# --- 0. Must be in repo root ----------------------------------------------
if [ ! -f "${COMPOSE_FILE}" ]; then
  fail "Please run from the Medical-AI repo root (${COMPOSE_FILE} not found)."
fi

# IMAGE_TAG is set by the GitHub Actions workflow; default to "latest" for
# manual invocation.
IMAGE_TAG="${IMAGE_TAG:-latest}"
export IMAGE_TAG

# --- 1. Pull latest code --------------------------------------------------
log "Pulling latest V5 code..."
git fetch origin V5
git reset --hard origin/V5
ok "Repo updated to $(git rev-parse --short HEAD)"

# --- 2. Pull pre-built images from ghcr.io --------------------------------
log "Pulling pre-built images (IMAGE_TAG=${IMAGE_TAG})..."
docker compose -f "${COMPOSE_FILE}" pull
ok "Images pulled"

# --- 3. Restart the stack -------------------------------------------------
log "Restarting services..."
docker compose -f "${COMPOSE_FILE}" up -d
ok "Stack restarted"

# --- 4. Wait for all services with healthchecks to become healthy ---------
log "Waiting for services to become healthy (up to 120 seconds)..."
for i in $(seq 1 ${MAX_RETRIES}); do
  UNHEALTHY=0
  while IFS=$'\t' read -r svc status health; do
    # Only check services that have a healthcheck defined
    if [ "${health}" != "" ] && [ "${health}" != "<none>" ]; then
      if [ "${health}" != "healthy" ]; then
        UNHEALTHY=$((UNHEALTHY + 1))
      fi
    fi
  done < <(docker compose -f "${COMPOSE_FILE}" ps --format "{{.Service}}\t{{.Status}}\t{{.Health}}")

  if [ "${UNHEALTHY}" -eq 0 ]; then
    ok "All services healthy"
    break
  fi

  if [ "${i}" -eq "${MAX_RETRIES}" ]; then
    warn "Timed out waiting for ${UNHEALTHY} service(s) to become healthy."
    warn "Current status:"
    docker compose -f "${COMPOSE_FILE}" ps
    fail "Deploy aborted — services not healthy."
  fi

  sleep "${POLL_INTERVAL}"
done

# --- 5. Summary ------------------------------------------------------------
echo ""
ok "${BOLD}Deploy complete${RESET}"
echo "  Images:  ghcr.io/lordrance/medical-ai-{backend,frontend}:${IMAGE_TAG}"
echo "  Stack:   $(docker compose -f "${COMPOSE_FILE}" ps --services | tr '\n' ' ')"
echo "  Check:   docker compose -f ${COMPOSE_FILE} ps"
echo "  Logs:    docker compose -f ${COMPOSE_FILE} logs -f"

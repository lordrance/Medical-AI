#!/usr/bin/env bash
# Backend container entrypoint.
#
# Steps performed before launching the main process:
#   1. (optional) Wait for the database to accept connections.
#   2. Run Alembic migrations to "head".
#   3. (optional) Seed cases / order_templates if SEED_ON_START=true.
#   4. exec the CMD passed to the container.
#
# Toggle behaviour via env vars:
#   RUN_MIGRATIONS=true|false   (default: true)
#   SEED_ON_START=true|false    (default: true; idempotent upserts)
#   WAIT_FOR_DB=true|false      (default: true when DATABASE_URL points at host:port)

set -euo pipefail

log() { echo "[entrypoint] $*"; }

if [[ "${WAIT_FOR_DB:-true}" == "true" && "${DATABASE_URL:-}" == *"://"* ]]; then
  # Best-effort: parse host:port out of postgresql+asyncpg://user:pass@host:port/db
  host_port=$(python -c "
import os, urllib.parse as u
url = os.environ.get('DATABASE_URL','')
p = u.urlparse(url.replace('postgresql+asyncpg', 'postgresql').replace('sqlite+aiosqlite', 'sqlite'))
if p.scheme.startswith('sqlite'):
    print('')
else:
    print(f'{p.hostname}:{p.port or 5432}')
")
  if [[ -n "$host_port" ]]; then
    host="${host_port%:*}"
    port="${host_port##*:}"
    log "waiting for database at ${host}:${port}..."
    for i in $(seq 1 60); do
      if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
        log "database is reachable"
        break
      fi
      sleep 1
    done
  fi
fi

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  log "running alembic upgrade head..."
  alembic upgrade head
fi

if [[ "${SEED_ON_START:-true}" == "true" ]]; then
  log "seeding cases & order templates (idempotent)..."
  python -m app.scripts.seed
fi

log "exec: $*"
exec "$@"

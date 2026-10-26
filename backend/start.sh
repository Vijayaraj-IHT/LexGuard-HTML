#!/usr/bin/env bash
# LexGuard production start command (Render/free single-service deployment).
set -euo pipefail

cd "$(dirname "$0")"

if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  echo "[LexGuard] Applying idempotent Phase-0 migration..."
  python migrate_phase0.py
fi

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips="*"

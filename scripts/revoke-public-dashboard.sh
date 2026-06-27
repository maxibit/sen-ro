#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

DASHBOARD_UID="${DASHBOARD_UID:-sen-overview}"

if [ -z "${PUBLIC_DASHBOARD_UID:-}" ]; then
  echo "PUBLIC_DASHBOARD_UID is required. Set it in .env or export it before running this script." >&2
  exit 1
fi

docker run --rm --network sen-monitor_internal curlimages/curl:8.8.0 \
  -fsS \
  -u "${GF_ADMIN_USER}:${GF_ADMIN_PASSWORD}" \
  -H "Content-Type: application/json" \
  -X PATCH \
  -d '{"isEnabled":false}' \
  "http://grafana:3000/api/dashboards/uid/${DASHBOARD_UID}/public-dashboards/${PUBLIC_DASHBOARD_UID}"

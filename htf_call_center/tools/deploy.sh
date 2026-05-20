#!/bin/sh
# Paste-safe deploy wrapper for the prod VM.
#
# Stops the web container, runs ``odoo -u htf_call_center
# --stop-after-init`` against the configured DB to apply any new
# migrations / view changes / asset rebuilds, then brings the web
# container back up. All inside a single short shell command so the
# terminal's line wrap can't split it apart on paste.
#
# Usage from the repo root on the prod VM:
#   bash htf_call_center/tools/deploy.sh
#
# Honors HTF_CONTAINER, HTF_DB, HTF_COMPOSE_DIR env-var overrides.

set -e

COMPOSE_DIR="${HTF_COMPOSE_DIR:-/opt/odoo-erp-amro-pro}"
CONTAINER="${HTF_CONTAINER:-web-erp-amro-pro}"
DB="${HTF_DB:-numo}"

cd "$COMPOSE_DIR"

echo "==> stopping $CONTAINER..."
docker compose stop web

echo "==> running '-u htf_call_center' against db=$DB ..."
docker compose run --rm web \
    odoo -d "$DB" -u htf_call_center \
        --stop-after-init --no-http --log-level=warn 2>&1 \
    | tail -15

echo "==> bringing $CONTAINER back up..."
docker compose up -d web

echo "==> done. Hard-refresh your browser to pick up the new code."

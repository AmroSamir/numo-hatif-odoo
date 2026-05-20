#!/bin/sh
# Wrapper around diagnose_window.py for paste-safe invocation from the
# host shell. Avoids the long single-line docker exec that keeps getting
# split by the terminal's line wrap on paste.
#
# Usage:
#   bash htf_call_center/tools/diagnose_window.sh                 # default phone hint
#   bash htf_call_center/tools/diagnose_window.sh +966571234567   # custom phone hint
#
# Override the container name with HTF_CONTAINER if your deployment
# uses something other than web-erp-amro-pro.

CONTAINER="${HTF_CONTAINER:-web-erp-amro-pro}"
DB="${HTF_DB:-numo}"
HINT="${1:-${HTF_DIAG_PHONE:-56 186 8578}}"

echo "exec(open('/mnt/extra-addons/htf_call_center/tools/diagnose_window.py').read())" \
    | docker exec -i -e HTF_DIAG_PHONE="$HINT" "$CONTAINER" \
        odoo shell -d "$DB" --no-http --log-level=warn 2>&1 \
    | tail -40

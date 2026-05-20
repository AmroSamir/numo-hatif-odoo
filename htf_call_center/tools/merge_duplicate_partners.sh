#!/bin/sh
# Paste-safe wrapper around merge_duplicate_partners.py.
#
# Usage:
#   bash htf_call_center/tools/merge_duplicate_partners.sh                 # full run
#   HTF_DRY_RUN=1 bash htf_call_center/tools/merge_duplicate_partners.sh   # preview only
#   HTF_PHONE_HINT='+966561868578' bash ...sh                              # scope to one phone
#
# Honors HTF_CONTAINER / HTF_DB / HTF_DRY_RUN / HTF_PHONE_HINT / HTF_LIMIT.

CONTAINER="${HTF_CONTAINER:-web-erp-amro-pro}"
DB="${HTF_DB:-numo}"

echo "exec(open('/mnt/extra-addons/htf_call_center/tools/merge_duplicate_partners.py').read())" \
    | docker exec -i \
        -e HTF_DRY_RUN="${HTF_DRY_RUN:-}" \
        -e HTF_PHONE_HINT="${HTF_PHONE_HINT:-}" \
        -e HTF_LIMIT="${HTF_LIMIT:-}" \
        "$CONTAINER" \
        odoo shell -d "$DB" --no-http --log-level=warn 2>&1 \
    | tail -60

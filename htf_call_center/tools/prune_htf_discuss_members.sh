#!/bin/sh
# Paste-safe wrapper around prune_htf_discuss_members.py.
#
# Usage from the repo root on the prod VM:
#   bash htf_call_center/tools/prune_htf_discuss_members.sh
#
# Preview without writing:
#   HTF_DRY_RUN=1 bash htf_call_center/tools/prune_htf_discuss_members.sh
#
# Scope to one channel:
#   HTF_CHANNEL_HINT=18 bash htf_call_center/tools/prune_htf_discuss_members.sh
#   HTF_CHANNEL_HINT='+966 56 186 8578' bash ...sh
#
# Honors HTF_CONTAINER / HTF_DB / HTF_DRY_RUN / HTF_CHANNEL_HINT / HTF_CHANNEL_LIMIT.

CONTAINER="${HTF_CONTAINER:-web-erp-amro-pro}"
DB="${HTF_DB:-numo}"

echo "exec(open('/mnt/extra-addons/htf_call_center/tools/prune_htf_discuss_members.py').read())" \
    | docker exec -i \
        -e HTF_DRY_RUN="${HTF_DRY_RUN:-}" \
        -e HTF_CHANNEL_HINT="${HTF_CHANNEL_HINT:-}" \
        -e HTF_CHANNEL_LIMIT="${HTF_CHANNEL_LIMIT:-}" \
        "$CONTAINER" \
        odoo shell -d "$DB" --no-http --log-level=warn 2>&1 \
    | tail -80

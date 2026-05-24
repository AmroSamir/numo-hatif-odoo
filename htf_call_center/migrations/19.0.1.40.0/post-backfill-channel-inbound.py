"""Migration 19.0.1.40.0 — backfill discuss.channel.x_htf_last_inbound_at.

v40 introduces a channel-level inbound timestamp so the Discuss
composer's 24h-window gate is robust against duplicate partner
records (phone-format variations create two res.partner rows for the
same human; the inbound webhook resolves to one while the channel was
provisioned for the other, so author-id matching breaks). The inbound
mirror stamps this field going forward; this migration backfills it
for channels that already have history.

Strategy (pure SQL, no API roundtrip): for every Hatif Discuss channel
(``x_htf_partner_id IS NOT NULL``), set ``x_htf_last_inbound_at`` to
the most recent ``mail.message.create_date`` in that channel authored
by a partner that is NOT linked to an active internal user — i.e. a
customer. This deliberately ignores agent (res.users-linked) and
OdooBot authors so the timestamp reflects genuine inbound traffic
regardless of which duplicate partner record carried it.

Idempotent. Safe to re-run — it recomputes from current message
history each time.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE discuss_channel dc
        SET x_htf_last_inbound_at = sub.last_in
        FROM (
            SELECT mm.res_id AS channel_id, MAX(mm.create_date) AS last_in
            FROM mail_message mm
            JOIN discuss_channel c
              ON c.id = mm.res_id
             AND c.x_htf_partner_id IS NOT NULL
            LEFT JOIN res_users u
              ON u.partner_id = mm.author_id
             AND u.active = TRUE
            WHERE mm.model = 'discuss.channel'
              AND mm.author_id IS NOT NULL
              AND u.id IS NULL   -- author is not an internal user => customer
            GROUP BY mm.res_id
        ) sub
        WHERE dc.id = sub.channel_id
        """
    )
    _logger.info(
        "[htf-backfill-1.40] backfilled x_htf_last_inbound_at on %d "
        "Hatif Discuss channel(s) from customer-authored message history",
        cr.rowcount,
    )

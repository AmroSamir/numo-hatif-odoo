"""Migration 19.0.1.29.0 — backfill ``res.partner.x_htf_last_channel_uuid``.

Why this exists: ``services/discuss_mirror.py:_stamp_conversation_metadata``
now also mirrors the Hatif workspace channel UUID to the partner on every
webhook (alongside the conversationId that was already being mirrored).
Existing partners with prior Hatif activity have the conversationId
filled but the channel UUID empty, which means the "Call via Hatif"
deep-link is missing ``?channelId=<uuid>`` until the next webhook
arrives for that partner.

Unlike migration 19.0.1.14.0 which calls out to Hatif, this backfill
is a pure local SQL join: the channel UUID is already stored on
``htf.channel.htf_channel_id`` and every ``htf.message`` /
``htf.call`` row carries an FK to that channel. So we pick the
most-recent message/call per partner and copy its channel UUID over.

Behaviour rules:
- **Idempotent**: only touches rows where
  ``x_htf_last_channel_uuid IS NULL OR ''``.
- **Fast**: single SQL, no API roundtrip — runs in well under a
  second even on large customer tables.
- **Safe**: if a partner has neither prior messages nor calls, they
  are skipped (the next webhook will fill it).
- **Non-fatal**: any error is logged and swallowed so a deploy
  isn't blocked.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Fresh install — nothing to backfill.
        return
    try:
        _run(cr)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-backfill-1.29] migration failed — non-fatal")


def _run(cr):
    # Most recent (htf_call.create_date OR htf_message.create_date) per
    # partner where the row links to a channel that has a UUID.
    # COALESCE picks message vs call by timestamp; tied rows resolve
    # to the call by accident of join order which is fine — both
    # point at the same workspace channel for normal flows.
    sql = """
        WITH latest_per_partner AS (
            SELECT DISTINCT ON (combined.partner_id)
                combined.partner_id,
                combined.htf_channel_uuid
            FROM (
                SELECT
                    m.partner_id,
                    c.htf_channel_id AS htf_channel_uuid,
                    m.create_date AS sort_ts
                FROM htf_message m
                JOIN htf_channel c ON c.id = m.channel_id
                WHERE m.partner_id IS NOT NULL
                  AND c.htf_channel_id IS NOT NULL
                  AND c.htf_channel_id <> ''
                UNION ALL
                SELECT
                    cl.partner_id,
                    c.htf_channel_id AS htf_channel_uuid,
                    cl.create_date AS sort_ts
                FROM htf_call cl
                JOIN htf_channel c ON c.id = cl.channel_id
                WHERE cl.partner_id IS NOT NULL
                  AND c.htf_channel_id IS NOT NULL
                  AND c.htf_channel_id <> ''
            ) combined
            ORDER BY combined.partner_id, combined.sort_ts DESC
        )
        UPDATE res_partner p
        SET x_htf_last_channel_uuid = lpp.htf_channel_uuid
        FROM latest_per_partner lpp
        WHERE p.id = lpp.partner_id
          AND (p.x_htf_last_channel_uuid IS NULL OR p.x_htf_last_channel_uuid = '')
    """
    cr.execute(sql)
    filled = cr.rowcount
    _logger.info(
        "[htf-backfill-1.29] backfilled x_htf_last_channel_uuid on "
        "%d partner(s) from existing htf.message / htf.call history",
        filled,
    )

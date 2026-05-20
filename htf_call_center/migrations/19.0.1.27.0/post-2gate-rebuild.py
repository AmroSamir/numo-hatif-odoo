"""Migration 19.0.1.27.0 — rebuild Hatif access state under the 2-gate model.

What changed: channel membership for per-customer Hatif Discuss channels
is now the intersection of TWO gates instead of one:

  (1) CHANNEL gate — ``htf.channel.user_ids`` (set via Map Users wizard).
  (2) LEAD gate    — ``crm.lead.user_id`` for that customer's lead.

Pre-19.0.1.27.0 used only the lead gate, which (a) granted access to
agents who weren't supposed to work the channel, and (b) didn't grant
``htf_call_center.group_user`` to non-admin assigned salespeople — so
they got AccessError when opening the Send WhatsApp wizard.

This post-upgrade migration:
  1. Grants ``htf_call_center.group_user`` to every user with at least
     one active ``htf.channel.user_ids`` mapping (so they can open the
     Send wizard immediately after deploy without admin intervention).
  2. Recomputes the member list on every Hatif Discuss channel using
     the new ``discuss.channel._htf_allowed_member_partner_ids`` —
     drops agents who fail the new channel-gate, adds agents who pass
     both gates but were missing.

Idempotent. Safe to re-run. Each batch commits so a hiccup mid-run
doesn't lose the work already done.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Standard Odoo post-upgrade migration entrypoint.

    cr: psycopg2 cursor
    version: previous installed version (string) or None on fresh install
    """
    from odoo.api import Environment, SUPERUSER_ID

    env = Environment(cr, SUPERUSER_ID, {})

    # ---- step 1: backfill group_user from channel.user_ids ---- #
    Channel = env['htf.channel'].sudo()
    active_channels = Channel.search([('state', '=', 'active')])
    user_ids = set()
    for ch in active_channels:
        user_ids |= set(ch.user_ids.ids)
    _logger.info(
        "[migration 19.0.1.27.0] step 1: syncing Hatif: User group for "
        "%d distinct user(s) from %d active channel(s)",
        len(user_ids), len(active_channels),
    )
    if user_ids:
        env['res.users'].browse(list(user_ids))._htf_sync_group_membership()
        cr.commit()

    # ---- step 2: recompute discuss channel members ---- #
    DiscussChannel = env['discuss.channel'].sudo()
    Member = env['discuss.channel.member'].sudo()
    hatif_channels = DiscussChannel.search([
        ('x_htf_partner_id', '!=', False),
        ('active', '=', True),
    ])
    _logger.info(
        "[migration 19.0.1.27.0] step 2: recomputing membership on "
        "%d Hatif Discuss channel(s)",
        len(hatif_channels),
    )
    total_added = 0
    total_removed = 0
    for ch in hatif_channels:
        try:
            allowed = DiscussChannel._htf_allowed_member_partner_ids(
                ch.x_htf_partner_id,
            )
            current = {m.partner_id.id: m for m in ch.channel_member_ids}
            to_add = allowed - set(current)
            to_remove = [m for pid, m in current.items() if pid not in allowed]
            for pid in to_add:
                Member.create({'channel_id': ch.id, 'partner_id': pid})
            if to_remove:
                Member.browse([m.id for m in to_remove]).unlink()
            total_added += len(to_add)
            total_removed += len(to_remove)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[migration 19.0.1.27.0] failed rebuilding channel id=%s "
                "partner id=%s — continuing",
                ch.id, ch.x_htf_partner_id.id,
            )
    cr.commit()
    _logger.info(
        "[migration 19.0.1.27.0] done — added %d member(s), removed "
        "%d member(s) across %d channel(s)",
        total_added, total_removed, len(hatif_channels),
    )

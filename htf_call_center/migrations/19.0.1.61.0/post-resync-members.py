"""Migration 19.0.1.61.0 — re-sync Hatif channel membership.

The access rule changed so that a Sales Manager who leads a DIFFERENT
team no longer sees this customer's chat (only the agent's own team
leader + pure global managers do). Re-sync every Hatif channel so the
now-excluded other-team leaders are dropped.

Idempotent. Channels are already private 'group' (v60), so no type
change is needed here — membership only.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    channels = env['discuss.channel'].sudo().search(
        [('x_htf_partner_id', '!=', False)]
    )
    if not channels:
        return
    channels._htf_sync_channel_members()
    _logger.info(
        "[htf-discuss] v61: re-synced membership on %d Hatif channel(s) "
        "(other-team leaders excluded)", len(channels),
    )

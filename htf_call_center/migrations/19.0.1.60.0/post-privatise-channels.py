"""Migration 19.0.1.60.0 — make Hatif Discuss channels private + re-sync.

Per-customer Hatif channels were created as ``channel_type='channel'``,
which in Odoo is PUBLIC: listed in the Channels directory and joinable
by any internal user. That leaked every customer's chat to every agent
(verified live — agents who never handled a customer had joined the
channel). They must be private ``group`` channels, visible only to the
authorised member set computed by ``_htf_allowed_member_partner_ids``
(the handling agent, their sales-team leader, and Sales Managers).

``channel_type`` cannot be changed through the ORM ("Cannot change the
channel type of: ..."), so flip the existing 'channel' rows to 'group'
with raw SQL, then re-sync membership to drop the agents who joined but
aren't authorised (and add any now-authorised manager/leader).

Idempotent. Safe to re-run.
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

    to_group = channels.filtered(lambda c: c.channel_type != 'group')
    if to_group:
        cr.execute(
            "UPDATE discuss_channel SET channel_type = 'group' "
            "WHERE id IN %s",
            (tuple(to_group.ids),),
        )
        env['discuss.channel'].invalidate_model(['channel_type'])
        _logger.info(
            "[htf-discuss] v60: privatised %d channel(s) to group: %s",
            len(to_group), to_group.ids,
        )

    # Re-sync membership against the v60 access rule (adds managers/leaders,
    # removes agents who joined the formerly-public channel).
    channels._htf_sync_channel_members()
    _logger.info(
        "[htf-discuss] v60: re-synced membership on %d Hatif channel(s)",
        len(channels),
    )

"""channels service — sync htf.channel from Hatif.

`/v1/channels/service-account` returns the per-workspace channel list.
We upsert by `htf_channel_id` and preserve admin overrides (team_id,
display_name, default_for_outbound_*, brand, color, sequence, notes) on
re-sync. Channels that disappear from Hatif are archived locally
(state='archived'), never hard-deleted, so historical references stay
intact.
"""

from __future__ import annotations

import logging

from odoo import fields

from ..exceptions import HtfApiError

_logger = logging.getLogger(__name__)

# Hatif `channelType` is a small int. Map to our Selection.
_CHANNEL_TYPE_MAP = {
    1: 'phone',
    2: 'whatsapp',
    3: 'both',
}

# Fields the channel sync OWNS — anything else admins set is preserved
# across re-sync. Keep this list tight.
_OWNED_FIELDS = {'name', 'htf_channel_id', 'channel_type', 'phone_number',
                 'icon', 'last_synced_at'}


class ChannelService:
    name = 'channels'

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def sync_from_htf(self):
        """Fetch + upsert. Returns the recordset of active channels post-sync."""
        http = self.env['htf.config'].get_service('http')
        payload = http.get('/v1/channels/service-account') or []
        # Some Hatif endpoints wrap in {'items': [...]}; tolerate both.
        if isinstance(payload, dict) and 'items' in payload:
            items = payload['items']
        elif isinstance(payload, list):
            items = payload
        else:
            raise HtfApiError(
                f'Unexpected channels response shape: {type(payload).__name__}',
                body=str(payload)[:300],
            )

        Channel = self.env['htf.channel'].sudo()
        seen_ids = set()
        now = fields.Datetime.now()

        for item in items:
            htf_id = item.get('id') or item.get('channelId')
            if not htf_id:
                _logger.warning("[htf.channels] item missing id, skipping: %s", item)
                continue
            seen_ids.add(htf_id)

            ctype_int = item.get('channelType')
            ctype = _CHANNEL_TYPE_MAP.get(ctype_int, 'whatsapp')

            vals = {
                'name': (item.get('name') or '').strip() or htf_id,
                'htf_channel_id': htf_id,
                'channel_type': ctype,
                'phone_number': (item.get('phoneNumber') or '').strip() or False,
                'icon': item.get('icon') or False,
                'state': 'active',
                'last_synced_at': now,
            }

            existing = Channel.search([('htf_channel_id', '=', htf_id)], limit=1)
            if existing:
                # Preserve admin overrides.
                update = {k: v for k, v in vals.items() if k in _OWNED_FIELDS or k == 'state'}
                existing.write(update)
            else:
                Channel.create(vals)

        # Archive channels we didn't see — they were removed on Hatif side.
        if seen_ids:
            stale = Channel.search([
                ('state', '=', 'active'),
                ('htf_channel_id', 'not in', list(seen_ids)),
            ])
            if stale:
                stale.write({'state': 'archived', 'last_synced_at': now})
                _logger.info("[htf.channels] archived %s removed channels", len(stale))

        active = Channel.search([('state', '=', 'active')])
        _logger.info("[htf.channels] synced %s items, %s active locally",
                     len(items), len(active))
        return active

    def list_active(self, *, channel_type=None):
        domain = [('state', '=', 'active')]
        if channel_type == 'whatsapp':
            domain.append(('channel_type', 'in', ('whatsapp', 'both')))
        elif channel_type == 'phone':
            domain.append(('channel_type', 'in', ('phone', 'both')))
        return self.env['htf.channel'].sudo().search(domain)

    def default_for_outbound_wa(self):
        return self.list_active(channel_type='whatsapp').filtered(
            lambda c: c.default_for_outbound_wa
        )[:1]

    def default_for_outbound_call(self):
        return self.list_active(channel_type='phone').filtered(
            lambda c: c.default_for_outbound_call
        )[:1]

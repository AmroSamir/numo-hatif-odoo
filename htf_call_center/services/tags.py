"""tags service — sync htf.tag from Hatif's `/v1/tags/service-account`.

Tags are mirror-only in P1; no remote mutate from Odoo yet (admins manage
the canonical list on the Hatif portal). CRUD methods exist for future
phases.
"""

from __future__ import annotations

import logging

from odoo import fields

from ..exceptions import HtfApiError

_logger = logging.getLogger(__name__)


class TagService:
    name = 'tags'

    def __init__(self, env):
        self.env = env

    def sync_from_htf(self) -> int:
        http = self.env['htf.config'].get_service('http')
        payload = http.get('/v1/tags/service-account') or []
        if isinstance(payload, dict) and 'items' in payload:
            items = payload['items']
        elif isinstance(payload, list):
            items = payload
        else:
            raise HtfApiError(
                f'Unexpected tags response shape: {type(payload).__name__}',
                body=str(payload)[:300],
            )

        Tag = self.env['htf.tag'].sudo()
        now = fields.Datetime.now()
        seen = 0
        for item in items:
            htf_id = item.get('id') or item.get('tagId')
            if not htf_id:
                continue
            vals = {
                'name': (item.get('name') or '').strip() or htf_id,
                'htf_tag_id': htf_id,
                'icon': item.get('icon') or False,
                'description': item.get('description') or False,
                'is_pinned': bool(item.get('isPinned')),
                'last_synced_at': now,
            }
            created_at_raw = item.get('creationTime') or item.get('createdAt')
            if created_at_raw:
                vals['created_at'] = created_at_raw.replace('T', ' ').split('.')[0]
            existing = Tag.search([('htf_tag_id', '=', htf_id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                Tag.create(vals)
            seen += 1
        _logger.info("[htf.tags] synced %s tags", seen)
        return seen

    def list(self):
        return self.env['htf.tag'].sudo().search([])

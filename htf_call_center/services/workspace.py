"""workspace service — list Hatif workspace users + auto-match to res.users.

`/v1/workspaces/users` returns every user / AI-agent in the active
workspace. `sync_users()` upserts an `htf.user.link` row per entry.
`match_by_email()` is the suggestion engine the Map Users wizard
displays.
"""

from __future__ import annotations

import logging

from odoo import fields

from ..exceptions import HtfApiError

_logger = logging.getLogger(__name__)


class WorkspaceService:
    name = 'workspace'

    def __init__(self, env):
        self.env = env

    def list_users(self) -> list[dict]:
        """Raw Hatif workspace user dicts. Used by the wizard preview."""
        http = self.env['htf.config'].get_service('http')
        payload = http.get('/v1/workspaces/users') or []
        if isinstance(payload, dict) and 'items' in payload:
            return list(payload['items'])
        if isinstance(payload, list):
            return list(payload)
        raise HtfApiError(
            f'Unexpected workspace response shape: {type(payload).__name__}',
            body=str(payload)[:300],
        )

    def sync_users(self):
        items = self.list_users()
        Link = self.env['htf.user.link'].sudo()
        now = fields.Datetime.now()
        for item in items:
            htf_id = item.get('id') or item.get('userId')
            if not htf_id:
                continue
            email = (item.get('email') or '').strip().lower() or False
            display = (item.get('displayName') or item.get('name')
                       or email or htf_id)
            vals = {
                'htf_user_id': htf_id,
                'email': email,
                # `name` (Odoo standard rec-name) — NOT `display_name`,
                # which collides with Odoo's auto-computed field and
                # silently disappears on read.
                'name': display,
                'is_ai_agent': bool(item.get('isAIAgent') or item.get('isAiAgent')),
                'role': self._normalize_role(item.get('role')),
                'last_synced_at': now,
            }
            existing = Link.search([('htf_user_id', '=', htf_id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                Link.create(vals)
        return Link.search([])

    # Hatif's `role` arrives as either a string ('Owner' / 'Member') or an
    # integer enum (observed 1=Owner, 2=Member in some workspaces).
    # Normalize defensively so a future enum value doesn't crash the sync.
    @staticmethod
    def _normalize_role(raw) -> str:
        if isinstance(raw, int) and not isinstance(raw, bool):
            return 'owner' if raw == 1 else 'member'
        if isinstance(raw, str) and raw.strip().lower() == 'owner':
            return 'owner'
        return 'member'

    def match_by_email(self) -> list[tuple]:
        """Suggest (res.users, htf.user.link) pairs by case-insensitive email.

        Skips links that are already mapped and AI-agent rows.
        """
        Link = self.env['htf.user.link'].sudo()
        ResUsers = self.env['res.users'].sudo()
        unmapped = Link.search([
            ('user_id', '=', False),
            ('is_ai_agent', '=', False),
            ('email', '!=', False),
        ])
        suggestions = []
        for link in unmapped:
            user = ResUsers.search([('login', '=ilike', link.email)], limit=1)
            if user:
                suggestions.append((user, link))
        return suggestions

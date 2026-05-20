"""res.users extension fields for Hatif workspace mapping.

Populated by the Map Users wizard (P1.D). Surfaced in the Hatif tab of
the user form (admin-only).
"""

from __future__ import annotations

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    x_htf_user_id = fields.Char(
        string='Hatif User ID',
        index=True,
        copy=False,
        help='Vendor-side UUID for this agent. Set via the Map Users wizard.',
    )
    x_htf_user_email = fields.Char(
        string='Hatif Email (mirror)',
        copy=False,
        help='Denormalized from htf.user.link for fast match.',
    )
    x_htf_role = fields.Selection(
        selection=[('owner', 'Owner'), ('member', 'Member')],
        string='Hatif Role',
        copy=False,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'x_htf_user_id', 'x_htf_user_email', 'x_htf_role',
        ]

    def _htf_sync_group_membership(self):
        """Add/remove ``htf_call_center.group_user`` based on whether
        the user is allowed on at least one active Hatif channel
        (``htf.channel.user_ids``).

        Called from:
          - ``htf.channel`` write/create when ``user_ids`` changes,
          - the Map Users wizard ``action_apply`` after writing channel
            user_ids,
          - the v19.0.1.27.0 migration to backfill the group from
            existing channel allowlists.

        Idempotent. Never removes ``group_admin`` members from
        ``group_user`` (admin implies user, so revoking would break the
        implication chain). Skips inactive / shared users since they
        can't log in anyway.
        """
        if not self:
            return
        group_user = self.env.ref(
            'htf_call_center.group_user', raise_if_not_found=False,
        )
        if not group_user:
            return
        group_admin = self.env.ref(
            'htf_call_center.group_admin', raise_if_not_found=False,
        )
        admin_ids = set(group_admin.user_ids.ids) if group_admin else set()

        Channel = self.env['htf.channel'].sudo()
        users = self.sudo().filtered(lambda u: u.active and not u.share)
        for user in users:
            if user.id in admin_ids:
                # Admin already implies group_user; don't touch.
                continue
            has_channel = bool(Channel.search_count([
                ('user_ids', 'in', user.id),
                ('state', '=', 'active'),
            ]))
            in_group = group_user in user.group_ids
            if has_channel and not in_group:
                user.write({'group_ids': [(4, group_user.id)]})
                _logger.info(
                    "[htf-access] granted Hatif: User to uid=%s login=%s "
                    "(has %s active channel mapping(s))",
                    user.id, user.login,
                    Channel.search_count([
                        ('user_ids', 'in', user.id),
                        ('state', '=', 'active'),
                    ]),
                )
            elif not has_channel and in_group:
                user.write({'group_ids': [(3, group_user.id)]})
                _logger.info(
                    "[htf-access] revoked Hatif: User from uid=%s login=%s "
                    "(no active channel mappings)",
                    user.id, user.login,
                )

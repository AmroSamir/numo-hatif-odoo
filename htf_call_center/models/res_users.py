"""res.users extension fields for Hatif workspace mapping.

Populated by the Map Users wizard (P1.D). Surfaced in the Hatif tab of
the user form (admin-only).
"""

from __future__ import annotations

from odoo import fields, models


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

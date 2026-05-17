"""htf.user.link — mapping between Hatif workspace users and res.users.

Populated by the Map Users wizard (P1.D). Auto-matched by email when
possible, manually overridable. AI agents from Hatif live here too with
`is_ai_agent=True` but no `user_id`.
"""

from __future__ import annotations

from odoo import fields, models


class HtfUserLink(models.Model):
    _name = 'htf.user.link'
    _description = 'HTF Workspace User Link (res.users ↔ Hatif user)'
    # Note: `_order` must use STORED fields. Odoo's auto `display_name` is
    # computed (not SQL-backed); ordering by it raises "Cannot convert ...
    # to SQL because it is not stored". Use email + htf_user_id instead.
    _order = 'is_ai_agent, email, htf_user_id'
    _log_access = True
    _rec_name = 'display_name'

    user_id = fields.Many2one(
        'res.users',
        string='Odoo User',
        ondelete='cascade',
        help='Linked Odoo user. Empty when this row represents a Hatif '
             'AI agent (is_ai_agent=True).',
    )
    htf_user_id = fields.Char(
        string='Hatif User ID',
        required=True,
        index=True,
    )
    email = fields.Char()
    display_name = fields.Char()
    is_ai_agent = fields.Boolean(default=False)
    role = fields.Selection(
        selection=[('owner', 'Owner'), ('member', 'Member')],
        default='member',
    )
    last_synced_at = fields.Datetime()

    _htf_user_id_unique = models.Constraint(
        'unique(htf_user_id)',
        'Hatif user UUID must be unique.',
    )

"""htf.tag — labels mirrored from Hatif's tag registry.

Used by P6 conversations and P7 lead enrichment for cross-channel reporting
("VIP", "Cold", "Hot", "Cambridge", "NH" etc.). Synced via
`services/tags.py` from Hatif's `/v1/tags/service-account`.
"""

from __future__ import annotations

from odoo import fields, models


class HtfTag(models.Model):
    _name = 'htf.tag'
    _description = 'HTF Tag (mirror of Hatif tag)'
    _order = 'is_pinned desc, sequence, name'
    _log_access = True

    name = fields.Char(required=True, index=True)
    htf_tag_id = fields.Char(
        string='Hatif Tag ID',
        required=True,
        index=True,
        help='Vendor-side UUID.',
    )
    icon = fields.Char()
    description = fields.Text()
    is_pinned = fields.Boolean(string='Pinned', default=False)
    color = fields.Integer(string='Kanban Color', default=0)
    sequence = fields.Integer(default=10)
    created_at = fields.Datetime(string='Created on Hatif at')
    last_synced_at = fields.Datetime()

    _htf_tag_id_unique = models.Constraint(
        'unique(htf_tag_id)',
        'Hatif tag UUID must be unique.',
    )

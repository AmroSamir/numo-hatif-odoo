"""htf.contact.link — mapping between res.partner and Hatif contacts.

One partner ↔ one Hatif contact (unique on partner_id). Created by
`services/contacts.upsert_from_partner()` or by inbound webhooks that
encounter an unknown contactId.
"""

from __future__ import annotations

from odoo import fields, models


class HtfContactLink(models.Model):
    _name = 'htf.contact.link'
    _description = 'HTF Contact Link (res.partner ↔ Hatif contact)'
    _order = 'last_synced_at desc'
    _log_access = True

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
        index=True,
    )
    htf_contact_id = fields.Char(
        string='Hatif Contact ID',
        required=True,
        index=True,
    )
    last_synced_at = fields.Datetime()
    sync_state = fields.Selection(
        selection=[
            ('synced', 'Synced'),
            ('pending', 'Pending'),
            ('error', 'Error'),
        ],
        default='synced',
    )
    sync_error = fields.Char(help='Last error message when sync_state=error.')
    custom_properties_json = fields.Text(
        string='Custom Properties (JSON)',
        help='Snapshot of vendor custom properties for fast display.',
    )

    _partner_id_unique = models.Constraint(
        'unique(partner_id)',
        'A partner can be linked to at most one Hatif contact.',
    )
    _htf_contact_id_unique = models.Constraint(
        'unique(htf_contact_id)',
        'A Hatif contact ID can map to at most one partner.',
    )

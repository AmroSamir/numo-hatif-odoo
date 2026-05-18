"""res.partner extension fields for Hatif integration.

Custom-field prefix `x_htf_*` is locked per 00_OVERVIEW.md §5.
24h Meta-window computation lives here so any view / service can read it
without re-implementing the date math.
"""

from __future__ import annotations

from datetime import timedelta

from odoo import api, fields, models

from ..constants import META_24H_WINDOW_HOURS


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_htf_contact_id = fields.Char(
        string='Hatif Contact ID',
        index=True,
        copy=False,
        help='Denormalized from htf.contact.link for fast filter / display.',
    )
    x_htf_synced_at = fields.Datetime(string='Hatif Last Synced At', copy=False)
    x_htf_last_inbound_at = fields.Datetime(
        string='Last Inbound at',
        copy=False,
        help='Most recent inbound WA message / call timestamp. Used to '
             'compute the 24h Meta window.',
    )
    x_htf_24h_window_open = fields.Boolean(
        string='24h Window Open',
        compute='_compute_x_htf_24h_window_open',
        help='True when last inbound is within the META 24h window.',
    )
    x_htf_opted_out = fields.Boolean(
        string='Opted Out (DNC)',
        default=False,
        copy=False,
        help='Mirrors an active htf.dnc row for this number. Outbound '
             'sends are blocked while True.',
    )
    x_htf_default_channel_id = fields.Many2one(
        'htf.channel',
        string='Preferred Hatif Channel',
        domain="[('state', '=', 'active')]",
        help='Per-partner override in the outbound channel resolution '
             'chain (Lead.team → Partner.team → THIS → User.team → fallback).',
    )
    # Smart-button counters — computed on the fly from related htf.call /
    # htf.message rows. Cheap because both tables have partner_id indexed.
    x_htf_call_count = fields.Integer(
        string='Calls',
        compute='_compute_x_htf_call_count',
        copy=False,
    )
    x_htf_message_count = fields.Integer(
        string='WhatsApp Messages',
        compute='_compute_x_htf_message_count',
        copy=False,
    )

    @api.depends('x_htf_last_inbound_at')
    def _compute_x_htf_24h_window_open(self):
        cutoff = fields.Datetime.now() - timedelta(hours=META_24H_WINDOW_HOURS)
        for rec in self:
            rec.x_htf_24h_window_open = bool(
                rec.x_htf_last_inbound_at and rec.x_htf_last_inbound_at >= cutoff
            )

    def _compute_x_htf_call_count(self):
        if not self.ids:
            for rec in self:
                rec.x_htf_call_count = 0
            return
        Call = self.env['htf.call'].sudo()
        groups = Call._read_group(
            [('partner_id', 'in', self.ids)],
            groupby=['partner_id'],
            aggregates=['__count'],
        )
        counts = {p.id: c for p, c in groups}
        for rec in self:
            rec.x_htf_call_count = counts.get(rec.id, 0)

    def _compute_x_htf_message_count(self):
        if not self.ids:
            for rec in self:
                rec.x_htf_message_count = 0
            return
        Msg = self.env['htf.message'].sudo()
        groups = Msg._read_group(
            [('partner_id', 'in', self.ids)],
            groupby=['partner_id'],
            aggregates=['__count'],
        )
        counts = {p.id: c for p, c in groups}
        for rec in self:
            rec.x_htf_message_count = counts.get(rec.id, 0)

    def action_view_htf_calls(self):
        """Open the htf.call list filtered to this partner."""
        self.ensure_one()
        action = self.env.ref('htf_call_center.htf_call_action').read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

    def action_view_htf_messages(self):
        """Open the htf.message list filtered to this partner."""
        self.ensure_one()
        action = self.env.ref('htf_call_center.htf_message_action').read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

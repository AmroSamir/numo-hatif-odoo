"""Bind Channels wizard — batch edit channel ↔ team assignments.

One screen, one save. Used after a fresh channel sync to assign Hatif
channels to Numo sales teams without opening each channel record.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtfBindChannelsWizard(models.TransientModel):
    _name = 'htf.bind.channels.wizard'
    _description = 'Bind Hatif Channels to Sales Teams'

    line_ids = fields.One2many(
        'htf.bind.channels.wizard.line',
        'wizard_id',
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        Channel = self.env['htf.channel']
        lines = []
        for ch in Channel.search([('state', '=', 'active')], order='sequence, display_name'):
            lines.append((0, 0, {
                'channel_id': ch.id,
                'team_id': ch.team_id.id if ch.team_id else False,
                'default_for_outbound_wa': ch.default_for_outbound_wa,
                'default_for_outbound_call': ch.default_for_outbound_call,
            }))
        vals['line_ids'] = lines
        return vals

    def action_apply(self):
        self.ensure_one()
        for line in self.line_ids:
            line.channel_id.write({
                'team_id': line.team_id.id if line.team_id else False,
                'default_for_outbound_wa': line.default_for_outbound_wa,
                'default_for_outbound_call': line.default_for_outbound_call,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Bindings saved'),
                'message': _('%s channels updated.') % len(self.line_ids),
                'sticky': False,
            },
        }


class HtfBindChannelsWizardLine(models.TransientModel):
    _name = 'htf.bind.channels.wizard.line'
    _description = 'Bind Hatif Channels — line'
    _order = 'channel_id'

    wizard_id = fields.Many2one('htf.bind.channels.wizard', required=True, ondelete='cascade')
    channel_id = fields.Many2one('htf.channel', string='Channel (ref)', required=True, readonly=True)
    channel_display = fields.Char(related='channel_id.display_name', string='Channel')
    channel_type = fields.Selection(related='channel_id.channel_type')
    phone_number = fields.Char(related='channel_id.phone_number')
    team_id = fields.Many2one('crm.team', string='Sales Team')
    default_for_outbound_wa = fields.Boolean(string='Default WA')
    default_for_outbound_call = fields.Boolean(string='Default Call')

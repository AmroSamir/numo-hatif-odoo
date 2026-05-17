"""htf.channel — a Hatif channel (a number / a WhatsApp line / both).

Per the locked design (00_OVERVIEW.md §8):

- Channel ↔ Team binding is 1:N (multi-channel-per-team allowed).
- Each team picks at most one default outbound WA channel and one default
  outbound call channel; everything else is available via dropdown override
  on the per-record forms.
- Outbound channel resolution chain (consumed by P3 channel resolver):
  Lead.team → Partner.team → Partner override → User.team → Workspace fallback.
- Inbound routing: channel.team owns; route by team's strategy.

This module owns the model. P1.C `services/channels.py` syncs it from
Hatif via `/v1/channels/service-account`.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class HtfChannel(models.Model):
    _name = 'htf.channel'
    _description = 'HTF Channel (Hatif number / WhatsApp line)'
    _order = 'sequence, display_name, name'
    _log_access = True

    name = fields.Char(
        string='Hatif Name',
        required=True,
        help='Channel name as reported by Hatif (e.g. "Numo Academy Sales").',
    )
    display_name = fields.Char(
        string='Display Name',
        help='Admin-editable friendly label shown in dropdowns + chatter '
             '(e.g. "Cambridge Sales", "Numo Academy KSA"). Falls back to '
             'the Hatif `name` when empty.',
        compute='_compute_display_name',
        store=True,
        readonly=False,
    )
    htf_channel_id = fields.Char(
        string='Hatif Channel ID',
        required=True,
        index=True,
        help='Vendor-side UUID for this channel.',
    )
    channel_type = fields.Selection(
        selection=[
            ('phone', 'Phone'),
            ('whatsapp', 'WhatsApp'),
            ('both', 'Phone + WhatsApp'),
        ],
        required=True,
        default='whatsapp',
    )
    phone_number = fields.Char(
        size=20,
        help='E.164-normalized inbound number (e.g. +966115001591).',
    )
    icon = fields.Char()
    team_id = fields.Many2one(
        'crm.team',
        string='Sales Team',
        ondelete='set null',
        help='Sales team that owns this channel. Drives inbound routing '
             'and the outbound channel resolution chain. Reassignable via '
             'the Bind Channels wizard without code changes.',
    )
    user_ids = fields.Many2many(
        'res.users',
        string='Allowed Agents (override)',
        help='Optional override. If empty, team members are the default '
             'pool of agents permitted to send via this channel.',
    )
    default_for_outbound_wa = fields.Boolean(
        string='Default for Outbound WhatsApp',
        default=False,
        help='Per-team default. The channel resolver picks this when no '
             'per-partner / per-record override is set.',
    )
    default_for_outbound_call = fields.Boolean(
        string='Default for Outbound Calls',
        default=False,
        help='Per-team default. Used by the phone-widget deep link picker.',
    )
    brand = fields.Char(
        help='Optional brand label (Cambridge / NH / Numo Academy) for '
             'reporting cross-cuts; not used by routing.',
    )
    color = fields.Integer(string='Kanban Color', default=0)
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('archived', 'Archived'),
        ],
        default='active',
        index=True,
    )
    last_synced_at = fields.Datetime(string='Last Synced At')
    notes = fields.Text(
        help='Admin notes (e.g. "Cambridge KSA inbound only").',
    )

    _htf_channel_id_unique = models.Constraint(
        'unique(htf_channel_id)',
        'Hatif channel UUID must be unique.',
    )

    @api.depends('name', 'display_name')
    def _compute_display_name(self):
        for rec in self:
            if rec.display_name:
                continue
            rec.display_name = rec.name

    @api.constrains('default_for_outbound_wa', 'team_id', 'state')
    def _check_one_default_wa_per_team(self):
        # Each team has at most one default-WA channel (among active ones).
        for rec in self:
            if not rec.default_for_outbound_wa or rec.state != 'active' or not rec.team_id:
                continue
            others = self.search([
                ('id', '!=', rec.id),
                ('team_id', '=', rec.team_id.id),
                ('default_for_outbound_wa', '=', True),
                ('state', '=', 'active'),
            ], limit=1)
            if others:
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'Team %(team)s already has a default outbound WhatsApp '
                    'channel (%(other)s). Unset the previous default first.'
                ) % {
                    'team': rec.team_id.name,
                    'other': others.display_name or others.name,
                })

    @api.constrains('default_for_outbound_call', 'team_id', 'state')
    def _check_one_default_call_per_team(self):
        for rec in self:
            if not rec.default_for_outbound_call or rec.state != 'active' or not rec.team_id:
                continue
            others = self.search([
                ('id', '!=', rec.id),
                ('team_id', '=', rec.team_id.id),
                ('default_for_outbound_call', '=', True),
                ('state', '=', 'active'),
            ], limit=1)
            if others:
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'Team %(team)s already has a default outbound Call '
                    'channel (%(other)s). Unset the previous default first.'
                ) % {
                    'team': rec.team_id.name,
                    'other': others.display_name or others.name,
                })

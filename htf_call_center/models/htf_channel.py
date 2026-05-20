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

    # ------------------------------------------------------------------ #
    # 2-gate access — react to user_ids / team_id changes                #
    # ------------------------------------------------------------------ #
    # Channel membership for the per-partner Hatif Discuss channels is
    # derived from htf.channel.user_ids (the channel-gate) ∩
    # crm.lead.user_id (the lead-gate). So any change to user_ids must:
    #   1. Resync Hatif: User group for users added/removed (so they can
    #      open the Send WhatsApp wizard).
    #   2. Recompute membership on every Hatif Discuss channel whose
    #      customer has a lead on this channel's team (the agents
    #      that just gained/lost channel access need to be added/
    #      removed from the right discuss.channels).
    # team_id changes also affect the membership map for the same reason.

    def write(self, vals):
        affects_access = any(k in vals for k in ('user_ids', 'team_id', 'state'))
        old_user_ids = (
            {ch.id: set(ch.user_ids.ids) for ch in self}
            if affects_access else {}
        )
        old_team_ids = (
            {ch.id: ch.team_id.id for ch in self}
            if affects_access else {}
        )
        res = super().write(vals)
        if affects_access:
            self._htf_propagate_access_change(old_user_ids, old_team_ids)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # New channels with user_ids prefilled need group + membership
        # sync too. team_id may also be unset on create — fine, gate
        # is permissive when team is absent.
        records._htf_propagate_access_change(
            old_user_ids={ch.id: set() for ch in records},
            old_team_ids={ch.id: False for ch in records},
        )
        return records

    def _htf_propagate_access_change(self, old_user_ids, old_team_ids):
        """Resync Hatif: User group + Discuss channel membership for
        users whose channel-access just changed.

        Called from write/create whenever ``user_ids`` / ``team_id`` /
        ``state`` change. Wrapped so callers don't have to know the
        bookkeeping. Best-effort — exceptions are logged not raised
        (don't break a channel save because of a downstream sync hiccup).
        """
        affected_uids = set()
        affected_teams = set()
        for ch in self:
            new_uids = set(ch.user_ids.ids)
            old_uids = old_user_ids.get(ch.id, set())
            affected_uids |= (new_uids ^ old_uids)
            # If team_id changed, both teams' membership maps could
            # shift for this channel's allowed agents.
            new_team = ch.team_id.id if ch.team_id else False
            old_team = old_team_ids.get(ch.id, False)
            if new_team != old_team:
                affected_uids |= new_uids
                if old_team:
                    affected_teams.add(old_team)
                if new_team:
                    affected_teams.add(new_team)
            else:
                if ch.team_id:
                    affected_teams.add(ch.team_id.id)

        if affected_uids:
            try:
                self.env['res.users'].browse(list(affected_uids))._htf_sync_group_membership()
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-access] group resync failed for users=%s after "
                    "channel allow-list change",
                    sorted(affected_uids),
                )

        # Resync Discuss channel membership for every customer who has
        # a lead on an affected team. Scope by team to keep the work
        # bounded — a channel access change can't affect customers on
        # other teams.
        if not affected_teams:
            return
        DiscussChannel = self.env['discuss.channel'].sudo()
        Lead = self.env['crm.lead'].sudo()
        leads = Lead.search([
            ('team_id', 'in', list(affected_teams)),
            ('partner_id', '!=', False),
        ])
        partner_ids = {l.partner_id.id for l in leads}
        if not partner_ids:
            return
        discuss_channels = DiscussChannel.search([
            ('x_htf_partner_id', 'in', list(partner_ids)),
            ('active', '=', True),
        ])
        for ch in discuss_channels:
            try:
                ch._htf_sync_channel_members()
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-access] discuss channel resync failed for "
                    "channel id=%s partner id=%s",
                    ch.id, ch.x_htf_partner_id.id,
                )

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

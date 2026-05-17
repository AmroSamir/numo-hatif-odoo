"""crm.team extension — Hatif Channels tab + computed defaults + routing.

A team owns N channels (One2many via htf.channel.team_id). Two computed
fields expose the per-team default outbound channels (WhatsApp and Call)
so the resolver (P3) and the phone widget (P3) don't have to re-search.

Routing strategy is consulted by P4 call dispatcher when a fresh inbound
needs an agent assignment.
"""

from __future__ import annotations

from odoo import api, fields, models


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    x_htf_channel_ids = fields.One2many(
        'htf.channel',
        'team_id',
        string='Hatif Channels',
    )
    x_htf_default_outbound_wa_channel_id = fields.Many2one(
        'htf.channel',
        string='Default Outbound WhatsApp Channel',
        compute='_compute_x_htf_default_outbound_channels',
    )
    x_htf_default_outbound_call_channel_id = fields.Many2one(
        'htf.channel',
        string='Default Outbound Call Channel',
        compute='_compute_x_htf_default_outbound_channels',
    )
    x_htf_routing_strategy = fields.Selection(
        selection=[
            ('lead_owner', 'Owner of matching lead (fallback round-robin)'),
            ('round_robin', 'Round robin'),
            ('least_busy', 'Least busy'),
            ('manual', 'Manual'),
        ],
        string='Inbound Routing Strategy',
        default='lead_owner',
        help='How to pick the agent when a fresh inbound on this team\'s '
             'channel has no existing lead owner.',
    )

    @api.depends(
        'x_htf_channel_ids.default_for_outbound_wa',
        'x_htf_channel_ids.default_for_outbound_call',
        'x_htf_channel_ids.state',
    )
    def _compute_x_htf_default_outbound_channels(self):
        for team in self:
            actives = team.x_htf_channel_ids.filtered(lambda c: c.state == 'active')
            team.x_htf_default_outbound_wa_channel_id = next(
                (c for c in actives if c.default_for_outbound_wa), False,
            )
            team.x_htf_default_outbound_call_channel_id = next(
                (c for c in actives if c.default_for_outbound_call), False,
            )

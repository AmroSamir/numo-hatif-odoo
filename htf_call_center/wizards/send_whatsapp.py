"""Send WhatsApp wizard (P3 T3.5).

Transient model that wraps the public ``services/whatsapp`` API in a
friendly form. Two modes:

- **Text** — free-form text inside the 24h Meta window
- **Template** — pre-approved Hatif template anytime

The wizard performs a pre-flight check (DNC, window, channel resolution)
before opening, surfacing problems as a banner instead of a 500 on
submit.
"""

from __future__ import annotations

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..exceptions import (
    HtfApiError, HtfChannelNotFoundError, HtfDncBlockedError,
    HtfWindowExpiredError,
)
from ..services import channel_resolver, whatsapp

_logger = logging.getLogger(__name__)


class HtfSendWhatsappWizard(models.TransientModel):
    _name = 'htf.send.whatsapp.wizard'
    _description = 'Send WhatsApp Wizard'

    # Target ---------------------------------------------------------- #
    partner_id = fields.Many2one('res.partner', required=True)
    lead_id = fields.Many2one(
        'crm.lead',
        help='Optional CRM lead this WA is associated with. Populates '
             'automatically when the wizard is opened from a lead form. '
             'Drives the channel resolver via lead.team_id.',
    )
    to_number = fields.Char(
        required=True,
        help='E.164 number to send to. Pre-filled from partner.phone, '
             'editable for one-off sends to alternates (e.g. WA-only '
             'numbers).',
    )

    # Channel --------------------------------------------------------- #
    channel_id = fields.Many2one(
        'htf.channel',
        domain="[('state','=','active'), ('channel_type','in',('whatsapp','both'))]",
        help='Outbound channel. Resolved automatically per the team-chain '
             'when blank — admin override here only if needed.',
    )

    # Mode + content -------------------------------------------------- #
    mode = fields.Selection(
        selection=[
            ('text', 'Free-form text (24h window required)'),
            ('template', 'Template (any time)'),
        ],
        default='text',
        required=True,
    )
    text = fields.Text(
        string='Message',
        help='Free-form WA text body — sent only when 24h window is open.',
    )

    template_name = fields.Char(
        help='Exact Hatif-approved template name (case-sensitive). '
             'Templates live on the Hatif portal per Q-13.',
    )
    template_language = fields.Char(
        default='ar',
        help='ISO language code (e.g. ar, en, ar_SA) matching the '
             'approved template on Hatif.',
    )
    template_parameters_json = fields.Text(
        string='Parameters (JSON)',
        help='Full Parameters array per Hatif sendTemplate spec. '
             'Helper buttons below build common shapes.',
    )
    template_body_params = fields.Char(
        string='Body Variables',
        help='Pipe-separated body values, e.g. "Ahmed|ORD-5123|confirmed". '
             'If set + Parameters JSON is empty, the wizard auto-builds '
             'a Body parameter block.',
    )
    template_category = fields.Selection(
        selection=[
            ('marketing', 'Marketing'),
            ('utility', 'Utility'),
            ('authentication', 'Authentication'),
            ('service', 'Service'),
        ],
        default='utility',
    )

    # Pre-flight (computed, readonly) --------------------------------- #
    dnc_blocked = fields.Boolean(compute='_compute_preflight', store=False)
    window_open = fields.Boolean(compute='_compute_preflight', store=False)
    resolved_channel_display = fields.Char(
        compute='_compute_preflight', store=False, string='Resolved Channel',
    )
    preflight_error = fields.Char(compute='_compute_preflight', store=False)

    # ---------------------------------------------------------------- #
    # Defaults + computes                                              #
    # ---------------------------------------------------------------- #

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        partner = None
        lead = None
        if active_model == 'res.partner' and active_id:
            partner = self.env['res.partner'].browse(active_id)
        elif active_model == 'crm.lead' and active_id:
            lead = self.env['crm.lead'].browse(active_id)
            # A lead may have no linked partner yet (early-stage). Fall
            # back to a lead-level phone if the partner_id is not set.
            if lead.partner_id:
                partner = lead.partner_id
        if partner:
            vals['partner_id'] = partner.id
            vals['to_number'] = partner.phone or ''
        if lead:
            vals['lead_id'] = lead.id
            # Prefer the lead's phone — agents update the lead form, not
            # always the partner directly.
            vals['to_number'] = (
                lead.phone or lead.mobile or vals.get('to_number') or ''
            )
        return vals

    @api.depends('partner_id', 'lead_id', 'channel_id', 'mode')
    def _compute_preflight(self):
        for w in self:
            w.dnc_blocked = bool(w.partner_id and w.partner_id.x_htf_opted_out)
            w.window_open = bool(w.partner_id and w.partner_id.x_htf_24h_window_open)
            error = ''
            channel = w.channel_id
            if not channel:
                try:
                    channel = channel_resolver.resolve_outbound_wa(
                        w.env, partner=w.partner_id, lead=w.lead_id,
                        sender_user=w.env.user,
                    )
                except HtfChannelNotFoundError as exc:
                    error = exc.message or str(exc)
            w.resolved_channel_display = (
                f'{channel.display_name or channel.name} ({channel.phone_number or "—"})'
                if channel else _('— not resolved —')
            )
            if w.dnc_blocked:
                error = _('Customer is on DNC list. Send blocked.')
            elif w.mode == 'text' and w.partner_id and not w.window_open:
                error = _('24h window is closed — switch to Template mode.')
            w.preflight_error = error

    # ---------------------------------------------------------------- #
    # Submit                                                           #
    # ---------------------------------------------------------------- #

    def action_send(self):
        self.ensure_one()
        if self.preflight_error:
            raise UserError(self.preflight_error)
        try:
            if self.mode == 'text':
                msg = whatsapp.send_text(
                    self.env,
                    to_number=self.to_number,
                    text=self.text or '',
                    partner=self.partner_id,
                    lead=self.lead_id or None,
                    channel=self.channel_id or None,
                    sender_user=self.env.user,
                    category='service',
                )
            else:
                params = self._compute_template_parameters()
                msg = whatsapp.send_template(
                    self.env,
                    template_name=self.template_name,
                    language=self.template_language,
                    to_number=self.to_number,
                    parameters=params,
                    partner=self.partner_id,
                    lead=self.lead_id or None,
                    channel=self.channel_id or None,
                    sender_user=self.env.user,
                    category=self.template_category,
                )
        except HtfDncBlockedError as exc:
            raise UserError(exc.message or _('DNC blocked'))
        except HtfWindowExpiredError as exc:
            raise UserError(exc.message or _('Window expired'))
        except HtfChannelNotFoundError as exc:
            raise UserError(exc.message or _('Channel not found'))
        except HtfApiError as exc:
            raise UserError(exc.message or _('Send failed: %s') % exc.__class__.__name__)

        # Open the related htf.message form so the agent can see status.
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htf.message',
            'res_id': msg.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _compute_template_parameters(self) -> list[dict]:
        if self.template_parameters_json:
            try:
                parsed = json.loads(self.template_parameters_json)
                if isinstance(parsed, list):
                    return parsed
                raise UserError(_('Parameters JSON must be a list.'))
            except (TypeError, ValueError) as exc:
                raise UserError(_('Invalid Parameters JSON: %s') % exc)
        if self.template_body_params:
            values = [v.strip() for v in self.template_body_params.split('|') if v.strip()]
            return [whatsapp.build_body_parameter(*values)]
        return []

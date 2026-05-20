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
from ..services import channel_resolver, conversations, whatsapp

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

    template_id = fields.Many2one(
        'htf.template',
        string='Template',
        help='Pick from approved templates registered locally. Filtered '
             'by the selected channel (or the user\'s allowed channels '
             'when no channel is set yet). Selecting one auto-fills the '
             'name, language and category fields below. Leave empty to '
             'type a name manually (for templates not yet registered).',
    )
    template_name = fields.Char(
        help='Exact Hatif-approved template name (CASE-SENSITIVE). '
             'Auto-filled from the Template dropdown above when available. '
             'See app.hatif.io → Settings → Message Templates for the '
             'list of approved names + their status (only Active templates '
             'will send). Common rejection causes if Hatif returns 400:\n'
             '  • Name typo or wrong case (e.g. "Utility" vs "utility")\n'
             '  • Language mismatch (e.g. "ar" sent but template is "ar_SA")\n'
             '  • Template under review / pending approval (status must be Active)\n'
             '  • Missing required body / header parameters for that template\n'
             '  • Wrong channel — template approved on a different ChannelId',
    )
    template_language = fields.Char(
        default='ar',
        help='ISO language code (e.g. ar, en, ar_SA) — MUST match the '
             'language tag on the approved Hatif template exactly. '
             'When Hatif rejects with 400 on a name that looks correct, '
             'this is the second most-common cause.',
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

        # Pre-resolve the outbound channel so the wizard opens with
        # ``channel_id`` already filled. This collapses the previous
        # two-field UX ("Channel" picker + "Resolved Channel" read-only
        # display) into a single editable field showing the channel the
        # send will actually go through — agents can still override it
        # via the dropdown when needed, but they don't see two labels
        # for the same concept anymore.
        if not vals.get('channel_id'):
            try:
                resolved = channel_resolver.resolve_outbound_wa(
                    self.env,
                    partner=partner,
                    lead=lead,
                    sender_user=self.env.user,
                )
            except HtfChannelNotFoundError:
                resolved = None
            if resolved:
                vals['channel_id'] = resolved.id

        # Refresh Meta's 24h customer-service-window status directly
        # from Hatif's conversation timeline so the wizard's free-form
        # gate reflects RIGHT NOW, not the last time a webhook happened
        # to update the partner. Webhooks can lag / fail; this puts the
        # wizard back in sync without an admin having to dig through
        # the partner form. Best-effort — Hatif outages keep the
        # locally-cached flag.
        if partner:
            try:
                conversations.refresh_window_from_hatif(self.env, partner)
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-window] wizard pre-check failed for partner=%s "
                    "— falling back to local x_htf_24h_window_open=%s",
                    partner.id, partner.x_htf_24h_window_open,
                )
        return vals

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Copy the picked template's metadata onto the legacy free-form
        fields so ``action_send`` keeps its existing code path: it still
        reads ``template_name`` / ``template_language`` / ``template_category``
        and posts those to Hatif. The Many2one is purely a UI convenience.

        Also auto-snaps ``channel_id`` to the template's channel when the
        wizard's channel is empty, so the agent doesn't have to set both.

        Body variables are intentionally NOT auto-filled from the
        template's ``parameter_hint`` — that hint is an EXAMPLE of what
        values look like (``Ahmed|ORD-5123|confirmed``), not real data.
        Pre-filling it would mean an agent who clicks Send without
        editing actually transmits the placeholder values to the
        customer. The hint surfaces as the field's placeholder text
        instead (set in the view) so the example shape is still
        visible without being submitted by accident.
        """
        for w in self:
            tpl = w.template_id
            if not tpl:
                continue
            w.template_name = tpl.name
            if tpl.language:
                w.template_language = tpl.language
            if tpl.category:
                w.template_category = tpl.category
            if not w.channel_id:
                w.channel_id = tpl.channel_id

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
                # Locked wording mirrors Hatif's portal notice for the
                # closed 24h window. English source — Arabic translation
                # provided by htf_call_center/i18n/ar.po so the Arabic
                # locale sees the same wording in Arabic.
                error = _(
                    'Template message required\n\n'
                    'To start or resume a conversation, you must send '
                    'an approved Meta template message. Once the customer '
                    'replies, you can message freely for 24 hours.'
                )
            w.preflight_error = error

    # ---------------------------------------------------------------- #
    # Submit                                                           #
    # ---------------------------------------------------------------- #

    def action_send(self):
        self.ensure_one()
        if self.preflight_error:
            raise UserError(self.preflight_error)
        if self.mode == 'template':
            self._validate_template_param_count()
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

    def _validate_template_param_count(self):
        """Refuse to send when the body-variables count doesn't match
        the registered template's ``parameter_count``.

        Meta returns ``(#132000) Number of parameters does not match the
        expected number of params`` as a 400 when this mismatches.
        Catching it locally with a UserError is much better UX than
        round-tripping to Hatif, storing a Failed htf.message row, and
        making the agent open the error to figure out what went wrong.

        Only enforced when the agent picked from the ``template_id``
        dropdown (so we KNOW the expected count). For free-form
        ``template_name`` (template not registered in htf.template)
        we can't validate — that path falls through to Hatif as before.

        ``template_parameters_json`` is treated as an advanced override;
        when it's set the agent has taken full control of the body
        shape, so we skip the count check.
        """
        if not self.template_id:
            return
        if self.template_parameters_json and self.template_parameters_json.strip():
            return
        expected = self.template_id.parameter_count or 0
        raw = (self.template_body_params or '').strip()
        provided = [v.strip() for v in raw.split('|') if v.strip()] if raw else []
        if len(provided) != expected:
            raise UserError(_(
                'This template expects %(expected)s body variable(s) but '
                'you provided %(provided)s.\n\n'
                'Template "%(tpl)s" body shape is set by Hatif/Meta — '
                'count the {{1}}, {{2}}, … placeholders in the approved '
                'template body and fill the "Body Variables" field with '
                'exactly that many pipe-separated values (e.g. '
                '"value1|value2"). Leave the field empty if the template '
                'has no body variables.'
            ) % {
                'expected': expected,
                'provided': len(provided),
                'tpl': self.template_id.name,
            })

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

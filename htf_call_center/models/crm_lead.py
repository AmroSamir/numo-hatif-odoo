"""crm.lead extension — mirror partner-level Hatif fields onto the lead.

Why this exists: the ``htf_phone`` widget on the lead form needs to
deep-link the Call button to the partner's Hatif conversation —
``https://app.hatif.io/ar/inbox?conversationId=<uuid>`` — same as the
Discuss ChatWindow header action. The widget reads
``record.data.x_htf_last_conversation_id`` from the form's loaded
record, but ``x_htf_last_conversation_id`` lives on ``res.partner``
not on ``crm.lead`` — so on a lead form the field is missing from
``record.data`` and the widget silently falls back to the inbox base
URL (no deep-link).

Adding ``related='partner_id.x_htf_last_conversation_id'`` here gives
the lead a read-only proxy field with the same name, which we then
declare ``invisible="1"`` on the lead form (``crm_lead_views.xml``) so
the OWL data loader pulls it into ``record.data`` and the widget can
build the deep-link.

No DB column (``store=False``) — the value lives on the partner row,
this is purely a read-through for the frontend.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    x_htf_last_conversation_id = fields.Char(
        related='partner_id.x_htf_last_conversation_id',
        readonly=True,
        store=False,
        string='Last Hatif conversationId (via partner)',
        help='Read-through to the linked partner\'s most recent Hatif '
             'conversation ID. Powers the lead-form phone widget Call '
             'button deep-link into the Hatif portal.',
    )
    x_htf_last_channel_uuid = fields.Char(
        related='partner_id.x_htf_last_channel_uuid',
        readonly=True,
        store=False,
        string='Last Hatif channelId (via partner)',
        help='Read-through to the linked partner\'s most recent Hatif '
             'workspace channel UUID. Combined with conversationId + '
             'phone by the deep-link builder.',
    )

    # ------------------------------------------------------------------ #
    # Read-only "Conversation" tab (v19.0.1.62.0)                         #
    # ------------------------------------------------------------------ #
    # Renders the customer's WhatsApp + call timeline from htf.message /
    # htf.call directly (NOT a chatter mirror — no third copy). View-only
    # by construction: there is no composer, agents reply via the existing
    # "Send WhatsApp" button. Gated by the SAME privacy as the Discuss
    # chat — the viewer must be a member of the customer's private Hatif
    # channel — so a manager who can see the lead but was excluded from
    # the channel (e.g. another team's leader) does NOT see the
    # conversation here either.

    x_htf_can_view_conversation = fields.Boolean(
        compute='_compute_htf_conversation',
        store=False,
        help='True when the current user may see this customer\'s Hatif '
             'conversation (i.e. is a member of the private chat channel). '
             'Drives visibility of the Conversation tab.',
    )
    x_htf_conversation_html = fields.Html(
        string='Hatif Conversation',
        compute='_compute_htf_conversation',
        store=False,
        sanitize=False,  # we generate + escape the markup ourselves
        help='Read-only WhatsApp + call timeline rendered from '
             'htf.message / htf.call for the linked partner.',
    )

    @api.depends('partner_id')
    def _compute_htf_conversation(self):
        Channel = self.env['discuss.channel'].sudo()
        viewer = self.env.user.partner_id
        for lead in self:
            partner = lead.partner_id
            if not partner:
                lead.x_htf_can_view_conversation = False
                lead.x_htf_conversation_html = False
                continue
            channel = Channel.search([
                ('x_htf_partner_id', '=', partner.id),
                ('active', '=', True),
            ], limit=1)
            member_pids = (
                channel.channel_member_ids.partner_id.ids if channel else []
            )
            allowed = bool(self.env.su or (viewer and viewer.id in member_pids))
            lead.x_htf_can_view_conversation = allowed
            lead.x_htf_conversation_html = (
                lead._htf_render_conversation_html(partner) if allowed else False
            )

    def _htf_render_conversation_html(self, partner):
        """Build the read-only WA + call timeline HTML for ``partner``.

        Reuses the Discuss bubble renderers so the content (template
        previews, call summary + verb, local times) matches the chat. A
        scoped <style> block with ``!important`` resets neutralises the
        margins Odoo's html editor injects on rendered blocks (which
        otherwise blow the bubble spacing wide open). Call bubbles embed
        the recording as an <audio> player when one is attached. Safe with
        ``sanitize=False`` — every customer string is escaped.
        """
        from html import escape

        from markupsafe import Markup

        from ..services import discuss_mirror

        render_env = discuss_mirror._with_bubble_lang(self.env)
        Msg = self.env['htf.message'].sudo()
        Call = self.env['htf.call'].sudo()
        msgs = Msg.search([('partner_id', '=', partner.id)], order='id', limit=500)
        calls = Call.search([('partner_id', '=', partner.id)], order='id', limit=500)

        events = []
        for m in msgs:
            events.append((m.created_at or m.create_date, 'msg', m))
        for c in calls:
            events.append((c.created_at or c.create_date, 'call', c))
        if not events:
            return Markup(
                '<div style="padding:16px;opacity:.6">%s</div>'
                % escape(self.env._('No WhatsApp or call activity yet.'))
            )
        events.sort(key=lambda e: (e[0] or fields.Datetime.now()))

        style = (
            '<style>'
            '.htf-convo{padding:10px;max-width:900px}'
            # No justify-content: under the RTL Arabic UI, flex-end/start
            # pushed bubbles to the wrong side. Letting every bubble align
            # to the flex start (the right edge in RTL) reads cleanly —
            # direction is conveyed by colour (in=grey, out=green) + the
            # author/time meta line, not by left/right placement.
            '.htf-row{display:flex !important;margin:0 0 4px 0 !important}'
            '.htf-b{max-width:78%;color:#fff;padding:7px 10px;'
            'border-radius:10px;line-height:1.35}'
            '.htf-b.in{background:#3a3f4b}'
            '.htf-b.out{background:#0b7a5f}'
            '.htf-b.call{max-width:88%;background:#2b2b3a;border:1px solid #444}'
            '.htf-meta{font-size:11px;opacity:.7;margin:0 0 2px 0 !important}'
            '.htf-rec{display:block;margin:6px 0 0 0 !important;width:260px;'
            'max-width:100%;height:34px}'
            '.htf-day{text-align:center;margin:10px 0 6px 0 !important}'
            '.htf-day span{background:#3a3f4b;color:#cfd3da;font-size:11px;'
            'padding:2px 10px;border-radius:10px}'
            '</style>'
        )
        rows = [style, '<div class="htf-convo">']
        last_day = None
        for ts, kind, rec in events:
            when = discuss_mirror._local_hm(render_env, ts) if ts else ''
            # Date separator when the (workspace-local) day changes.
            day_key, day_label = self._htf_day_label(render_env, ts)
            if day_key and day_key != last_day:
                last_day = day_key
                rows.append(
                    '<div class="htf-day"><span>%s</span></div>' % escape(day_label)
                )
            rec = rec.with_env(render_env)
            if kind == 'msg':
                inbound = rec.direction == 'inbound'
                inner = discuss_mirror._render_wa_body(rec, rec.direction)
                who = (
                    partner.name if inbound
                    else (rec.sender_user_id.name or self.env._('Agent'))
                )
                side = 'in' if inbound else 'out'
                rows.append(
                    '<div class="htf-row %s"><div class="htf-b %s">'
                    '<div class="htf-meta">%s · %s</div>%s</div></div>' % (
                        side, side, escape(who or ''), escape(when), inner,
                    )
                )
            else:
                inner = discuss_mirror._render_call_body(rec)
                audio = self._htf_call_recording_player(rec)
                rows.append(
                    '<div class="htf-row call"><div class="htf-b call">%s%s'
                    '</div></div>' % (inner, audio)
                )
        rows.append('</div>')
        return Markup(''.join(rows))

    def _htf_day_label(self, render_env, ts):
        """Return ``(date, label)`` for a timeline date separator, computed
        in the workspace timezone. Label is Today / Yesterday / a localized
        date. ``(None, '')`` when ``ts`` is missing.
        """
        if not ts:
            return (None, '')
        from datetime import datetime as _dt, timedelta as _td

        import pytz

        from ..services import discuss_mirror
        try:
            tz = pytz.timezone(discuss_mirror._bubble_tz(render_env))
            day = pytz.utc.localize(ts).astimezone(tz).date()
            today = _dt.now(tz).date()
            if day == today:
                return (day, self.env._('Today'))
            if day == today - _td(days=1):
                return (day, self.env._('Yesterday'))
            try:
                from babel.dates import format_date
                loc = (render_env.context.get('lang') or 'en_US').replace('-', '_')
                return (day, format_date(day, format='d MMMM y', locale=loc))
            except Exception:  # noqa: BLE001
                return (day, day.strftime('%d %b %Y'))
        except Exception:  # noqa: BLE001
            return (None, '')

    def _htf_call_recording_player(self, call_row):
        """Return an <audio> player for a call's recording, or ''.

        Reuses the recording attachment the Discuss voice-mirror already
        downloaded (linked to the ``<htf-call-N>`` bubble), served via
        /web/content with an access token so the lead viewer can play it
        without separate attachment ACLs. No attachment (older call) → no
        player.
        """
        from html import escape

        sentinel = '<htf-call-%d@htf_call_center>' % call_row.id
        bubble = self.env['mail.message'].sudo().search(
            [('message_id', '=', sentinel)], limit=1,
        )
        att = bubble.attachment_ids[:1] if bubble else None
        if not att:
            return ''
        token = att.access_token or att.sudo().generate_access_token()[0]
        src = '/web/content/%d?access_token=%s' % (att.id, escape(token))
        return (
            '<audio class="htf-rec" controls preload="none">'
            '<source src="%s" type="%s"></audio>' % (
                src, escape(att.mimetype or 'audio/wav'),
            )
        )

    def write(self, vals):
        """When the lead's salesperson, partner, or team changes,
        re-sync the Hatif Discuss channel membership so the new agent
        gets access and the old agent loses it. Without this hook,
        re-assigning a lead leaves the channel members stuck on
        whoever the channel was originally provisioned for.

        team_id changes matter under the v19.0.1.27.0 2-gate model:
        the channel-gate is team-scoped, so moving a lead to a
        different team can cause the salesperson to gain or lose
        access via the channel they're mapped to.

        Only fires when the relevant keys are in the write payload —
        unrelated writes (stage, expected revenue, tags, etc.) skip
        the recompute.
        """
        affects_membership = any(k in vals for k in ('user_id', 'partner_id', 'team_id'))
        old_partners = {
            lead.id: lead.partner_id for lead in self
        } if affects_membership else {}

        res = super().write(vals)

        if not affects_membership:
            return res

        partners_to_resync = self.env['res.partner']
        for lead in self:
            old = old_partners.get(lead.id)
            if old and old != lead.partner_id:
                partners_to_resync |= old
            if lead.partner_id:
                partners_to_resync |= lead.partner_id

        self._htf_resync_partner_channels(partners_to_resync)
        return res

    def action_htf_open_whatsapp(self):
        """Delegate to the partner's WhatsApp entry point (Discuss popup
        when the new UX flag is on, classic wizard otherwise).

        Falls back to the wizard with the lead's phone pre-filled when
        the lead has no linked partner yet.
        """
        self.ensure_one()
        cfg = self.env['htf.config'].sudo()
        if self.partner_id:
            return self.partner_id.action_htf_open_whatsapp()
        # No partner yet — fall back to the classic wizard so the agent
        # can still send a template against a raw phone number.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp'),
            'res_model': 'htf.send.whatsapp.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_to_number': self.phone or self.mobile or '',
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        partners = self.env['res.partner']
        for lead in leads:
            if lead.partner_id and lead.user_id:
                partners |= lead.partner_id
        if partners:
            self._htf_resync_partner_channels(partners)
        return leads

    def _htf_resync_partner_channels(self, partners):
        """Recompute Hatif Discuss channel membership for each partner's
        channel, if one exists. Errors per partner are logged and
        swallowed so a sync hiccup never breaks the calling write/create.
        """
        if not partners:
            return
        Channel = self.env['discuss.channel'].sudo()
        for partner in partners:
            channel = Channel.search([
                ('x_htf_partner_id', '=', partner.id),
                ('active', '=', True),
            ], limit=1)
            if not channel:
                continue
            try:
                channel._htf_sync_channel_members()
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-discuss] channel-member resync failed for "
                    "channel id=%s partner id=%s — non-fatal",
                    channel.id, partner.id,
                )

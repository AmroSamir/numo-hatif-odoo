"""discuss.channel extension for P7 — Hatif conversation surface.

Adds 3 fields that mark a `discuss.channel` as a "Hatif-linked" channel:
one channel per `res.partner` with Hatif activity. The channel is created
lazily by services/whatsapp_inbound.py + services/calls.py on first
inbound webhook for that partner. With the master flag
`htf_call_center.discuss_mirror_enabled` off, these fields stay empty and
no codepath in the module touches discuss.channel.

The schema is additive only — every field is nullable, has a safe
default, and is unreferenced when the feature flag is off, so dropping
this file in a revert leaves the columns harmless.

P7.5 patches the OWL ChatWindow component to look at `x_htf_partner_id`
to decide whether to hide the native voice-call icon and render the
"Call via Hatif" button. With `discuss_ui_override=False`, the patch is
a no-op and the field is read but ignored.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..exceptions import HtfDncBlockedError, HtfWindowExpiredError

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    # The customer this channel represents. NULL on every standard
    # Odoo channel (DMs, internal channels, livechat, etc.) — only
    # set on auto-provisioned Hatif mirror channels. Indexed so the
    # OWL patch's `t-if` on x_htf_partner_id is cheap, and so the
    # revert tooling can find every Hatif-linked channel in one query.
    x_htf_partner_id = fields.Many2one(
        'res.partner',
        string='Hatif Customer',
        copy=False,
        index=True,
        ondelete='set null',
        help='Set when this channel is the per-partner mirror of '
             'Hatif activity. NULL on every standard Odoo channel.',
    )
    # Most recent conversationId observed on any webhook for this
    # partner. Used by the OWL ChatWindow patch to build the
    # "Call via Hatif" deep-link `app.hatif.io/ar/inbox?conversationId=<id>`.
    x_htf_last_conversation_id = fields.Char(
        string='Last Hatif conversationId',
        copy=False,
        help='Updated on every webhook. Empty until the first webhook '
             'lands for this partner.',
    )
    # Most recent Hatif channel (the workspace channel like
    # "أكاديمية نمو" or "الدعم الفني") this conversation flowed
    # through. Used when the outbound override needs to pick which
    # Hatif channel to send a reply on — falls back to the existing
    # resolver chain when empty.
    x_htf_last_htf_channel_id = fields.Many2one(
        'htf.channel',
        string='Last Hatif Channel Used',
        copy=False,
        ondelete='set null',
        help='Updated on every webhook. Tells the outbound override '
             'which Hatif channel to route the agent reply through.',
    )

    # ------------------------------------------------------------------ #
    # P7.5 — Push x_htf fields to the OWL store                          #
    # ------------------------------------------------------------------ #
    # The OWL ChatWindow patch reads `thread.x_htf_partner_id` to decide
    # whether to hide the native voice-call buttons and render the
    # "Call via Hatif" anchor. Without this _to_store_defaults override
    # the fields stay server-side and the patch sees `undefined`.
    #
    # Gated by the `discuss_ui_override` sub-flag — turning it off
    # makes the OWL patch see undefined on every channel, so the
    # native UI returns even though the schema + mirror are still
    # active. This is the L2 revert path for the OWL surface alone.

    def _to_store_defaults(self, target):
        base = super()._to_store_defaults(target)
        if self.env['htf.config'].discuss_mirror_active('ui'):
            return base + ['x_htf_partner_id', 'x_htf_last_conversation_id']
        return base

    # ------------------------------------------------------------------ #
    # Channel auto-provisioning                                          #
    # ------------------------------------------------------------------ #

    @api.model
    def _ensure_htf_discuss_channel(self, partner):
        """Get-or-create the per-partner Hatif Discuss channel.

        Idempotent. Returns the channel record. CALLER MUST CHECK the
        master feature flag before calling — this method assumes it is
        on and proceeds unconditionally.

        Channel shape (decisions locked 2026-05-19):
          - channel_type='channel' (private)
          - name = f"Hatif · {partner.display_name}"
          - members: the partner (so their name + avatar render on
            inbound bubbles via author_id=partner.id)
          - x_htf_partner_id = partner.id (this is what the OWL patch
            and revert tooling look for)
        """
        if not partner:
            return self.env['discuss.channel']
        # Fast path — back-reference on the partner.
        if partner.x_htf_discuss_channel_id and partner.x_htf_discuss_channel_id.active:
            return partner.x_htf_discuss_channel_id
        # Slow path — orphan-search by x_htf_partner_id (handles the case
        # where partner.x_htf_discuss_channel_id got cleared somehow).
        existing = self.sudo().search(
            [('x_htf_partner_id', '=', partner.id), ('active', '=', True)], limit=1,
        )
        if existing:
            if not partner.x_htf_discuss_channel_id:
                partner.sudo().write({'x_htf_discuss_channel_id': existing.id})
            return existing
        # Create. Channel name uses a 📞 emoji prefix so the rows sort
        # together alphabetically AND are visually distinct from regular
        # Odoo channels (general, etc.) in the Discuss sidebar — Odoo 19
        # doesn't support custom sidebar categories, so prefix-grouping
        # is the cheapest legible solution.
        channel_name = f'📞 {partner.display_name or partner.name or "?"}'
        channel = self.sudo().create({
            'name': channel_name[:200],  # mail enforces 200-char cap somewhere
            'channel_type': 'channel',
            'group_public_id': False,  # private — only invited members see it
            'x_htf_partner_id': partner.id,
        })
        # Add the customer as a participant so author_id=partner.id renders
        # their name + avatar on inbound bubbles. They have no res.users
        # — they never log in. This is the "partner-as-participant"
        # decision from the spec.
        self.env['discuss.channel.member'].sudo().create({
            'channel_id': channel.id,
            'partner_id': partner.id,
        })
        partner.sudo().write({'x_htf_discuss_channel_id': channel.id})
        _logger.info(
            "[htf-discuss] auto-provisioned channel id=%s for partner id=%s (%s)",
            channel.id, partner.id, partner.display_name,
        )
        return channel

    # ------------------------------------------------------------------ #
    # P7.4 — Outbound override                                           #
    # ------------------------------------------------------------------ #
    # When an internal Odoo user types in a Hatif-linked channel, route
    # the message body through Hatif WhatsApp outbound after the
    # message is persisted. Guards:
    #   1. Channel must have x_htf_partner_id set.
    #   2. Master flag + outbound sub-flag must be on.
    #   3. The context flag `htf_mirror_write` is NOT set (which is
    #      what our own mirror writes from services/discuss_mirror.py
    #      use to avoid an infinite loop).
    #   4. The message author is NOT the partner (i.e. it's not an
    #      inbound mirror from a customer-as-author write).
    #   5. The message subtype is NOT the htf-mirror sentinel.
    #
    # 24h-window check fails -> UserError -> Odoo rolls back the
    # transaction (the persisted mail.message is undone) and OWL shows
    # the error toast. This honors locked decision 5(a): "reject with
    # toast" (no auto-template injection).

    def _message_post_after_hook(self, message, msg_vals):
        # Always call super() FIRST so non-Hatif channels are not
        # affected and the base bookkeeping (notification, bus, etc.)
        # runs unaffected.
        result = super()._message_post_after_hook(message, msg_vals)
        try:
            if not self._htf_should_route_outbound(message, msg_vals):
                return result
            self._htf_send_outbound_via_hatif(message)
        except UserError:
            raise
        except Exception:  # noqa: BLE001 — never lose an error to logs
            _logger.exception(
                "[htf-discuss] outbound route failed for channel=%s message=%s",
                self.id, message.id,
            )
            raise UserError(
                _('WhatsApp send via Hatif failed — see server logs for details.')
            ) from None
        return result

    def _htf_should_route_outbound(self, message, msg_vals) -> bool:
        """Five-gate check for the outbound override. All must be True."""
        # 1. Hatif-linked channel
        if not self.x_htf_partner_id:
            return False
        # 2. Master + sub-flag
        if not self.env['htf.config'].discuss_mirror_active('outbound'):
            return False
        # 3. Not our own mirror write
        if self.env.context.get('htf_mirror_write'):
            return False
        # 4. Not authored by the partner (=inbound mirror)
        if message.author_id and message.author_id == self.x_htf_partner_id:
            return False
        # 5. Not the mt_htf_mirror sentinel subtype
        mirror_subtype = self.env.ref(
            'htf_call_center.mt_htf_mirror', raise_if_not_found=False
        )
        if message.subtype_id and mirror_subtype and message.subtype_id == mirror_subtype:
            return False
        # Only route messages with actual text. Voice notes, file uploads,
        # and pure attachment posts are routed only when there's body text.
        # (Hatif voice/audio outbound isn't in scope for P7.)
        plain = html2plaintext(message.body or '').strip()
        if not plain:
            return False
        return True

    def _htf_send_outbound_via_hatif(self, message):
        """Send the message body through Hatif WhatsApp outbound.

        Errors raise UserError so OWL renders the toast and Odoo rolls
        back the persisted mail.message. This is the locked-decision-5(a)
        path: window-closed = explicit rejection, not silent fallback.
        """
        from ..services import whatsapp  # local import to avoid cycle at boot
        partner = self.x_htf_partner_id
        if not partner:
            raise UserError(_('Hatif channel has no partner — cannot send.'))
        phone = partner.phone or partner.mobile or ''
        if not phone:
            raise UserError(
                _('Partner %s has no phone number — cannot send WhatsApp.')
                % partner.display_name
            )
        plain_body = html2plaintext(message.body or '').strip()
        if not plain_body:
            raise UserError(_('Empty message body — nothing to send.'))
        try:
            whatsapp.send_text(
                self.env, to_number=phone, text=plain_body, partner=partner,
            )
        except HtfDncBlockedError:
            raise UserError(_(
                'This partner has opted out (DNC). WhatsApp send blocked.'
            )) from None
        except HtfWindowExpiredError:
            raise UserError(_(
                'The 24-hour WhatsApp window is closed for %s. '
                'Use a template via the partner form Send WhatsApp button instead.'
            ) % partner.display_name) from None

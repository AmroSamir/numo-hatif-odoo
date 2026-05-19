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

from odoo import api, fields, models

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
        # Create. Use _create_channel to get sensible defaults, then
        # adjust. The display_name fallback handles partners without
        # x_htf_contact_id (e.g., manual creations).
        channel_name = f'Hatif · {partner.display_name or partner.name or "?"}'
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

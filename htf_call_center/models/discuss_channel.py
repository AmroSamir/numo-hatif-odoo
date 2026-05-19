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

from odoo import fields, models


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

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

from odoo import api, fields, models

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

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

from odoo import fields, models


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

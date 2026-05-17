"""htf.message — WhatsApp message record (inbound or outbound).

Per DATA_MODEL.md §htf.message and P2_WHATSAPP_INBOUND.md.

Lifecycle:
1. Inbound webhook hits ``controllers/webhook_whatsapp.py``
2. ``services/whatsapp_inbound.py`` creates an ``htf.message`` row
3. ``services/chatter.py`` posts the bubble to ``res.partner`` chatter
   and stores the resulting ``mail.message.id`` in ``chatter_message_id``
4. Outbound STATUS webhooks (Sent → Delivered → Read → Failed) hit the
   same endpoint and update ``state`` + ``delivered_at`` / ``read_at`` /
   ``error_code`` on the existing row (matched by ``htf_message_id``)

``conversation_id`` Many2one to ``htf.conversation`` is INTENTIONALLY
omitted in P2 because the conversation model lands in P5. The raw
``conversation_event_id`` (Char) is captured so we can backfill the FK
when P5 ships.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Hatif → Odoo selection mappings ------------------------------------- #

# direction: "Inbound" / "Outbound" → "inbound" / "outbound"
HATIF_DIRECTION_MAP = {
    'inbound': 'inbound',
    'outbound': 'outbound',
}

# messageType: "Text", "Image", ..., "Interactive" → lowercase
HATIF_MESSAGE_TYPES = (
    'text', 'image', 'video', 'audio', 'document',
    'location', 'contact', 'sticker', 'template', 'interactive',
)

# status: "Pending" / "Sent" / "Delivered" / "Read" / "Failed" → lowercase
HATIF_STATUS_MAP = {
    'pending': 'pending',
    'sent': 'sent',
    'delivered': 'delivered',
    'read': 'read',
    'failed': 'failed',
}


class HtfMessage(models.Model):
    _name = 'htf.message'
    _description = 'HTF WhatsApp Message'
    _order = 'created_at desc, id desc'
    _rec_name = 'name'
    _log_access = True

    # Display / identity ---------------------------------------------- #
    name = fields.Char(compute='_compute_name', store=True)
    htf_message_id = fields.Char(
        string='Meta Message ID',
        index=True,
        help='Meta-side WhatsApp message id from the webhook payload. '
             'May be null for very fresh messages (Hatif fills it in on a '
             'subsequent status update).',
    )
    conversation_event_id = fields.Char(
        string='Hatif Conversation Event ID',
        index=True,
        help='Returned by sendTemplate / sendText; used to correlate '
             'outbound sends with later STATUS updates when messageId is '
             'not yet known.',
    )
    conversation_uuid = fields.Char(
        string='Hatif Conversation UUID',
        index=True,
        help='Raw conversationId from the Hatif webhook. Will be promoted '
             'to a Many2one to htf.conversation when P5 ships.',
    )
    contact_uuid = fields.Char(
        string='Hatif Contact UUID',
        index=True,
        help='Raw contactId from the Hatif webhook. Resolves to '
             'htf.contact.link → res.partner.',
    )

    # Content --------------------------------------------------------- #
    direction = fields.Selection(
        selection=[
            ('inbound', 'Inbound'),
            ('outbound', 'Outbound'),
        ],
        required=True,
        index=True,
    )
    message_type = fields.Selection(
        selection=[
            ('text', 'Text'),
            ('image', 'Image'),
            ('video', 'Video'),
            ('audio', 'Audio'),
            ('document', 'Document'),
            ('location', 'Location'),
            ('contact', 'Contact'),
            ('sticker', 'Sticker'),
            ('template', 'Template'),
            ('interactive', 'Interactive'),
        ],
        required=True,
        index=True,
    )
    body = fields.Text(
        help='Text body. Present for text, template, interactive — also '
             'used to carry a vCard for contact messages.',
    )
    media_url = fields.Char(
        help='URL to the media file. Treat as ephemeral per Q-06: '
             'Hatif does not commit to retention or signed-URL expiry. '
             'P4 cache layer (Q-15) will copy into ir.attachment.',
    )
    mime_type = fields.Char()
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))

    # State / status -------------------------------------------------- #
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('delivered', 'Delivered'),
            ('read', 'Read'),
            ('failed_pending', 'Failed — retrying'),
            ('failed', 'Failed'),
        ],
        required=True,
        default='pending',
        index=True,
    )
    error_code = fields.Integer()
    error_reason = fields.Char()
    is_billable = fields.Boolean(default=False)
    meta_category = fields.Selection(
        selection=[
            ('marketing', 'Marketing'),
            ('utility', 'Utility'),
            ('authentication', 'Authentication'),
            ('service', 'Service'),
        ],
        help='Meta WA Business category — drives local cost estimate '
             'until Q-09 (Hatif cost API) is answered.',
    )
    meta_cost_estimate = fields.Float(
        digits=(10, 4),
        help='Local cost estimate in USD per Meta category. Updated when '
             'Hatif exposes a per-message cost API.',
    )

    # Timestamps ------------------------------------------------------ #
    created_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
        help='When Hatif first observed the message (creationTime in the '
             'webhook payload). NOT Odoo create_date — that one tracks '
             'when the bridge persisted the row.',
    )
    delivered_at = fields.Datetime()
    read_at = fields.Datetime()

    # Relations ------------------------------------------------------- #
    channel_id = fields.Many2one(
        'htf.channel',
        ondelete='restrict',
        index=True,
        help='Resolved from webhook.channelId via htf_channel_id lookup.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        ondelete='set null',
        index=True,
        help='Resolved partner — auto-created on first inbound from an '
             'unknown phone number (P2 T2.4).',
    )
    sender_user_id = fields.Many2one(
        'res.users',
        ondelete='set null',
        help='Hatif user who sent this outbound message. Resolved via '
             'htf.user.link from webhook.senderUserId. Null for inbound.',
    )
    chatter_message_id = fields.Many2one(
        'mail.message',
        ondelete='set null',
        copy=False,
        help='Back-reference to the chatter post on res.partner so STATUS '
             'updates can re-render the icon without creating a duplicate '
             'bubble (P2 T2.5).',
    )

    # Audit ----------------------------------------------------------- #
    raw_payload = fields.Text(
        help='JSON-serialized webhook body (after PII redaction). Used '
             'for debugging when a message renders oddly or a status '
             'transition fails. Trim periodically — these can get fat.',
    )
    is_opt_out = fields.Boolean(
        default=False,
        help='Inbound text matched a DNC opt-out keyword (P2 T2.5b). '
             'Bridge subscriber acts on this in P7.',
    )

    # Constraints ----------------------------------------------------- #
    # Plain UNIQUE allows multiple NULLs in Postgres (each NULL is
    # distinct), so this enforces uniqueness only on present values —
    # which is what we want, since Hatif sometimes ships the messageId
    # on a later STATUS update rather than on the first webhook.
    _htf_message_id_unique = models.Constraint(
        'unique(htf_message_id)',
        'Meta WhatsApp message id must be unique when present.',
    )

    # Computes -------------------------------------------------------- #
    @api.depends('direction', 'message_type', 'partner_id.name', 'channel_id.display_name')
    def _compute_name(self):
        for rec in self:
            direction_label = (
                _('Inbound') if rec.direction == 'inbound' else _('Outbound')
            )
            type_label = dict(self._fields['message_type'].selection).get(
                rec.message_type or '', rec.message_type or '?'
            )
            who = rec.partner_id.name or _('Unknown')
            via = rec.channel_id.display_name or rec.channel_id.name or '—'
            rec.name = f"[{direction_label} {type_label}] {who} via {via}"

    # API helpers ----------------------------------------------------- #
    @api.model
    def find_by_message_id(self, htf_message_id: str):
        """Return existing message by Meta id, or empty recordset."""
        if not htf_message_id:
            return self.browse()
        return self.search([('htf_message_id', '=', htf_message_id)], limit=1)

    @api.model
    def cron_retry_failed_pending(self, max_attempts: int = 6) -> int:
        """Thin wrapper so ir.cron can dispatch via the model layer.

        Delegates to ``services.whatsapp.cron_retry_failed_pending``
        because cron `state='code'` cannot import service modules
        directly per safe_eval rules — going through the model keeps
        the import inside Python.
        """
        from ..services import whatsapp
        return whatsapp.cron_retry_failed_pending(self.env, max_attempts=max_attempts)

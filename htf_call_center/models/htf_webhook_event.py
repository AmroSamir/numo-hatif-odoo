"""htf.webhook.event — idempotency table for inbound webhook deliveries.

Per SECURITY.md §Idempotency: each incoming webhook gets its provider event
id (callId, messageId, ivr id) recorded with the route. UNIQUE on
(event_id, route) means a Hatif retry that re-delivers the same payload
short-circuits to a 200 without re-firing signals or persisting duplicates.

A nightly cron archives rows older than 90 days.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HtfWebhookEvent(models.Model):
    _name = 'htf.webhook.event'
    _description = 'HTF Webhook Event (idempotency record)'
    _order = 'received_at desc, id desc'
    _log_access = True

    event_id = fields.Char(
        string='Provider Event ID',
        required=True,
        index=True,
        help='Vendor-side identifier — messageId for WA, callId for calls, '
             'IVR run id for IVR. Combined with route this is unique.',
    )
    route = fields.Selection(
        selection=[
            ('call', 'Call'),
            ('whatsapp', 'WhatsApp'),
            ('ivr', 'IVR'),
        ],
        required=True,
        index=True,
    )
    received_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    processed = fields.Boolean(default=False, index=True)
    payload_hash = fields.Char(
        string='SHA-256 Payload Hash',
        size=64,
        help='Hex digest of the raw body — debug aid when investigating '
             'webhook duplicates with subtly different bodies.',
    )
    note = fields.Char(help='Optional one-liner from the handler.')

    _sql_constraints = [
        (
            'event_route_unique',
            'unique(event_id, route)',
            'Webhook event must be unique per route — duplicate delivery.',
        ),
    ]

    # ------------------------------------------------------------------ #
    # Helpers used by webhook controllers (P2/P4/P5)                      #
    # ------------------------------------------------------------------ #

    @api.model
    def record_or_skip(self, event_id: str, route: str, raw_body: bytes = b''):
        """Insert an idempotency row or return False if already seen.

        Returns the new record on first delivery, False on duplicate.
        Controllers use the False return to short-circuit to a 200.
        """
        if not event_id or not route:
            # Without an event id we can't dedupe. Caller decides whether to
            # process anyway; this method just refuses to record garbage.
            return self.browse()

        payload_hash = ''
        if raw_body:
            try:
                payload_hash = hashlib.sha256(raw_body).hexdigest()
            except (TypeError, ValueError):
                payload_hash = ''

        try:
            with self.env.cr.savepoint():
                return self.sudo().create({
                    'event_id': event_id,
                    'route': route,
                    'payload_hash': payload_hash,
                })
        except Exception as exc:  # IntegrityError on UNIQUE
            _logger.info(
                "[htf] webhook duplicate route=%s event_id=%s (%s)",
                route, event_id, exc.__class__.__name__,
            )
            return False

    @api.model
    def mark_processed(self, record_id: int, note: str = '') -> None:
        if not record_id:
            return
        self.browse(record_id).sudo().write({
            'processed': True,
            'note': note or False,
        })

    # ------------------------------------------------------------------ #
    # Purge cron                                                          #
    # ------------------------------------------------------------------ #

    @api.model
    def cron_purge_old(self, days: int = 90) -> int:
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old = self.sudo().search([('received_at', '<', cutoff)])
        count = len(old)
        if count:
            old.unlink()
            _logger.info("[htf] purged %s webhook events older than %s days", count, days)
        return count

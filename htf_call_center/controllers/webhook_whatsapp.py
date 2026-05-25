"""POST /htf/webhook/whatsapp — Hatif WhatsApp Message Webhook receiver.

Pipeline:

1.  Read the raw request body (bytes). The HMAC is computed over the bytes
    *as Hatif sent them* — re-encoding `request.jsonrequest` would change
    the signature.
2.  Verify the ``X-Voxa-Signature`` header against
    ``htf.config.webhook_secrets()`` (current + previous, for rotation
    overlap per Q-04).
3.  Parse JSON payload. Extract ``messageId``.
4.  Idempotency: ``htf.webhook.event.record_or_skip(messageId, 'whatsapp')``.
    A successful prior delivery returns False → we 200 immediately and do
    NOT re-fire signals.
5.  Hand off to the dispatcher (inbound vs outbound STATUS).
6.  Mark the event processed for audit.

Failure modes:

- Bad signature → 401, no processing.
- Missing/invalid JSON → 400, no idempotency row created.
- Dispatch raises → 500, the surrounding Odoo transaction rolls back
  including the idempotency row. Hatif retries (5 attempts, exponential
  backoff per Q-22).

Per Q-02 ASSUMED: no IP allowlist. HMAC + idempotency is sole auth.
"""

from __future__ import annotations

import json
import logging

from odoo import http
from odoo.http import Response, request

from ..constants import WEBHOOK_SIGNATURE_HEADER
from ..services import hmac_verify

_logger = logging.getLogger(__name__)

WEBHOOK_ROUTE_WHATSAPP = '/htf/webhook/whatsapp'


class HtfWhatsAppWebhookController(http.Controller):

    @http.route(
        WEBHOOK_ROUTE_WHATSAPP,
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def receive_whatsapp(self, **kwargs):
        # Step 1: read raw body — DO NOT use request.jsonrequest, which
        # re-serializes and would invalidate the HMAC.
        raw_body = request.httprequest.get_data(cache=False)

        # Step 2: verify HMAC unless explicitly skipped.
        #
        # Q-03 ANSWERED claimed Hatif signs with HMAC-SHA256 in the
        # X-Voxa-Signature header. Live UAT against the real Hatif
        # endpoint (2026-05-18) revealed they currently send NO
        # signature header at all (signature_headers={} in diagnostic
        # logs). Until Hatif's spec catches up to their implementation,
        # admins can flip htf.config.dev_mode_skip_hmac=True to accept
        # unsigned payloads. Idempotency + IP context (X-Forwarded-For)
        # remain available as defence-in-depth.
        cfg = request.env['htf.config'].sudo()
        skip_hmac = bool(cfg.get_param('dev_mode_skip_hmac'))

        if skip_hmac:
            _logger.warning(
                "[htf-wa] HMAC verification SKIPPED via "
                "htf.config.dev_mode_skip_hmac=True. Source IP: %s. "
                "Re-enable verification once Hatif starts signing webhooks.",
                request.httprequest.headers.get('X-Real-Ip') or
                request.httprequest.remote_addr,
            )
        elif not hmac_verify.verify_from_request(
            request.env, raw_body, request.httprequest.headers,
        ):
            _log_signature_failure_diagnostics(request, raw_body)
            return Response('invalid signature', status=401)

        # Step 3: parse JSON.
        try:
            payload = json.loads(raw_body.decode('utf-8') or 'null')
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _logger.warning("[htf-wa] webhook %s bad JSON: %s%s",
                            WEBHOOK_ROUTE_WHATSAPP, exc,
                            _reject_diag(request, raw_body))
            return Response('invalid json', status=400)

        if not isinstance(payload, dict):
            # Observed live: Hatif/network occasionally delivers a webhook
            # with an EMPTY body (parses to None), which costs us that one
            # inbound message because Hatif does not retry a 4xx. Log the
            # declared Content-Length vs the bytes we actually read so the
            # next occurrence shows whether the body was truncated in
            # transit (Content-Length > 0, 0 bytes read) or Hatif genuinely
            # sent nothing (Content-Length 0).
            _logger.warning("[htf-wa] webhook payload not an object: %r%s",
                            type(payload).__name__,
                            _reject_diag(request, raw_body))
            return Response('invalid payload', status=400)

        # Step 4: build the dedupe key.
        #
        # Hatif reuses the SAME messageId across the outbound lifecycle
        # (Sent → Delivered → Read → Failed), so a bare messageId-only key
        # would falsely deduplicate distinct status transitions. The
        # composite ``<messageId>:<status>:<direction>`` is unique per
        # state-change event while still collapsing genuine retries
        # (Hatif resends the same body — same status, same direction).
        #
        # On a fresh inbound where messageId is null we synthesise a key
        # from conversationId + creationTime (Hatif retries resend the
        # same body verbatim per Q-22, so this is stable across attempts).
        message_id = payload.get('messageId') or _synth_event_id(payload)
        if not message_id:
            _logger.warning("[htf-wa] no message_id, no synth key — skipping")
            return Response('no event id', status=400)
        dedupe_key = _compose_event_id(message_id, payload)

        # record_or_skip returns False on UNIQUE violation (duplicate of a
        # previously-COMMITTED delivery). A row that was created in an
        # earlier transaction that rolled back will NOT exist, so retries
        # of failed deliveries proceed normally.
        event_record = request.env['htf.webhook.event'].sudo().record_or_skip(
            dedupe_key, 'whatsapp', raw_body,
        )
        if event_record is False:
            _logger.info("[htf-wa] duplicate event_id=%s — short-circuit 200",
                         _short(dedupe_key))
            return Response('OK (duplicate)', status=200)

        # Step 5: dispatch.
        try:
            from ..services import whatsapp_inbound
            outcome = whatsapp_inbound.process(request.env, payload)
        except Exception as exc:  # noqa: BLE001 — top-level handler
            _logger.exception(
                "[htf-wa] dispatch failed for event_id=%s — letting Hatif retry",
                _short(dedupe_key),
            )
            # Re-raise so Odoo rolls back the transaction (including the
            # idempotency row), then return 500 so Hatif retries.
            return Response(f'dispatch failed: {exc.__class__.__name__}',
                            status=500)

        # Step 6: mark processed (audit only).
        if event_record:
            request.env['htf.webhook.event'].sudo().mark_processed(
                event_record.id, note=outcome,
            )

        return Response('OK', status=200)


def _compose_event_id(message_id: str, payload: dict) -> str:
    """Compose the idempotency key as ``<messageId>:<status>:<direction>``.

    Outbound STATUS transitions share a messageId across Sent/Delivered/
    Read/Failed events — distinguishing on ``status`` keeps each
    transition addressable while genuine Hatif retries (same status,
    same direction) still collapse.
    """
    status = (payload.get('status') or '').strip().lower() or '_'
    direction = (payload.get('direction') or '').strip().lower() or '_'
    return f'{message_id}:{status}:{direction}'


def _synth_event_id(payload: dict) -> str:
    """Synthetic dedupe key when ``messageId`` is null on a fresh inbound.

    Combines conversationId + creationTime so retries of the same payload
    still collapse to one row. Hatif's retry policy resends the same body,
    so this is stable across attempts.
    """
    conv = payload.get('conversationId') or ''
    ts = payload.get('creationTime') or ''
    if conv and ts:
        return f'synth:{conv}:{ts}'
    return ''


def _short(value: str | None) -> str:
    """Log-friendly truncation — message ids are long UUIDs."""
    if not value:
        return ''
    return value if len(value) <= 16 else f'{value[:13]}...'


def _reject_diag(req, raw_body: bytes) -> str:
    """Diagnostic suffix for rejected (400) webhooks.

    Compares the declared Content-Length with the bytes we actually read
    so a recurrence of the empty-body drop is attributable to either
    in-transit truncation or a genuinely empty Hatif payload. No secrets
    are logged — only transport metadata + a short body preview.
    """
    try:
        h = req.httprequest.headers
        body_len = len(raw_body or b'')
        preview = (raw_body[:120] or b'').decode('utf-8', errors='replace')
        return (
            " [diag content_length=%s bytes_read=%d user_agent=%r "
            "content_type=%r x_forwarded_for=%r body_preview=%r]" % (
                h.get('Content-Length'), body_len, h.get('User-Agent'),
                h.get('Content-Type'), h.get('X-Forwarded-For'), preview,
            )
        )
    except Exception:  # noqa: BLE001 — diagnostics must never break the 400
        return ''


def _log_signature_failure_diagnostics(req, raw_body: bytes) -> None:
    """Emit detailed diagnostics on HMAC verification failure.

    Active only when ``htf.config.debug_log_enabled`` is True so
    production logs stay quiet. The output is what we need to
    reverse-engineer the actual secret + algorithm Hatif is using
    when the documented X-Voxa-Signature/HMAC-SHA256/Client-Secret
    triple doesn't match.
    """
    import hashlib
    import hmac as _hmac

    debug_on = False
    try:
        debug_on = req.env['htf.config'].sudo().get_param('debug_log_enabled')
    except Exception:  # noqa: BLE001
        debug_on = False

    if not debug_on:
        _logger.warning(
            "[htf-wa] webhook %s rejected: invalid signature "
            "(enable htf.config.debug_log_enabled for diagnostics)",
            WEBHOOK_ROUTE_WHATSAPP,
        )
        return

    headers = dict(req.httprequest.headers.items() or {})
    # Headers most likely to carry a Hatif signature.
    candidate_header_names = (
        'X-Voxa-Signature', 'X-Hatif-Signature', 'X-Signature',
        'X-Hub-Signature', 'X-Hub-Signature-256', 'X-Webhook-Signature',
        'Signature', 'X-Hmac-Signature',
    )
    sig_headers = {
        k: v for k, v in headers.items()
        if k.lower() in {n.lower() for n in candidate_header_names}
    }

    # Headers redacted to ones safe to log (no Authorization, no cookies).
    safe_keys = ('content-type', 'content-length', 'user-agent', 'host',
                 'x-forwarded-for', 'x-forwarded-proto', 'x-real-ip',
                 *[h.lower() for h in candidate_header_names])
    safe_headers = {
        k: v for k, v in headers.items() if k.lower() in safe_keys
    }

    # What we computed vs what arrived.
    body_len = len(raw_body or b'')
    body_sha256 = hashlib.sha256(raw_body or b'').hexdigest()
    body_preview = (raw_body[:200] or b'').decode('utf-8', errors='replace')

    secrets = req.env['htf.config'].sudo().webhook_secrets() or []
    candidate_hmacs = {}
    for i, s in enumerate(secrets):
        if not s:
            continue
        candidate_hmacs[f'secret_{i}_hex_sha256'] = _hmac.new(
            s.encode(), raw_body or b'', hashlib.sha256,
        ).hexdigest()

    _logger.warning(
        "[htf-wa] webhook %s rejected: invalid signature\n"
        "  body_len=%s body_sha256=%s\n"
        "  body_preview=%r\n"
        "  signature_headers=%r\n"
        "  safe_headers=%r\n"
        "  our_computed_hmacs=%r",
        WEBHOOK_ROUTE_WHATSAPP,
        body_len, body_sha256, body_preview,
        sig_headers, safe_headers, candidate_hmacs,
    )

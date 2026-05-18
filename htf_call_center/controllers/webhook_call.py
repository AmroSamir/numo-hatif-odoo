"""POST /htf/webhook/call — Hatif Post-Call Webhook receiver.

Identical hardening contract to the WhatsApp controller (P2 T2.2):

1. Read the raw request body (bytes) — DO NOT use jsonrequest.
2. Verify HMAC unless dev_mode_skip_hmac=True (post-2026-05-19 reality:
   Hatif does NOT sign webhooks, so this flag stays ON in prod until
   they enable signing — see HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md).
3. Parse JSON.
4. Idempotency via htf.webhook.event with composite event_id:
   ``<htf_call_id>:<status>:<direction>`` — same rationale as the WA
   controller (Hatif may resend the same call object multiple times
   as status transitions from Active → Completed/Failed/etc.).
5. Hand off to ``services/calls.process()``.
6. Mark processed for audit.

Hard failures (5xx) → Hatif retries per Q-22 (5 attempts, exp
backoff, 62-min window).
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import logging

from odoo import http
from odoo.http import Response, request

from ..constants import WEBHOOK_SIGNATURE_HEADER
from ..services import hmac_verify

_logger = logging.getLogger(__name__)

WEBHOOK_ROUTE_CALL = '/htf/webhook/call'


class HtfCallWebhookController(http.Controller):

    @http.route(
        WEBHOOK_ROUTE_CALL,
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def receive_call(self, **kwargs):
        # Step 1: read raw body.
        raw_body = request.httprequest.get_data(cache=False)

        # Step 2: verify HMAC unless explicitly skipped.
        cfg = request.env['htf.config'].sudo()
        skip_hmac = bool(cfg.get_param('dev_mode_skip_hmac'))

        if skip_hmac:
            _logger.warning(
                "[htf-call] HMAC verification SKIPPED via "
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
            _logger.warning("[htf-call] webhook %s bad JSON: %s",
                            WEBHOOK_ROUTE_CALL, exc)
            return Response('invalid json', status=400)

        if not isinstance(payload, dict):
            _logger.warning("[htf-call] webhook payload not an object: %r",
                            type(payload).__name__)
            return Response('invalid payload', status=400)

        # Step 4: build the composite dedupe key.
        #
        # Hatif uses one CallId across the lifecycle (Active → Completed
        # / Missed / Failed). The composite key keeps each transition
        # addressable while genuine Hatif retries (same status, same
        # direction) still collapse.
        call_id = payload.get('id') or payload.get('callId') or \
            payload.get('CallId') or _synth_event_id(payload)
        if not call_id:
            _logger.warning("[htf-call] no call_id, no synth key — skipping")
            return Response('no event id', status=400)
        dedupe_key = _compose_event_id(call_id, payload)

        event_record = request.env['htf.webhook.event'].sudo().record_or_skip(
            dedupe_key, 'call', raw_body,
        )
        if event_record is False:
            _logger.info("[htf-call] duplicate event_id=%s — short-circuit 200",
                         _short(dedupe_key))
            return Response('OK (duplicate)', status=200)

        # Step 5: dispatch.
        try:
            from ..services import calls
            outcome = calls.process(request.env, payload)
        except Exception as exc:  # noqa: BLE001 — top-level handler
            _logger.exception(
                "[htf-call] dispatch failed for event_id=%s — letting Hatif retry",
                _short(dedupe_key),
            )
            return Response(f'dispatch failed: {exc.__class__.__name__}',
                            status=500)

        # Step 6: mark processed.
        if event_record:
            request.env['htf.webhook.event'].sudo().mark_processed(
                event_record.id, note=outcome,
            )

        return Response('OK', status=200)


# ---------------------------------------------------------------- #
# Helpers                                                          #
# ---------------------------------------------------------------- #

def _compose_event_id(call_id: str, payload: dict) -> str:
    status = str(payload.get('status') or '').strip().lower() or '_'
    direction = str(payload.get('type') or '').strip().lower() or '_'
    return f'{call_id}:{status}:{direction}'


def _synth_event_id(payload: dict) -> str:
    """Synthetic dedupe key when no call id is present."""
    chan = payload.get('channelId') or ''
    contact = payload.get('contactId') or payload.get('callerNumber') or ''
    ts = payload.get('creationTime') or ''
    if chan and ts:
        return f'synth:{chan}:{contact}:{ts}'
    return ''


def _short(value: str | None) -> str:
    if not value:
        return ''
    return value if len(value) <= 16 else f'{value[:13]}...'


def _log_signature_failure_diagnostics(req, raw_body: bytes) -> None:
    """Same diagnostic as the WA controller — useful when re-enabling HMAC."""
    debug_on = False
    try:
        debug_on = req.env['htf.config'].sudo().get_param('debug_log_enabled')
    except Exception:  # noqa: BLE001
        debug_on = False

    if not debug_on:
        _logger.warning(
            "[htf-call] webhook %s rejected: invalid signature "
            "(enable htf.config.debug_log_enabled for diagnostics)",
            WEBHOOK_ROUTE_CALL,
        )
        return

    headers = dict(req.httprequest.headers.items() or {})
    candidate_header_names = (
        'X-Voxa-Signature', 'X-Hatif-Signature', 'X-Signature',
        'X-Hub-Signature', 'X-Hub-Signature-256', 'X-Webhook-Signature',
        'Signature', 'X-Hmac-Signature',
    )
    sig_headers = {
        k: v for k, v in headers.items()
        if k.lower() in {n.lower() for n in candidate_header_names}
    }
    safe_keys = ('content-type', 'content-length', 'user-agent', 'host',
                 'x-forwarded-for', 'x-forwarded-proto', 'x-real-ip',
                 *[h.lower() for h in candidate_header_names])
    safe_headers = {
        k: v for k, v in headers.items() if k.lower() in safe_keys
    }

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
        "[htf-call] webhook %s rejected: invalid signature\n"
        "  body_len=%s body_sha256=%s\n"
        "  body_preview=%r\n"
        "  signature_headers=%r\n"
        "  safe_headers=%r\n"
        "  our_computed_hmacs=%r",
        WEBHOOK_ROUTE_CALL,
        body_len, body_sha256, body_preview,
        sig_headers, safe_headers, candidate_hmacs,
    )

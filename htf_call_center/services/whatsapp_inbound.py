"""Stub dispatcher for WhatsApp webhook events — fleshed out in T2.3.

The webhook controller (``controllers/webhook_whatsapp.py``) calls
``process(env, payload)`` after verifying HMAC + idempotency. For T2.2
this is a no-op log shim so the controller path is end-to-end testable.
T2.3 replaces this with the real dispatcher that branches by direction
and message_type.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def process(env, payload: dict) -> str:
    """Return a one-line audit note for ``htf.webhook.event.note``.

    Real implementation lands in T2.3. For now we just confirm the
    controller plumbing works and log enough context for debugging.
    """
    direction = payload.get('direction', '?')
    message_type = payload.get('messageType', '?')
    status = payload.get('status', '?')
    note = f'T2.2 stub: direction={direction} type={message_type} status={status}'
    _logger.info("[htf-wa] %s", note)
    return note

"""HMAC verification for inbound Hatif/Voxa webhooks.

Per Q-03 ANSWERED (apidog export L5088):

- Header: ``X-Voxa-Signature``
- Algorithm: HMAC-SHA256
- Encoding: lowercase hex
- Signed payload: raw JSON request body only — **no** timestamp prefix
- Per-channel ``webhookSecret`` configured manually on the Hatif side

There is NO timestamp header, so we DO NOT enforce a replay-window. Replay
protection comes from event-id idempotency (``htf.webhook.event`` UNIQUE
constraint) instead.

During secret rotation, both ``webhook_secret_current`` and
``webhook_secret_previous`` from ``htf.config`` are tried, so the system stays
verifiable across the 7-day overlap window.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Iterable

from ..constants import WEBHOOK_HASH_ALGO, WEBHOOK_SIGNATURE_HEADER

_logger = logging.getLogger(__name__)


def compute_signature(secret: str, body: bytes) -> str:
    """Return the expected HMAC-SHA256 hex digest of ``body`` under ``secret``."""
    if isinstance(secret, str):
        secret_bytes = secret.encode('utf-8')
    else:
        secret_bytes = secret
    return hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()


def _normalize_sig(sig: str | None) -> str:
    if not sig:
        return ''
    # Tolerate "sha256=..." prefix in case Hatif adds it on a future version;
    # current contract is bare hex, but compare_digest fails fast on length
    # mismatch anyway.
    sig = sig.strip()
    if sig.lower().startswith(f'{WEBHOOK_HASH_ALGO}='):
        sig = sig.split('=', 1)[1]
    return sig.lower()


def verify(
    body: bytes,
    signature: str | None,
    secrets: Iterable[str],
) -> bool:
    """Return True iff ``signature`` is a valid HMAC of ``body`` under any
    secret in ``secrets``.

    Empty signature, empty secret list, or empty body → False (never True).
    Uses ``hmac.compare_digest`` for timing-safe comparison.
    """
    received = _normalize_sig(signature)
    if not received:
        return False

    secret_list = [s for s in secrets if s]
    if not secret_list:
        _logger.warning("[htf] no webhook secret configured — refusing to verify")
        return False

    if body is None:
        body = b''
    if isinstance(body, str):
        body = body.encode('utf-8')

    for secret in secret_list:
        expected = compute_signature(secret, body)
        if hmac.compare_digest(expected, received):
            return True

    return False


def verify_from_request(env, body: bytes, headers) -> bool:
    """Convenience wrapper used by webhook controllers.

    ``headers`` is anything supporting ``.get(name)`` (a werkzeug Headers
    object, a plain dict, etc.).
    """
    signature = None
    if headers is not None:
        signature = headers.get(WEBHOOK_SIGNATURE_HEADER) or headers.get(
            WEBHOOK_SIGNATURE_HEADER.lower()
        )
    secrets = env['htf.config'].webhook_secrets()
    return verify(body, signature, secrets)

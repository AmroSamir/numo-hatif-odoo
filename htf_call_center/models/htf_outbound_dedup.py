"""Outbound-send idempotency claims.

v19.0.1.44.0 — stops duplicate WhatsApp sends caused by the Discuss
client resending a message_post when the synchronous Hatif HTTP call
is slow (verified live: one "هلا" reached the customer 5 times).

The trick is the *autonomous* claim: ``_htf_claim_send`` opens a
SEPARATE cursor, inserts a ``(channel, body)`` marker, and COMMITS it
immediately — before the slow Hatif POST runs in the caller's
transaction. That makes the claim visible to every other concurrent
or sequential request the instant it's made, so retries see it and
bail. A transaction-scoped advisory lock could not do this: it
releases at commit, so two sends 0.4s apart (each completing before
the next starts) never overlapped and both went through.

Rows older than the dedup window are purged opportunistically on each
claim, so the table stays tiny and the same text can be legitimately
re-sent once the window passes.
"""

from __future__ import annotations

import hashlib
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# How long a claim blocks an identical (channel, body) re-send. Tuned
# to cover the worst-case slow-Hatif window (~60s read timeout) plus a
# margin for websocket-reconnect resend storms.
_DEDUP_WINDOW_SECONDS = 90


class HtfOutboundDedup(models.Model):
    _name = 'htf.outbound.dedup'
    _description = 'HTF Outbound Send Idempotency Claim'

    dedup_key = fields.Char(required=True, index=True)
    _dedup_key_uniq = models.Constraint(
        'unique(dedup_key)',
        'An outbound-send claim with this key already exists.',
    )

    @api.model
    def _htf_claim_send(self, channel_id: int, body: str) -> bool:
        """Atomically claim an outbound (channel, body) send.

        Returns True when the caller may proceed with the Hatif POST,
        False when an identical send was already claimed within the
        dedup window (=> the caller must skip to avoid a duplicate).

        Uses an autonomous cursor committed immediately so the claim is
        visible cross-transaction before the caller's slow HTTP call.
        Never raises — on any DB hiccup it returns True (fail-open:
        better a rare duplicate than a dropped legitimate send).
        """
        key = (
            f'{channel_id}:'
            f'{hashlib.sha256((body or "").encode("utf-8")).hexdigest()}'
        )
        try:
            with self.env.registry.cursor() as cr:
                # Opportunistic cleanup so the table never grows and the
                # same text can be re-sent after the window elapses.
                cr.execute(
                    "DELETE FROM htf_outbound_dedup "
                    "WHERE create_date < (now() at time zone 'UTC') "
                    "- interval %s",
                    (f'{_DEDUP_WINDOW_SECONDS} seconds',),
                )
                cr.execute(
                    "INSERT INTO htf_outbound_dedup "
                    "(dedup_key, create_date) "
                    "VALUES (%s, now() at time zone 'UTC') "
                    "ON CONFLICT (dedup_key) DO NOTHING "
                    "RETURNING id",
                    (key,),
                )
                claimed = cr.fetchone() is not None
                # cursor commits on context-manager exit
            if not claimed:
                _logger.info(
                    "[htf-discuss] outbound send suppressed — duplicate "
                    "claim for channel=%s (within %ss window)",
                    channel_id, _DEDUP_WINDOW_SECONDS,
                )
            return claimed
        except Exception:  # noqa: BLE001 — fail-open
            _logger.exception(
                "[htf-discuss] dedup claim errored; allowing send "
                "(fail-open) for channel=%s", channel_id,
            )
            return True

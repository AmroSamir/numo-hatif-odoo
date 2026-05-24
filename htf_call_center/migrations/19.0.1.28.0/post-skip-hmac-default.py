"""Migration 19.0.1.28.0 — flip dev_mode_skip_hmac default to True.

Policy change. As of this version the HMAC kill switch defaults to ON
because Hatif's live webhook deliveries do NOT include the
X-Voxa-Signature header (see docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md
— filed 2026-05-19, no answer yet from Hatif). With the gate OFF every
inbound call / WhatsApp event is rejected and the integration looks
broken end-to-end.

Existing installs that never touched the flag have the old default
(``False``) stored in ``ir_config_parameter`` from the first time an
admin opened Settings → Hatif. This migration upgrades them to ``True``
on the version bump so production receives webhooks out of the box.

Admins should flip it back OFF in Settings → Hatif → Debug the moment
Hatif enables signing AND the per-channel Webhook Secrets are
configured. The view in this version surfaces both controls side by
side and the help text explains the trade-off.

Idempotent. Re-running is a no-op.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value)
        VALUES ('htf_call_center.dev_mode_skip_hmac', 'True')
        ON CONFLICT (key) DO UPDATE SET value = 'True'
        """
    )
    _logger.info(
        "[htf migration 19.0.1.28.0] htf_call_center.dev_mode_skip_hmac "
        "set to True (Hatif still not signing webhooks — see "
        "docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md)"
    )

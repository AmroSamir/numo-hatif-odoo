"""Migration 19.0.1.35.0 — default the Discuss-first WhatsApp UX to ON.

Per ADR 2026-05-24: v35 introduces the ``whatsapp_button_opens_discuss``
toggle that re-routes WhatsApp buttons through the per-partner Discuss
popup (with a disabled composer + Send Template button when Meta's 24h
window is closed). The toggle defaults True on fresh installs.

Existing installs upgrading from <=v34 also need this set to True so
the new UX is the default behaviour out of the box. Option (a) from
the rollout discussion: we leave the four mirror sub-flags
(``discuss_mirror_enabled`` / ``_inbound`` / ``_calls`` /
``discuss_outbound_route`` / ``discuss_ui_override``) UNTOUCHED so an
admin who deliberately turned them OFF in the past keeps that
preference recoverable — toggling the new flag back OFF restores it.

Runtime overrider lives in ``htf.config.discuss_mirror_active``: when
``whatsapp_button_opens_discuss`` is True it short-circuits the
sub-flag check and returns True.

Idempotent. Re-running is a no-op.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value)
        VALUES ('htf_call_center.whatsapp_button_opens_discuss', 'True')
        ON CONFLICT (key) DO UPDATE SET value = 'True'
        """
    )
    _logger.info(
        "[htf migration 19.0.1.35.0] whatsapp_button_opens_discuss set "
        "to True — Discuss-first WA UX is now the workspace default. "
        "Admins can toggle it OFF in Settings → Hatif → WhatsApp UX "
        "if they prefer the classic wizard."
    )

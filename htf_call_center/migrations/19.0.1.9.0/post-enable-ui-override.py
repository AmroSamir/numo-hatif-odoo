"""Migration 19.0.1.9.0 — auto-enable the P7.8 OWL ChatWindow override.

P7.8 ships the JS patch that hides native voice/video icons on Hatif
channels and registers the teal "Call via Hatif" header action. The
patch is gated by the ``discuss_ui_override`` config flag — without it,
``discuss.channel._to_store_defaults`` skips pushing
``x_htf_partner_id`` / ``x_htf_last_conversation_id`` to the OWL store,
so the patch sees ``undefined`` everywhere and the native UI keeps
running.

On UPGRADE we flip the flag ON so the deploy is the one-step ship the
user asked for. On a FRESH INSTALL (``version`` is empty / falsy) we
do NOT touch the flag — new sites stay opted out of the OWL surface
until an admin explicitly enables it.

L2 revert: flip the flag back to ``False`` in Settings → Technical →
Parameters (``htf_call_center.discuss_ui_override``). No restart
required — ``_to_store_defaults`` reads the flag on every fetch.
"""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_FLAG_KEY = 'htf_call_center.discuss_ui_override'


def migrate(cr, version):
    if not version:
        # Fresh install — keep the flag at its declared default (False)
        # so new sites stay behaviour-neutral until opted in.
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        param = env['ir.config_parameter'].sudo()
        current = param.get_param(_FLAG_KEY, 'False')
        if current == 'True':
            _logger.info(
                "[htf-p7.8] %s already True — leaving as-is", _FLAG_KEY,
            )
            return
        param.set_param(_FLAG_KEY, 'True')
        _logger.info(
            "[htf-p7.8] enabled %s (was %r) — OWL ChatWindow override now "
            "live. Toggle OFF in Settings → Technical → Parameters to revert.",
            _FLAG_KEY, current,
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-p7.8] could not enable %s — non-fatal", _FLAG_KEY)

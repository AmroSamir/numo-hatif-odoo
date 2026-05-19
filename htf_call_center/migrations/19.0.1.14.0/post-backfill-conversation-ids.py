"""Migration 19.0.1.14.0 — backfill ``res.partner.x_htf_last_conversation_id``.

Why this exists: ``services/discuss_mirror.py:_stamp_conversation_metadata``
writes the partner's latest conversationId on every Hatif webhook, but
only for events that arrive AFTER the discuss mirror was enabled. Any
customer who had Hatif conversations before that point has a NULL
``x_htf_last_conversation_id`` — which means the ``htf_phone`` widget
falls back to ``?phone=<E.164>`` instead of the auto-opening
``?conversationId=<uuid>`` deep-link.

This migration walks every partner with a non-empty phone and an
empty ``x_htf_last_conversation_id``, asks Hatif (via
``services.conversations.lookup_latest_conversation_id``) for the
most recent conversation across all active channels, and stores it.

Behaviour rules:
- **Idempotent**: skips partners that already have the field set,
  so re-runs are cheap (do the work only for newly-eligible rows).
- **Bounded**: respects an ``HTF_BACKFILL_LIMIT`` env var so an
  operator can test the migration against a small subset before
  letting it loose on the full partner table. Unset = no limit.
- **Rate-friendly**: a 50ms sleep between API calls, which keeps a
  10k-partner backfill under 10 min while staying well within
  typical Hatif rate limits. The underlying http_client already
  honours ``Retry-After`` on 429.
- **Never fatal**: per-partner errors are swallowed + logged so one
  bad row doesn't abort the whole batch. The migration writes in
  batches of 50 to avoid holding a giant transaction open.
- **Gated**: if ``discuss_mirror_enabled`` is OFF or the Hatif http
  client can't authenticate (no client_id/secret yet), the migration
  logs a notice and exits without touching anything — the deploy
  is still safe.

To re-run manually after the fact (e.g. you turned on
``discuss_mirror_enabled`` after the deploy and now want to fill
historical partners): bump the manifest patch version and re-deploy,
or call the helper directly from ``odoo shell``::

    from odoo.addons.htf_call_center.migrations._helper import backfill_now
    backfill_now(env)
"""

import logging
import os
import time

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_SLEEP_BETWEEN_LOOKUPS_S = 0.05    # 50ms — gentle on Hatif's rate limit
_COMMIT_BATCH = 50                  # write + commit every N updates
_LOG_PROGRESS_EVERY = 100           # info-log every N partners scanned


def migrate(cr, version):
    if not version:
        # Fresh install — no partners to backfill yet.
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _run(env)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-backfill-1.14] migration failed — non-fatal")


def _run(env):
    cfg = env['htf.config']

    # Refuse to fire when the mirror is disabled — the field this
    # populates is only useful when the OWL surface and lead-form
    # widgets consume it, which all require discuss_mirror_active().
    if not cfg.discuss_mirror_active():
        _logger.info(
            "[htf-backfill-1.14] discuss_mirror_enabled=False, "
            "skipping conversationId backfill (the field is unused "
            "until the mirror flag is turned on)."
        )
        return

    # Refuse to fire when Hatif credentials aren't configured yet —
    # the http_client would raise on every call and we'd churn
    # through the partner list logging exceptions for nothing.
    try:
        env['htf.config'].get_service('auth').get_token()
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "[htf-backfill-1.14] cannot acquire Hatif token (%s); "
            "skipping backfill. Run the migration again after Hatif "
            "credentials are configured.", exc,
        )
        return

    from odoo.addons.htf_call_center.services.conversations import (
        lookup_latest_conversation_id,
    )

    limit_env = (os.environ.get('HTF_BACKFILL_LIMIT') or '').strip()
    limit = int(limit_env) if limit_env.isdigit() else 0

    Partner = env['res.partner'].sudo()
    domain = [
        ('phone', '!=', False),
        ('phone', '!=', ''),
        '|',
        ('x_htf_last_conversation_id', '=', False),
        ('x_htf_last_conversation_id', '=', ''),
    ]
    partners = Partner.search(domain, limit=limit or None)
    total = len(partners)
    _logger.info(
        "[htf-backfill-1.14] starting — %d partner(s) eligible "
        "(limit=%s)", total, limit or 'unbounded',
    )

    filled = 0
    misses = 0
    errors = 0
    pending_updates: list[tuple[int, str]] = []

    def _flush():
        nonlocal pending_updates
        for pid, conv_id in pending_updates:
            try:
                Partner.browse(pid).write({'x_htf_last_conversation_id': conv_id})
            except Exception:  # noqa: BLE001
                _logger.exception("[htf-backfill-1.14] write failed for partner=%s", pid)
        env.cr.commit()
        pending_updates = []

    for index, partner in enumerate(partners, start=1):
        if index % _LOG_PROGRESS_EVERY == 0:
            _logger.info(
                "[htf-backfill-1.14] progress %d/%d — filled=%d misses=%d errors=%d",
                index, total, filled, misses, errors,
            )

        try:
            conv_id = lookup_latest_conversation_id(env, partner.phone)
        except Exception:  # noqa: BLE001 — service swallows but be paranoid
            errors += 1
            _logger.exception(
                "[htf-backfill-1.14] lookup raised for partner=%s phone=%s",
                partner.id, partner.phone,
            )
            conv_id = None

        if conv_id:
            pending_updates.append((partner.id, conv_id))
            filled += 1
        else:
            misses += 1

        if len(pending_updates) >= _COMMIT_BATCH:
            _flush()

        time.sleep(_SLEEP_BETWEEN_LOOKUPS_S)

    if pending_updates:
        _flush()

    _logger.info(
        "[htf-backfill-1.14] done — scanned=%d filled=%d misses=%d errors=%d",
        total, filled, misses, errors,
    )

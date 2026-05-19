"""Migration 19.0.1.7.0 — re-render every Discuss mirror bubble in
the user's primary language with a fortified translation reload.

Why this exists when 19.0.1.6.0 already had a re-render migration:
the 19.0.1.6.0 script worked locally but was observed in production
(erp.amro.pro / db `numo`) leaving call bubbles in English even after
the ar.po had loaded. Two suspected causes:

1. Production was already at 19.0.1.6.0 when the migration directory
   was added, so the migration framework never triggered it.
2. The `code_translations` LRU cache may have been primed earlier in
   the same process (before the new ar.po landed), so `_('…')` calls
   inside the migration returned the English source string.

This script:
- Forces the code-translations cache to be re-read for the active
  Arabic language.
- Walks every htf-* mirror message and re-renders its body via the
  current renderer under `lang=ar_001` (or whichever ar* lang is
  active on the DB).
- Is idempotent: re-runs produce the same body and no visible change.
"""

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


_HTF_MSG_RE = re.compile(r'^<htf-msg-(\d+)@htf_call_center>$')
_HTF_CALL_RE = re.compile(r'^<htf-call-(\d+)@htf_call_center>$')


def _pick_render_lang(env):
    arabic_lang = env['res.lang'].sudo().with_context(active_test=False).search([
        ('code', '=like', 'ar%'),
        ('active', '=', True),
    ], limit=1)
    return arabic_lang.code if arabic_lang else 'en_US'


def _force_reload_code_translations(lang):
    """Force a fresh read of the htf_call_center ar.po into the lru-cached
    code_translations dict. Without this, `_()` inside this migration
    may return the English source string when the cache was warmed
    BEFORE the new ar.po was loaded."""
    try:
        from odoo.tools.translate import code_translations
    except ImportError:
        return
    # Clear the lru_cache so the next get_python_translations call
    # re-reads the .po file from disk.
    for attr in ('get_python_translations', 'get_web_translations'):
        fn = getattr(code_translations, attr, None)
        if fn and hasattr(fn, 'cache_clear'):
            try:
                fn.cache_clear()
            except Exception:  # noqa: BLE001
                pass
    # Prime the cache with a real call so failures surface in the log
    # instead of at first user request.
    try:
        cnt = len(code_translations.get_python_translations('htf_call_center', lang))
        _logger.info(
            "[htf-relocalize-1.7] reloaded code translations for lang=%s -> %d entries",
            lang, cnt,
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-relocalize-1.7] could not re-prime code_translations cache")


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _run(env)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-relocalize-1.7] migration failed — non-fatal")


def _run(env):
    from odoo.addons.htf_call_center.services import discuss_mirror

    lang = _pick_render_lang(env)
    _force_reload_code_translations(lang)
    _logger.info("[htf-relocalize-1.7] rendering bubbles under lang=%s", lang)
    env = env(context=dict(env.context, lang=lang))

    msgs = env['mail.message'].sudo().search([
        ('model', '=', 'discuss.channel'),
        ('message_id', '=like', '<htf-%@htf_call_center>'),
    ])
    _logger.info("[htf-relocalize-1.7] scanning %d mirror messages", len(msgs))

    rewrites = 0
    errors = 0
    for m in msgs:
        try:
            ref_id = m.message_id or ''
            new_body = None
            call_m = _HTF_CALL_RE.match(ref_id)
            msg_m = _HTF_MSG_RE.match(ref_id)
            if call_m:
                call = env['htf.call'].sudo().browse(int(call_m.group(1))).exists()
                if call:
                    new_body = str(discuss_mirror._render_call_body(call))
            elif msg_m:
                wa = env['htf.message'].sudo().browse(int(msg_m.group(1))).exists()
                if wa:
                    direction = 'inbound' if (wa.direction or '').lower() == 'inbound' else 'outbound'
                    new_body = str(discuss_mirror._render_wa_body(wa, direction=direction))
            if new_body and new_body != (m.body or ''):
                m.write({'body': new_body})
                rewrites += 1
        except Exception:  # noqa: BLE001
            errors += 1
            _logger.exception(
                "[htf-relocalize-1.7] failed on mail.message=%s message_id=%s",
                m.id, m.message_id,
            )
    _logger.info(
        "[htf-relocalize-1.7] done — lang=%s rewrites=%d errors=%d",
        lang, rewrites, errors,
    )

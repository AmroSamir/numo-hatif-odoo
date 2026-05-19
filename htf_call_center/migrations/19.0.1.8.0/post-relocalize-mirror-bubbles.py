"""Migration 19.0.1.8.0 — re-render mirror bubbles after icon swap
+ Arabic "Missed call" wording change.

Two source-of-truth changes since 19.0.1.7.0:

- Bubble call icon switched from the 📞 emoji to Font Awesome
  ``<i class="fa fa-phone" style="color:#02c7b5"></i>`` so the icon
  picks up the Hatif teal brand colour.
- Arabic translation of "Missed call" updated from "اتصال فائت" to
  "مكالمة واردة (لم يتم الرد)" (matching the other ``Call (no agent
  pickup)`` wording per user request).

Re-runs ``_render_call_body`` / ``_render_wa_body`` under the active
Arabic lang so existing bubbles pick up both changes at once. Identical
shape to the 19.0.1.7.0 migration, just bound to a new version tag so
the framework actually fires it on prod DBs already at 19.0.1.7.0.
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
    try:
        from odoo.tools.translate import code_translations
    except ImportError:
        return
    for attr in ('get_python_translations', 'get_web_translations'):
        fn = getattr(code_translations, attr, None)
        if fn and hasattr(fn, 'cache_clear'):
            try:
                fn.cache_clear()
            except Exception:  # noqa: BLE001
                pass
    try:
        cnt = len(code_translations.get_python_translations('htf_call_center', lang))
        _logger.info(
            "[htf-relocalize-1.8] reloaded code translations for lang=%s -> %d entries",
            lang, cnt,
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-relocalize-1.8] could not re-prime code_translations cache")


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _run(env)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-relocalize-1.8] migration failed — non-fatal")


def _run(env):
    from odoo.addons.htf_call_center.services import discuss_mirror

    lang = _pick_render_lang(env)
    _force_reload_code_translations(lang)
    _logger.info("[htf-relocalize-1.8] rendering bubbles under lang=%s", lang)
    env = env(context=dict(env.context, lang=lang))

    msgs = env['mail.message'].sudo().search([
        ('model', '=', 'discuss.channel'),
        ('message_id', '=like', '<htf-%@htf_call_center>'),
    ])
    _logger.info("[htf-relocalize-1.8] scanning %d mirror messages", len(msgs))

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
                "[htf-relocalize-1.8] failed on mail.message=%s message_id=%s",
                m.id, m.message_id,
            )
    _logger.info(
        "[htf-relocalize-1.8] done — lang=%s rewrites=%d errors=%d",
        lang, rewrites, errors,
    )

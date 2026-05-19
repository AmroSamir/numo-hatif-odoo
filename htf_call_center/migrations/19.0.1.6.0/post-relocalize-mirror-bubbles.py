"""Migration 19.0.1.6.0 — re-render every mirror bubble using the
current renderer + the system's primary user language.

Why: bubbles are written ONCE to the DB; the text is fixed at write
time. When we shipped 19.0.1.5.0 (English source + i18n/ar.po), only
NEW bubbles benefited from the new wording. This migration walks every
existing mirror mail.message and re-renders its body with the current
_render_call_body / _render_wa_body, executed under the language that
gives the desired output (Arabic on Numo, English elsewhere).

Language detection priority:
  1. Active language with code starting 'ar' (Numo's case -> ar_001)
     so the curated Arabic wording from ar.po lands
  2. Otherwise fall back to en_US

Idempotent — re-runs simply produce the same body and trigger no
visible change.
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


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _run(env)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-relocalize] migration failed — non-fatal")


def _run(env):
    from odoo.addons.htf_call_center.services import discuss_mirror

    lang = _pick_render_lang(env)
    _logger.info("[htf-relocalize] rendering bubbles under lang=%s", lang)
    env = env(context=dict(env.context, lang=lang))

    msgs = env['mail.message'].sudo().search([
        ('model', '=', 'discuss.channel'),
        ('message_id', '=like', '<htf-%@htf_call_center>'),
    ])
    _logger.info("[htf-relocalize] scanning %d mirror messages", len(msgs))

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
                "[htf-relocalize] failed on mail.message=%s message_id=%s",
                m.id, m.message_id,
            )
    _logger.info(
        "[htf-relocalize] done — lang=%s rewrites=%d errors=%d",
        lang, rewrites, errors,
    )

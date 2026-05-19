"""Migration 19.0.1.3.0 — retranslate existing mirror bubbles to Arabic
and reattribute the "Public user" duplicates left over from the
voice-recording burst bug.

Three things happen per Hatif-linked discuss.channel mail.message:

  1. If the body is still in English (older mirror writes from before
     the bfbc3d4 Arabic translation), regenerate it using the current
     _render_call_body / _render_wa_body — produces Arabic labels +
     strips leading '###' from any call summary.

  2. If the author_id is the public-user partner (the "Public user"
     bubbles caused by the voice-recording burst before the a51edd3
     dedup-guard landed), reattribute:
        - for call bubbles  -> OdooBot (system actor) or the customer
        - for WA inbound    -> the customer's partner
        - for WA outbound   -> the sender_user_id.partner_id if known,
                               else OdooBot

The migration is idempotent — re-runs detect already-translated bodies
and skip them.
"""

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


_HTF_MSG_RE = re.compile(r'^<htf-msg-(\d+)@htf_call_center>$')
_HTF_CALL_RE = re.compile(r'^<htf-call-(\d+)@htf_call_center>$')


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        _run(env)
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-retranslate] migration failed — non-fatal")


def _run(env):
    from odoo.addons.htf_call_center.services import discuss_mirror

    public_partner = env.ref('base.public_partner', raise_if_not_found=False)
    public_pid = public_partner.id if public_partner else False
    bot_partner = env.ref('base.partner_root', raise_if_not_found=False)
    bot_pid = bot_partner.id if bot_partner else False

    msgs = env['mail.message'].sudo().search([
        ('model', '=', 'discuss.channel'),
        ('message_id', '=like', '<htf-%@htf_call_center>'),
    ])
    _logger.info("[htf-retranslate] scanning %d mirror messages", len(msgs))

    body_rewrites = 0
    author_rewrites = 0
    errors = 0

    for m in msgs:
        try:
            ref_id = m.message_id or ''
            updates = {}

            call_m = _HTF_CALL_RE.match(ref_id)
            msg_m = _HTF_MSG_RE.match(ref_id)
            if call_m:
                call_id = int(call_m.group(1))
                call = env['htf.call'].sudo().browse(call_id).exists()
                if call:
                    new_body = str(discuss_mirror._render_call_body(call))
                    if new_body and new_body != (m.body or ''):
                        updates['body'] = new_body
            elif msg_m:
                wa_id = int(msg_m.group(1))
                wa = env['htf.message'].sudo().browse(wa_id).exists()
                if wa:
                    direction = 'inbound' if (wa.direction or '').lower() == 'inbound' else 'outbound'
                    new_body = str(discuss_mirror._render_wa_body(wa, direction=direction))
                    if new_body and new_body != (m.body or ''):
                        updates['body'] = new_body

            if public_pid and m.author_id and m.author_id.id == public_pid:
                new_author_id = None
                if call_m:
                    call = env['htf.call'].sudo().browse(int(call_m.group(1))).exists()
                    if call:
                        if (call.direction or '').lower() == 'outbound' and call.handler_user_id and call.handler_user_id.partner_id:
                            new_author_id = call.handler_user_id.partner_id.id
                        elif call.partner_id:
                            new_author_id = call.partner_id.id
                        else:
                            new_author_id = bot_pid
                elif msg_m:
                    wa = env['htf.message'].sudo().browse(int(msg_m.group(1))).exists()
                    if wa:
                        if (wa.direction or '').lower() == 'inbound' and wa.partner_id:
                            new_author_id = wa.partner_id.id
                        elif wa.sender_user_id and wa.sender_user_id.partner_id:
                            new_author_id = wa.sender_user_id.partner_id.id
                        else:
                            new_author_id = bot_pid
                if new_author_id and new_author_id != public_pid:
                    updates['author_id'] = new_author_id

            if updates:
                m.write(updates)
                if 'body' in updates:
                    body_rewrites += 1
                if 'author_id' in updates:
                    author_rewrites += 1
        except Exception:  # noqa: BLE001
            errors += 1
            _logger.exception(
                "[htf-retranslate] failed on mail.message=%s message_id=%s",
                m.id, m.message_id,
            )

    _logger.info(
        "[htf-retranslate] done — bodies_rewritten=%d authors_reattributed=%d errors=%d",
        body_rewrites, author_rewrites, errors,
    )

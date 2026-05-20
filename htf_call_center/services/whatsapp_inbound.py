"""WhatsApp webhook dispatcher (P2 T2.3 + T2.5).

Two flows hit the same endpoint:

- **Inbound** (``direction == 'Inbound'``) — a new message from the
  customer. Persist ``htf.message``, find-or-create the partner, post a
  chatter bubble, update the 24h-window timestamp, run the opt-out
  detector, fire ``htf.wa.inbound``.

- **Outbound STATUS** (``direction == 'Outbound'``) — Hatif delivering
  a state update (Sent → Delivered → Read → Failed) for a message that
  was either sent by Numo Odoo (P3 — has a pre-existing row) or by an
  agent directly on the Hatif portal (no pre-existing row → create one).
  Either way: update ``state`` + timestamps, refresh the chatter bubble
  in place, fire ``htf.wa.status``.

Error budget: ``process()`` raises on hard failures so the controller
returns 500 and Hatif retries (per Q-22, 5 attempts / 62 min window).
Soft failures (e.g. partner enrichment fetch timeout) degrade
gracefully — the message persists, just with a placeholder partner.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from odoo.tools import safe_eval  # noqa: F401 — keep import bag tidy

from ..signals import htf_signals
from . import chatter, discuss_mirror, dnc_listener

_logger = logging.getLogger(__name__)


# -------------------------------------------------------------- #
# Public entry point                                             #
# -------------------------------------------------------------- #

def process(env, payload: dict) -> str:
    """Top-level dispatcher.

    Returns a one-line audit string for ``htf.webhook.event.note``.
    """
    direction_raw = (payload.get('direction') or '').strip()
    direction = direction_raw.lower()
    if direction not in ('inbound', 'outbound'):
        # Unknown direction — record, do nothing, return 200 to stop
        # retries. (Hatif may add new direction values in the future.)
        _logger.warning("[htf-wa] unknown direction=%r — skipping",
                        direction_raw)
        return f'skip: unknown direction={direction_raw}'

    if direction == 'inbound':
        return _process_inbound(env, payload)
    return _process_outbound_status(env, payload)


# -------------------------------------------------------------- #
# Inbound (T2.3)                                                 #
# -------------------------------------------------------------- #

def _process_inbound(env, payload: dict) -> str:
    channel = _resolve_channel(env, payload.get('channelId'))
    partner = _resolve_partner(env, payload.get('contactId'))

    message_type = _normalize_message_type(payload.get('messageType'))
    state = _normalize_status(payload.get('status'))
    created_at = _parse_dt(payload.get('creationTime'))
    body = payload.get('body') or ''

    is_opt_out = (
        message_type == 'text'
        and dnc_listener.is_opt_out(body, dnc_listener.load_keywords(env))
    )

    Msg = env['htf.message'].sudo()

    # If Hatif's at-least-once delivery beat the dispatcher to a duplicate
    # creation (e.g. clock skew between idempotency lock + ORM), the
    # UNIQUE constraint on htf_message_id catches it. We surface that as
    # an early return so the caller (controller) sees a deterministic
    # "OK (existing inbound)" outcome.
    msg_id = payload.get('messageId') or ''
    existing = Msg.find_by_message_id(msg_id) if msg_id else Msg.browse()
    if existing:
        _logger.info("[htf-wa] inbound msg_id=%s already persisted as id=%s",
                      msg_id[:14] + '…', existing.id)
        return f'inbound:duplicate id={existing.id}'

    new_msg = Msg.create({
        'direction': 'inbound',
        'message_type': message_type or 'text',
        'state': state or 'delivered',
        'body': body,
        'media_url': payload.get('mediaUrl') or False,
        'mime_type': payload.get('mimeType') or False,
        'latitude': payload.get('latitude') or 0.0,
        'longitude': payload.get('longitude') or 0.0,
        'htf_message_id': msg_id or False,
        'conversation_uuid': payload.get('conversationId') or False,
        'contact_uuid': payload.get('contactId') or False,
        'channel_id': channel.id if channel else False,
        'partner_id': partner.id if partner else False,
        'is_billable': bool(payload.get('isBillable', False)),
        'error_code': payload.get('errorCode') or 0,
        'error_reason': payload.get('errorReason') or False,
        'created_at': created_at,
        'is_opt_out': is_opt_out,
        'raw_payload': json.dumps(payload, ensure_ascii=False, default=str),
    })

    # Open / refresh the 24h Meta window on the partner.
    if partner:
        partner.sudo().write({'x_htf_last_inbound_at': created_at})
        # Best-effort: post to partner chatter.
        try:
            chatter.post_inbound_wa(partner, new_msg)
        except Exception:  # noqa: BLE001 — chatter failure is non-fatal
            _logger.exception(
                "[htf-wa] chatter post failed for partner=%s msg_id=%s",
                partner.id, new_msg.id,
            )
        # P7 — Mirror into the partner's Discuss channel. No-op when
        # htf_call_center.discuss_mirror_enabled is off. Best-effort —
        # discuss_mirror.mirror_inbound_wa swallows its own exceptions.
        discuss_mirror.mirror_inbound_wa(env, partner, new_msg, payload)

    # Fire the signal so the bridge can react (auto-create lead, etc.).
    _fire_signal('htf.wa.inbound', {
        'message_id': new_msg.id,
        'message_type': new_msg.message_type,
        'partner_id': partner.id if partner else None,
        'channel_id': channel.id if channel else None,
        'is_opt_out_keyword': is_opt_out,
        'raw': payload,
    })

    if is_opt_out:
        _fire_signal('htf.wa.optout', {
            'message_id': new_msg.id,
            'partner_id': partner.id if partner else None,
            'channel_id': channel.id if channel else None,
            'body': body,
        })

    return f'inbound:created id={new_msg.id} type={new_msg.message_type} optout={is_opt_out}'


# -------------------------------------------------------------- #
# Outbound STATUS (T2.5)                                         #
# -------------------------------------------------------------- #

def _process_outbound_status(env, payload: dict) -> str:
    Msg = env['htf.message'].sudo()
    msg_id = payload.get('messageId') or ''
    conv_event_id = payload.get('conversationEventId') or ''
    existing = Msg.find_by_message_id(msg_id) if msg_id else Msg.browse()
    # Fallback dedup: the POST response to our wizard-driven send
    # populates ``conversation_event_id`` on the htf.message row but
    # may not always include ``messageId`` immediately. When the
    # status webhook arrives we still want to UPDATE the existing
    # row (preserving its ``sender_user_id`` set by our wizard) —
    # NOT create a parallel row that loses the agent's identity.
    # The Discuss mirror's outbound author resolver depends on
    # ``sender_user_id`` being set; without this fallback the bubble
    # falls through to OdooBot or the customer (the visual bug
    # reported in the screenshot).
    if not existing and conv_event_id:
        existing = Msg.search([
            ('conversation_event_id', '=', conv_event_id),
            ('direction', '=', 'outbound'),
        ], limit=1)
        if existing and msg_id and not existing.htf_message_id:
            # Stamp the messageId we now have so subsequent webhook
            # status updates (delivered / read / failed) find us via
            # the fast index path instead of needing this fallback.
            try:
                existing.write({'htf_message_id': msg_id})
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-wa] could not stamp htf_message_id=%s on existing id=%s",
                    msg_id, existing.id,
                )

    new_state = _normalize_status(payload.get('status')) or 'sent'
    ts = _parse_dt(payload.get('creationTime'))

    if not existing:
        # An outbound message Numo agents sent directly on the Hatif portal
        # (not via Odoo P3 send). Persist it so chatter still has a record.
        channel = _resolve_channel(env, payload.get('channelId'))
        partner = _resolve_partner(env, payload.get('contactId'))
        sender = _resolve_sender(env, payload.get('senderUserId'))
        new_msg = Msg.create({
            'direction': 'outbound',
            'message_type': _normalize_message_type(payload.get('messageType')) or 'text',
            'state': new_state,
            'body': payload.get('body') or '',
            'media_url': payload.get('mediaUrl') or False,
            'mime_type': payload.get('mimeType') or False,
            'latitude': payload.get('latitude') or 0.0,
            'longitude': payload.get('longitude') or 0.0,
            'htf_message_id': msg_id or False,
            'conversation_uuid': payload.get('conversationId') or False,
            'contact_uuid': payload.get('contactId') or False,
            'channel_id': channel.id if channel else False,
            'partner_id': partner.id if partner else False,
            'sender_user_id': sender.id if sender else False,
            'is_billable': bool(payload.get('isBillable', False)),
            'error_code': payload.get('errorCode') or 0,
            'error_reason': payload.get('errorReason') or False,
            'created_at': ts,
            'delivered_at': ts if new_state in ('delivered', 'read') else False,
            'read_at': ts if new_state == 'read' else False,
            'raw_payload': json.dumps(payload, ensure_ascii=False, default=str),
        })
        if partner:
            try:
                chatter.post_outbound_wa(partner, new_msg)
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "[htf-wa] outbound chatter post failed for partner=%s msg_id=%s",
                    partner.id, new_msg.id,
                )
            # P7 — Mirror to Discuss. No-op when flags off.
            discuss_mirror.mirror_outbound_wa_from_hatif(env, partner, new_msg, payload)
        _fire_signal('htf.wa.outbound', {
            'message_id': new_msg.id,
            'partner_id': partner.id if partner else None,
            'channel_id': channel.id if channel else None,
            'source': 'hatif_portal',
            'raw': payload,
        })
        return f'outbound:created id={new_msg.id} state={new_state}'

    # Existing row → STATUS update.
    old_state = existing.state
    vals = {
        'state': new_state,
        'error_code': payload.get('errorCode') or existing.error_code or 0,
        'error_reason': payload.get('errorReason') or existing.error_reason or False,
        'raw_payload': json.dumps(payload, ensure_ascii=False, default=str),
    }
    if new_state == 'delivered' and not existing.delivered_at:
        vals['delivered_at'] = ts
    if new_state == 'read':
        if not existing.delivered_at:
            vals['delivered_at'] = ts
        if not existing.read_at:
            vals['read_at'] = ts
    existing.write(vals)

    # Refresh chatter bubble in place (no duplicate post).
    try:
        chatter.refresh_status(existing)
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-wa] refresh_status failed for htf.message id=%s", existing.id,
        )

    _fire_signal('htf.wa.status', {
        'message_id': existing.id,
        'old_state': old_state,
        'new_state': new_state,
        'partner_id': existing.partner_id.id or None,
    })
    return f'outbound:status id={existing.id} {old_state}->{new_state}'


# -------------------------------------------------------------- #
# Resolvers                                                      #
# -------------------------------------------------------------- #

def _resolve_channel(env, hatif_channel_id):
    if not hatif_channel_id:
        return env['htf.channel'].browse()
    return env['htf.channel'].sudo().search(
        [('htf_channel_id', '=', hatif_channel_id)], limit=1,
    )


def _resolve_partner(env, hatif_contact_id):
    if not hatif_contact_id:
        return env['res.partner'].browse()
    link = env['htf.contact.link'].sudo().search(
        [('htf_contact_id', '=', hatif_contact_id)], limit=1,
    )
    if link and link.partner_id:
        return link.partner_id

    # First time we see this contact — create a placeholder partner +
    # a contact link. The contacts-poll cron (Q-10 ANSWERED: polling
    # required) will backfill name + phone on its next pass.
    # The Hatif logo on partner.image_1920 (migration 19.0.1.4.0)
    # already brands the row visually, so the name is just the
    # contactId-short.
    short = (hatif_contact_id or '')[:8] + '…' if hatif_contact_id else 'unknown'
    partner = env['res.partner'].sudo().create({
        'name': short,
        'comment': (
            f'[htf] Auto-created from inbound WA webhook. '
            f'contactId={hatif_contact_id}. '
            f'Name + phone backfilled by contacts-poll cron.'
        ),
    })
    env['htf.contact.link'].sudo().create({
        'partner_id': partner.id,
        'htf_contact_id': hatif_contact_id,
        'sync_state': 'pending',
    })
    _logger.info(
        "[htf-wa] placeholder partner id=%s created for contactId=%s",
        partner.id, hatif_contact_id,
    )
    return partner


def _resolve_sender(env, hatif_user_id):
    if not hatif_user_id:
        return env['res.users'].browse()
    return env['res.users'].sudo().search(
        [('x_htf_user_id', '=', hatif_user_id)], limit=1,
    )


# -------------------------------------------------------------- #
# Normalisers                                                    #
# -------------------------------------------------------------- #

_MESSAGE_TYPES = {
    'text', 'image', 'video', 'audio', 'document',
    'location', 'contact', 'sticker', 'template', 'interactive',
}


def _normalize_message_type(value) -> str:
    if not value:
        return ''
    lowered = value.strip().lower()
    return lowered if lowered in _MESSAGE_TYPES else ''


def _normalize_status(value) -> str:
    if not value:
        return ''
    lowered = value.strip().lower()
    return lowered if lowered in ('pending', 'sent', 'delivered', 'read', 'failed') else ''


def _parse_dt(value):
    """Tolerate ISO8601 with trailing Z or offset; fall back to now()."""
    if not value:
        from odoo.fields import Datetime as Dt
        return Dt.now()
    try:
        s = value.replace('Z', '+00:00') if isinstance(value, str) else value
        dt = datetime.fromisoformat(s)
        # Odoo stores naive UTC datetimes.
        if dt.tzinfo is not None:
            from datetime import timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        from odoo.fields import Datetime as Dt
        return Dt.now()


# -------------------------------------------------------------- #
# Signal helper                                                  #
# -------------------------------------------------------------- #

def _fire_signal(name: str, payload: dict) -> None:
    try:
        htf_signals.fire(name, payload)
    except Exception:  # noqa: BLE001 — already raised once below for visibility
        _logger.exception("[htf-wa] signal %s subscriber raised", name)
        raise

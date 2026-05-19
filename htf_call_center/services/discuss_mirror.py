"""P7 — Hatif activity mirror into per-partner discuss.channel.

Module-level functions invoked from the existing webhook dispatchers in
`whatsapp_inbound.py` (P7.2) and `calls.py` (P7.3) after the primary
htf.* row + partner-side-effects (chatter post, x_htf_last_inbound_at,
signal fire) have already been written.

ALL entry points first call `_active(env, sub_flag)` and bail out on
False. With the master flag `discuss_mirror_enabled` off this module is
inert — its functions return immediately without touching discuss.channel
or mail.message. The pre-P7 behavior of the dispatchers is unaffected.

Every mail.message written here is tagged with the
`htf_call_center.mt_htf_mirror` subtype. The P7.4 outbound override
checks for this subtype to avoid re-firing a Hatif send when our own
mirror write triggers `discuss.channel.message_post`.

Style notes:
  - Best-effort: every mirror is wrapped in try/except. A Discuss
    failure NEVER breaks the primary webhook processing — the dispatchers
    have already persisted everything that matters BEFORE calling here.
  - Author mapping (decision #2 partner-as-participant):
      * inbound WA from customer  -> author_id = partner.id
      * outbound WA from agent    -> author_id = sender_user.partner_id
                                     or env.user.partner_id fallback
      * call ended (any direction) -> author_id = pickup_user.partner_id
                                     if known, else partner.id (so the
                                     bubble visually anchors to the
                                     conversation rather than appearing
                                     as a system-from-nowhere)
"""

from __future__ import annotations

import logging
from html import escape

import requests
from markupsafe import Markup

from odoo import _

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- #
# Flag gating                                                      #
# ---------------------------------------------------------------- #

def _active(env, sub_flag: str) -> bool:
    """Master + sub flag check. Returns False on any error so a broken
    config can never accidentally enable the mirror."""
    try:
        return env['htf.config'].discuss_mirror_active(sub_flag)
    except Exception:  # noqa: BLE001 — defensive; never raise from a gate
        _logger.exception("[htf-discuss] flag-check error — fail-closed")
        return False


def _mirror_subtype_id(env):
    """Resolve the htf_call_center.mt_htf_mirror subtype xmlid id.

    Returns False if the data file failed to load (paranoid; should
    never happen after a clean module upgrade). Without this xmlid we
    fall back to message_post default subtype and the outbound override
    will not be able to filter mirror writes — so we LOG LOUD and bail.
    """
    try:
        return env.ref('htf_call_center.mt_htf_mirror', raise_if_not_found=False).id or False
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-discuss] mt_htf_mirror xmlid missing — aborting mirror")
        return False


# ---------------------------------------------------------------- #
# Stable RFC2822-style message_id for idempotency                  #
# ---------------------------------------------------------------- #
# Each mirror write is tagged with a deterministic message_id so the
# backfill script can detect "already mirrored this row" and skip,
# making backfill idempotent.

def _wa_message_id(htf_message) -> str:
    return f'<htf-msg-{htf_message.id}@htf_call_center>'


def _call_message_id(call_row) -> str:
    return f'<htf-call-{call_row.id}@htf_call_center>'


def _already_mirrored(env, channel_id: int, msg_id_sentinel: str) -> bool:
    """Idempotency check — return True if a mail.message with this
    message_id already exists in the channel. Allows safe re-fires of
    the same Hatif webhook (e.g., Hatif's 5-retry policy on 5xx) without
    creating duplicate Discuss bubbles.

    Cheap: mail.message has an index on (model, res_id) AND message_id
    is a small Char with btree index in Odoo 19.
    """
    return bool(
        env['mail.message'].sudo().search_count(
            [
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', channel_id),
                ('message_id', '=', msg_id_sentinel),
            ],
            limit=1,
        )
    )


# ---------------------------------------------------------------- #
# Conversation/channel id stamping                                 #
# ---------------------------------------------------------------- #

def _stamp_conversation_metadata(channel, partner, payload: dict, htf_channel_id=False):
    """Update channel + partner with the latest conversationId + htf channel.

    Cheap, but only writes when the value changed (avoids gratuitous
    write triggering watchers).
    """
    convo_id = payload.get('conversationId') or False
    updates = {}
    if convo_id and channel.x_htf_last_conversation_id != convo_id:
        updates['x_htf_last_conversation_id'] = convo_id
    if htf_channel_id and channel.x_htf_last_htf_channel_id.id != htf_channel_id:
        updates['x_htf_last_htf_channel_id'] = htf_channel_id
    if updates:
        channel.sudo().write(updates)
    if partner and convo_id and partner.x_htf_last_conversation_id != convo_id:
        partner.sudo().write({'x_htf_last_conversation_id': convo_id})


# ---------------------------------------------------------------- #
# WhatsApp inbound mirror                                          #
# ---------------------------------------------------------------- #

def mirror_inbound_wa(env, partner, htf_message, payload: dict) -> None:
    """Post a mail.message in the partner's Hatif channel for an inbound WA.

    Called from services/whatsapp_inbound.py after the htf.message is
    persisted and the chatter is updated. No-op when feature flags off.
    """
    if not partner or not _active(env, 'inbound'):
        return
    subtype = _mirror_subtype_id(env)
    if not subtype:
        return
    try:
        channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        if not channel:
            return
        _stamp_conversation_metadata(channel, partner, payload, htf_message.channel_id.id)
        sentinel = _wa_message_id(htf_message)
        if _already_mirrored(env, channel.id, sentinel):
            return  # idempotent — webhook re-fire
        body = _render_wa_body(htf_message, direction='inbound')
        channel.with_context(
            mail_create_nosubscribe=True,
            htf_mirror_write=True,
        ).message_post(
            body=body,
            author_id=partner.id,
            subtype_id=subtype,
            message_type='comment',
            message_id=sentinel,
        )
    except Exception:  # noqa: BLE001 — never break the webhook
        _logger.exception(
            "[htf-discuss] mirror_inbound_wa failed for partner=%s htf.message=%s",
            partner.id, htf_message.id,
        )


def mirror_outbound_wa_from_hatif(env, partner, htf_message, payload: dict) -> None:
    """Post a mail.message for an outbound WA the agent sent on the Hatif portal.

    Distinct from P7.4 which handles the inverse direction (agent posting
    *in Discuss* fires a Hatif send). Here Hatif sent the message and we
    mirror what happened. Same flag gate (inbound, since this is still
    incoming webhook traffic about the conversation).
    """
    if not partner or not _active(env, 'inbound'):
        return
    subtype = _mirror_subtype_id(env)
    if not subtype:
        return
    try:
        channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        if not channel:
            return
        _stamp_conversation_metadata(channel, partner, payload, htf_message.channel_id.id)
        sentinel = _wa_message_id(htf_message)
        if _already_mirrored(env, channel.id, sentinel):
            return  # idempotent
        body = _render_wa_body(htf_message, direction='outbound')
        # Author: the agent who sent it via Hatif (if mapped), else the
        # current Odoo user's partner.
        author = (
            htf_message.sender_user_id.partner_id
            if htf_message.sender_user_id and htf_message.sender_user_id.partner_id
            else env.user.partner_id
        )
        channel.with_context(
            mail_create_nosubscribe=True,
            htf_mirror_write=True,
        ).message_post(
            body=body,
            author_id=author.id,
            subtype_id=subtype,
            message_type='comment',
            message_id=sentinel,
        )
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-discuss] mirror_outbound_wa_from_hatif failed for partner=%s htf.message=%s",
            partner.id, htf_message.id,
        )


# ---------------------------------------------------------------- #
# Call mirror                                                      #
# ---------------------------------------------------------------- #

# Hard cap on recording-download size. Hatif's MP3s are typically
# 30-700 KB; setting 5 MB is well above any realistic call. Stops a
# pathological response from filling the webhook handler's memory.
_RECORDING_DOWNLOAD_MAX_BYTES = 5 * 1024 * 1024
_RECORDING_DOWNLOAD_TIMEOUT_S = 10


def mirror_call(env, partner, call_row, payload: dict) -> None:
    """Post a single mail.message in the partner's Hatif channel for a call.

    Bubble contents (decision #3 ONE message):
      - HTML body with status icon, duration, who answered, AI summary.
      - When recording_url is present, the MP3 bytes are downloaded
        inline (10s timeout, 5 MB cap) and attached with the Discuss
        voice flag so the attachment renders as a native voice-note
        bubble alongside the body text.

    Author mapping:
      - Inbound call  -> author_id = partner.id (left side, anchored
                         to the customer who initiated)
      - Outbound call -> author_id = handler.partner_id if known,
                         else env.user.partner_id (right side, anchored
                         to the agent who initiated)

    Called from services/calls.py after the htf.call row is persisted
    and the chatter is updated. Best-effort — exceptions are swallowed
    so a Discuss failure NEVER breaks the call webhook.
    """
    if not partner or not _active(env, 'calls'):
        return
    subtype = _mirror_subtype_id(env)
    if not subtype:
        return
    try:
        channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        if not channel:
            return
        _stamp_conversation_metadata(channel, partner, payload, call_row.channel_id.id)
        sentinel = _call_message_id(call_row)
        if _already_mirrored(env, channel.id, sentinel):
            return  # idempotent
        body = _render_call_body(call_row)
        author = _resolve_call_author(env, call_row, partner)
        attachments = _maybe_download_recording(call_row)
        channel.with_context(
            mail_create_nosubscribe=True,
            htf_mirror_write=True,
        ).message_post(
            body=body,
            author_id=author.id if author else False,
            subtype_id=subtype,
            message_type='comment',
            attachments=attachments,
            message_id=sentinel,
        )
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-discuss] mirror_call failed for partner=%s htf.call=%s",
            partner.id, call_row.id,
        )


def _resolve_call_author(env, call_row, partner):
    direction = (call_row.direction or '').lower()
    if direction == 'outbound':
        if call_row.handler_user_id and call_row.handler_user_id.partner_id:
            return call_row.handler_user_id.partner_id
        return env.user.partner_id
    # inbound (or unknown direction) — anchor to the customer
    return partner


def _render_call_body(call_row) -> Markup:
    """Compose the HTML body of the call bubble.

    Returned as `markupsafe.Markup` so Odoo's mail sanitizer recognises
    the markup as pre-sanitised. Without this, Odoo escapes every `<`
    in the body because `message_post(body=...)` expects HTML and falls
    back to text-escape mode for plain str.

    Strings are emitted in Arabic to match Numo's customer-conversation
    locale — Hatif's customer messages are Arabic, the partner names
    are Arabic, and Numo's agents read both. Arabic-first is the
    sensible default; if we ever need English fallback for non-AR
    workspaces we'll swap to a .po-driven gettext path.

    Layout (renders next to the voice-note bubble in Discuss):
      📞 <verb>  ·  <duration>  ·  بدأت <time>
      رد عليه <agent>  (if pickup_kind=human)
      الملخص: <ai summary first 200 chars>  (if present)
    """
    status = (call_row.status or '').lower()
    pickup_kind = (call_row.pickup_kind or '').lower()
    duration = call_row.duration_display or ''
    started = call_row.created_at and call_row.created_at.strftime('%H:%M') or ''
    icon, verb = _call_icon_and_verb(status, pickup_kind)
    parts = [f'<strong>{icon} {escape(verb)}</strong>']
    if duration:
        parts.append(f' · {escape(duration)}')
    if started:
        parts.append(f' · بدأت {escape(started)}')
    head = ''.join(parts)
    extra = []
    if pickup_kind == 'human' and call_row.handler_user_id and call_row.handler_user_id.name:
        extra.append(
            f'<small>رد عليه {escape(call_row.handler_user_id.name)}</small>'
        )
    elif pickup_kind == 'system':
        extra.append(
            f'<small><em>تم الرد بواسطة المجيب الآلي / IVR</em></small>'
        )
    if call_row.summary:
        snippet = call_row.summary[:200] + ('…' if len(call_row.summary) > 200 else '')
        extra.append(
            f'<div><em>الملخص:</em> {escape(snippet)}</div>'
        )
    html = head + ('<br/>' + '<br/>'.join(extra) if extra else '')
    return Markup(html)


def _call_icon_and_verb(status: str, pickup_kind: str) -> tuple[str, str]:
    if status == 'missed' and pickup_kind == 'none':
        return '📞', 'مكالمة فائتة'
    if status == 'missed':
        return '📞', 'مكالمة (لم يرد الموظف)'
    if status in ('answered', 'completed'):
        return '📞', 'انتهت المكالمة'
    if status == 'ringing':
        return '📞', 'جارٍ الاتصال'
    if status == 'failed':
        return '📞', 'فشلت المكالمة'
    return '📞', f'مكالمة — {status or "غير معروف"}'


def _maybe_download_recording(call_row) -> list:
    """Return attachments-tuple-list for message_post, or empty list.

    Returns [(filename, bytes, {'voice': True, 'mimetype': 'audio/mpeg'})]
    when the MP3 downloads within budget. On any failure, returns []
    and logs — the message still posts without the voice bubble.

    Hatif's recording_url is short-lived (apidog notes 401 after a few
    minutes), so the download MUST happen synchronously inside the
    webhook handler. 10-second timeout is the budget.
    """
    url = call_row.recording_url or ''
    if not url:
        return []
    try:
        resp = requests.get(url, timeout=_RECORDING_DOWNLOAD_TIMEOUT_S, stream=True)
        resp.raise_for_status()
        data = b''
        for chunk in resp.iter_content(chunk_size=8192):
            data += chunk
            if len(data) > _RECORDING_DOWNLOAD_MAX_BYTES:
                _logger.warning(
                    "[htf-discuss] recording exceeds %d bytes — abandoning attachment "
                    "for htf.call=%s",
                    _RECORDING_DOWNLOAD_MAX_BYTES, call_row.id,
                )
                return []
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-discuss] recording download failed for htf.call=%s (url=%s)",
            call_row.id, url,
        )
        return []
    filename = f'call-{call_row.htf_call_id or call_row.id}.mp3'
    return [(filename, data, {'voice': True, 'mimetype': 'audio/mpeg'})]


def _render_wa_body(htf_message, direction: str) -> Markup:
    """Render a WA body into the Discuss bubble.

    Returned as `markupsafe.Markup` so HTML survives Odoo's
    message_post sanitiser. Plain-text body (escaped) for text
    messages. Media types get a labelled placeholder in Arabic
    (Numo's customer locale) — media itself is NOT downloaded
    because Hatif's mediaUrl is short-lived.
    """
    msg_type = htf_message.message_type or 'text'
    body = htf_message.body or ''
    if msg_type == 'text':
        return Markup(escape(body).replace('\n', '<br/>'))
    label = {
        'image': '📷 صورة',
        'video': '🎥 فيديو',
        'audio': '🎵 تسجيل صوتي',
        'document': '📎 مستند',
        'location': '📍 موقع',
    }.get(msg_type, 'مرفق')
    caption = escape(body) if body else ''
    html = f'<em>{escape(label)}</em>' + (f'<br/>{caption}' if caption else '')
    return Markup(html)

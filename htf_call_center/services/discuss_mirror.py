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

import base64
import logging
from typing import Optional
from html import escape

import requests
from markupsafe import Markup

from odoo import _

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- #
# Language pinning                                                 #
# ---------------------------------------------------------------- #

def _bubble_lang_code(env) -> str:
    """Pick the language Discuss mirror bubbles render in.

    Bubbles store HTML in ``mail.message.body`` at write time — they're
    NOT re-translated per-viewer. So we must pin ONE language at render
    time. For Numo we want Arabic; we detect any active ``ar*`` lang on
    the DB and fall back to ``en_US`` if none is installed.

    Centralising the lookup also means the migration that re-renders
    historical bubbles uses the same logic as real-time webhook handlers.
    """
    try:
        ar = env['res.lang'].sudo().with_context(active_test=False).search([
            ('code', '=like', 'ar%'),
            ('active', '=', True),
        ], limit=1)
        return ar.code if ar else 'en_US'
    except Exception:  # noqa: BLE001
        return 'en_US'


def _with_bubble_lang(env):
    """Return an env whose ``lang`` context is pinned for bubble rendering.

    Free-function renderers below use ``record.env._('…')`` to translate
    strings. ``env._`` reads ``env.lang`` directly, so the recordset MUST
    be browsed inside the lang-pinned env for translations to apply.
    Without this, ``_()`` falls back to English source strings because it
    can't introspect a ``self`` recordset from a free function's stack
    frame.
    """
    return env(context=dict(env.context, lang=_bubble_lang_code(env)))


def _bubble_tz(env) -> str:
    """Timezone used to render bubble timestamps.

    A bubble stores ONE rendered string (it isn't re-localised per
    viewer), and it's rendered in the WEBHOOK context where ``env.user``
    is the API/service account — never the viewing agent — so the acting
    user's tz is meaningless here. Pin the workspace tz instead: the main
    company partner's tz, else Asia/Riyadh (Numo's locale).
    """
    try:
        return env.company.partner_id.tz or 'Asia/Riyadh'
    except Exception:  # noqa: BLE001
        return 'Asia/Riyadh'


def _local_hm(env, dt) -> str:
    """Format a naive-UTC datetime as ``HH:MM`` in the workspace tz.

    Call bubbles previously showed the raw UTC time (e.g. "بدأت 07:58"
    for a 10:58 Riyadh call); convert before formatting.
    """
    if not dt:
        return ''
    try:
        import pytz
        return pytz.utc.localize(dt).astimezone(
            pytz.timezone(_bubble_tz(env))
        ).strftime('%H:%M')
    except Exception:  # noqa: BLE001 — fall back to raw value
        return dt.strftime('%H:%M')


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
    if partner:
        partner_updates = {}
        if convo_id and partner.x_htf_last_conversation_id != convo_id:
            partner_updates['x_htf_last_conversation_id'] = convo_id
        # Resolve the raw Hatif UUID for the partner mirror — we have
        # the htf.channel local id (htf_channel_id arg), look up its
        # UUID Char. Skip silently if the local row isn't found
        # (shouldn't happen in practice but the partner write must not
        # block the webhook on a stale FK).
        if htf_channel_id:
            ch_uuid = channel.env['htf.channel'].sudo().browse(htf_channel_id).htf_channel_id
            if ch_uuid and partner.x_htf_last_channel_uuid != ch_uuid:
                partner_updates['x_htf_last_channel_uuid'] = ch_uuid
        if partner_updates:
            partner.sudo().write(partner_updates)


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
        # Pin lang so _render_wa_body's `record.env._()` translates.
        render_env = _with_bubble_lang(env)
        htf_message = htf_message.with_env(render_env)
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
        # v19.0.1.40.0 — stamp the channel's inbound timestamp and push
        # it to the OWL store so the composer's 24h-window gate opens
        # reactively. This is keyed on the CHANNEL, not the authoring
        # partner, so it stays correct even when phone-format variations
        # land the inbound on a duplicate partner record different from
        # the channel's x_htf_partner_id.
        channel._htf_stamp_inbound_now(when=htf_message.created_at or None)
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
        # Pin lang so _render_wa_body's `record.env._()` translates.
        render_env = _with_bubble_lang(env)
        htf_message = htf_message.with_env(render_env)
        channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        if not channel:
            return
        _stamp_conversation_metadata(channel, partner, payload, htf_message.channel_id.id)
        sentinel = _wa_message_id(htf_message)
        if _already_mirrored(env, channel.id, sentinel):
            return  # idempotent
        body = _render_wa_body(htf_message, direction='outbound')
        # Author: the agent who sent it via Hatif (if mapped). Otherwise
        # anchor to the customer's partner — visually consistent (their
        # name + Hatif logo avatar) and avoids "Public user" / OdooBot
        # noise when the webhook doesn't tell us the agent.
        author = _resolve_outbound_author(env, htf_message, partner=partner)
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
        # Pin lang so _render_call_body's `record.env._()` translates.
        render_env = _with_bubble_lang(env)
        call_row = call_row.with_env(render_env)
        channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        if not channel:
            return
        _stamp_conversation_metadata(channel, partner, payload, call_row.channel_id.id)
        sentinel = _call_message_id(call_row)
        body = _render_call_body(call_row)
        existing = env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('message_id', '=', sentinel),
        ], limit=1)
        if existing:
            # A call progresses through several Hatif webhooks
            # (ringing -> answered -> completed). calls.py calls this
            # mirror on EACH one. Previously _already_mirrored() made us
            # skip after the first, so the bubble froze at the initial
            # "ringing · 0:00 · no summary" state while the htf.call row
            # filled in duration + AI summary + recording. Refresh the
            # SAME bubble in place instead so it tracks the final call.
            _update_call_bubble(env, channel, existing, call_row, body)
            return
        author = _resolve_call_author(env, call_row, partner)
        msg = channel.with_context(
            mail_create_nosubscribe=True,
            htf_mirror_write=True,
        ).message_post(
            body=body,
            author_id=author.id if author else False,
            subtype_id=subtype,
            message_type='comment',
            message_id=sentinel,
        )
        # Attach the recording as a proper Discuss voice message if it is
        # already present on this first event (rare — the call is usually
        # still ringing here and the recording lands on a later event,
        # handled by _update_call_bubble).
        if _attach_recording_voice(env, msg, call_row):
            _bus_push_message(channel, msg)
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-discuss] mirror_call failed for partner=%s htf.call=%s",
            partner.id, call_row.id,
        )


def _update_call_bubble(env, channel, message, call_row, body) -> None:
    """Refresh an existing call bubble in place as the call progresses.

    Re-renders the body (final duration + AI summary + sentiment) and,
    once Hatif exposes the recording (absent on the early ringing/answered
    events), attaches it. Pushes the refreshed message over the bus so an
    open Discuss panel updates without a reload.
    """
    updates = {}
    if (message.body or '').strip() != str(body).strip():
        updates['body'] = body
    if updates:
        message.sudo().write(updates)
    # Attach the recording (as a Discuss voice message) the first time it
    # appears — Hatif only exposes recording_url on the completed event.
    _attach_recording_voice(env, message, call_row)
    _bus_push_message(channel, message)


def _attach_recording_voice(env, message, call_row) -> bool:
    """Download the call recording and attach it to ``message`` as a
    Discuss VOICE message (waveform player), not a plain file.

    Returns True if an attachment was added. Idempotent: a no-op when the
    call has no recording yet or the message already carries an attachment.

    Odoo 19 marks an attachment as voice via a ``discuss.voice.metadata``
    row (makes ``ir.attachment.voice_ids`` non-empty); ``message_post``'s
    ``{'voice': True}`` attachment hint is NOT honoured, so we create the
    metadata ourselves. The mimetype must match the real file (Hatif
    serves ``audio/wav``) or the player will not render.
    """
    if not call_row.recording_url or message.attachment_ids:
        return False
    items = _maybe_download_recording(call_row)
    if not items:
        return False
    fname, data, info = items[0]
    try:
        att = env['ir.attachment'].sudo().create({
            'name': fname,
            'datas': base64.b64encode(data),
            'res_model': 'mail.message',
            'res_id': message.id,
            'mimetype': info.get('mimetype') or 'audio/wav',
        })
        message.sudo().write({'attachment_ids': [(4, att.id)]})
        env['discuss.voice.metadata'].sudo().create({'attachment_id': att.id})
        return True
    except Exception:  # noqa: BLE001 — recording is non-critical
        _logger.exception(
            "[htf-discuss] attach voice recording failed for call=%s",
            call_row.id,
        )
        return False


def _bus_push_message(channel, message) -> None:
    """Push a (re)rendered bubble to connected Discuss clients."""
    try:
        from odoo.addons.mail.tools.discuss import Store
        Store(bus_channel=channel).add(message).bus_send()
    except Exception:  # noqa: BLE001 — DB already updated; live push best-effort
        _logger.exception(
            "[htf-discuss] bus push of call bubble failed for channel=%s",
            channel.id,
        )


def _resolve_call_author(env, call_row, partner):
    direction = (call_row.direction or '').lower()
    if direction == 'outbound':
        if call_row.handler_user_id and call_row.handler_user_id.partner_id:
            return call_row.handler_user_id.partner_id
        return partner  # anchor to the customer when no agent identified
    # inbound (or unknown direction) — anchor to the customer
    return partner


def _resolve_outbound_author(env, htf_message, partner=None):
    """Pick the author for an outbound mirror mail.message bubble.

    Order of preference:
      1. ``htf.message.sender_user_id.partner_id`` — the agent we
         know sent it (set by our wizard, or by mapping Hatif's
         ``senderUserId`` via ``htf.user.link``).
      2. The webhook auth user's partner (``env.user.partner_id``)
         when env.user is a real internal user — that's typically the
         API/webhook service account; shows the message came from
         "the system" not from the customer.
      3. ``base.partner_root`` (OdooBot) last resort.

    The customer's partner is INTENTIONALLY skipped here — falling
    back to ``partner`` made outbound bubbles look like they came
    from the customer in the Discuss UI (verified in user screenshot:
    the agent-sent template body appeared grouped under the customer's
    avatar at 12:09 PM). For Hatif WhatsApp flows the directionality
    has to be visually obvious; misattributing outbound to the
    customer breaks that completely.

    ``partner`` is still accepted as a parameter for API compatibility
    with callers — it's ignored for author selection but documents
    the conversation context.
    """
    del partner  # explicitly ignore — kept on signature for caller compat
    if htf_message.sender_user_id and htf_message.sender_user_id.partner_id:
        return htf_message.sender_user_id.partner_id
    odoobot = env.ref('base.partner_root', raise_if_not_found=False)
    if env.user and not env.user._is_public() and env.user.partner_id:
        # Avoid the public webhook user — if env.user really is the
        # public anon (which Hatif's HMAC route disallows in practice
        # but be defensive), fall through to OdooBot.
        if env.user.partner_id != odoobot:
            return env.user.partner_id
    return odoobot or env.user.partner_id


def _render_call_body(call_row) -> Markup:
    """Compose the HTML body of the call bubble.

    Returned as `markupsafe.Markup` so Odoo's mail sanitizer recognises
    the markup as pre-sanitised. Strings use ``call_row.env._(...)`` —
    NOT the module-level ``_()`` — because the bare ``_()`` from a free
    function can't introspect a recordset out of the stack frame and
    silently falls back to the English source string. Callers must pass
    a ``call_row`` browsed inside a lang-pinned env (see
    ``_with_bubble_lang``).

    Layout (renders next to the voice-note bubble in Discuss):
      📞 <verb>  ·  <duration>  ·  started <time>
      Answered by <agent>  (if pickup_kind=human)
      Summary: <ai summary first 200 chars>  (if present)
    """
    env = call_row.env
    status = (call_row.status or '').lower()
    pickup_kind = (call_row.pickup_kind or '').lower()
    duration = call_row.duration_display or ''
    started = _local_hm(env, call_row.created_at)
    direction = (call_row.direction or '').lower()
    icon, verb = _call_icon_and_verb(env, status, pickup_kind, direction)
    parts = [f'<strong>{icon} {escape(verb)}</strong>']
    # Show duration only when a conversation actually happened — a missed /
    # no-answer call has no meaningful "0:00" to display.
    if duration and duration not in ('0:00', '0:00:00') and status not in _NO_ANSWER_STATUSES:
        parts.append(f' · {escape(duration)}')
    if started:
        parts.append(f' · {escape(env._("started"))} {escape(started)}')
    head = ''.join(parts)
    extra = []
    if pickup_kind == 'human' and call_row.handler_user_id and call_row.handler_user_id.name:
        extra.append(
            f'<small>{escape(env._("Answered by"))} '
            f'{escape(call_row.handler_user_id.name)}</small>'
        )
    elif pickup_kind == 'system':
        extra.append(
            f'<small><em>{escape(env._("Picked up by auto-responder / IVR"))}</em></small>'
        )
    if call_row.summary:
        summary_html = _render_summary_html(call_row.summary)
        if summary_html:
            extra.append(f'<div class="htf-call-summary">{summary_html}</div>')
    html = head + ('<br/>' + '<br/>'.join(extra) if extra else '')
    return Markup(html)


def _render_summary_html(summary: str) -> str:
    """Render Hatif's AI call summary in full, preserving its structure.

    Hatif returns a markdown-lite block — ``### <heading>`` section
    titles, ``∙`` bullet lines, and blank-line spacing between sections,
    e.g.::

        ### ملخص المكالمة
        ∙ العميل يسأل عن ...
        ∙ ...

        ### الخطوات التالية
        ∙ ...

    We keep it verbatim (no truncation): ``###`` lines become bold
    headings, bullet/body lines are kept as-is (the ∙ glyph preserved),
    and blank lines become a visible gap. Everything is HTML-escaped
    before re-inserting the layout tags, so the body is safe to wrap in
    Markup at the call site.
    """
    text = (summary or '').replace('\r\n', '\n').replace('\r', '\n')
    out = []
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            out.append('')  # blank line -> spacing
            continue
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
            out.append(f'<strong>{escape(heading)}</strong>')
        else:
            out.append(escape(line))
    # Drop leading/trailing blanks so the bubble has no stray gaps.
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    return '<br/>'.join(out)


def _clean_summary(raw: str) -> str:
    """Trim Hatif's markdown noise from a call summary string.

    Hatif's AI summarisation prefixes the output with `### ملخص المكالمة`
    (a level-3 markdown heading) which Discuss renders as literal "###"
    characters because the mail.message body sanitiser doesn't process
    markdown. Strip every leading `#` and surrounding whitespace.
    """
    s = (raw or '').strip()
    while s.startswith('#'):
        s = s.lstrip('#').strip()
    return s


# Direction/outcome-coloured phone icons for call bubbles. Inlined as
# Font Awesome (rides on the icon font Odoo's chrome already loads) so the
# colour itself signals the call type at a glance: inbound green, outbound
# teal (Hatif brand), missed/failed red.
_ICON_INBOUND = '<i class="fa fa-phone" style="color:#28a745"></i>'
_ICON_OUTBOUND = '<i class="fa fa-phone" style="color:#02c7b5"></i>'
_ICON_MISSED = '<i class="fa fa-phone" style="color:#e0245e"></i>'

# Statuses that mean "no conversation happened" (no answer / rejected).
_NO_ANSWER_STATUSES = (
    'missed', 'no_answer', 'rejected_by_caller', 'rejected_by_callee',
    'cancelled',
)


def _call_icon_and_verb(env, status: str, pickup_kind: str,
                        direction: str = '') -> tuple[str, str]:
    """First-line label for the call bubble.

    The previous version keyed only on ``status`` ("Call ended"), so the
    bubble never said whether the call was inbound, outbound, or missed —
    which is the single most important fact about a call log entry. Now
    the verb (and icon colour) encode direction + outcome.
    """
    inbound = (direction or '').lower() == 'inbound'
    if status in _NO_ANSWER_STATUSES:
        if inbound:
            return _ICON_MISSED, env._('Missed call')
        return _ICON_MISSED, env._('Outbound call (no answer)')
    if status == 'failed':
        return _ICON_MISSED, (
            env._('Inbound call (failed)') if inbound
            else env._('Outbound call (failed)')
        )
    if status == 'ringing':
        return (
            (_ICON_INBOUND, env._('Incoming call')) if inbound
            else (_ICON_OUTBOUND, env._('Outgoing call'))
        )
    # active / answered / completed → a real conversation took place.
    if inbound:
        return _ICON_INBOUND, env._('Inbound call')
    return _ICON_OUTBOUND, env._('Outbound call')


_AUDIO_EXT_BY_MIME = {
    'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/wave': 'wav',
    'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/ogg': 'ogg',
    'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/aac': 'aac',
}


def _maybe_download_recording(call_row) -> list:
    """Return ``[(filename, bytes, {'mimetype': ...})]`` for the recording,
    or ``[]`` on failure.

    The mimetype is taken from the response Content-Type (Hatif serves
    ``audio/wav``, NOT mp3) and falls back to the URL extension — getting
    this right matters because Discuss only renders an audio/voice player
    when the attachment's mimetype actually matches the bytes.

    Hatif's recording_url is short-lived, so the download MUST happen
    synchronously inside the webhook handler. 10-second timeout is the
    budget.
    """
    url = call_row.recording_url or ''
    if not url:
        return []
    try:
        resp = requests.get(url, timeout=_RECORDING_DOWNLOAD_TIMEOUT_S, stream=True)
        resp.raise_for_status()
        ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
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
    url_ext = url.split('?')[0].rsplit('.', 1)[-1].lower()
    if ctype in _AUDIO_EXT_BY_MIME:
        mimetype = ctype
    elif url_ext == 'wav':
        mimetype = 'audio/wav'
    elif url_ext in ('mp3', 'mpeg'):
        mimetype = 'audio/mpeg'
    else:
        mimetype = 'audio/wav'  # Hatif's default container
    ext = _AUDIO_EXT_BY_MIME.get(mimetype, url_ext or 'wav')
    filename = f'call-{call_row.htf_call_id or call_row.id}.{ext}'
    return [(filename, data, {'mimetype': mimetype})]


def _render_wa_body(htf_message, direction: str) -> Markup:
    """Render a WA body into the Discuss bubble.

    Uses ``htf_message.env._(...)`` (NOT module-level ``_()``) so the
    pinned-lang env passed in by the caller actually drives translation.
    See ``_render_call_body`` for the why.

    v19.0.1.38.0: for outbound template sends, look up the matching
    htf.template by name + channel and render its body_preview with
    {{1}}/{{2}}/... parameter substitution from the htf.message's
    raw_payload. Falls back to the previous "📝 <template_name>" form
    when the template isn't found locally OR the body_preview is
    blank (admin hasn't pasted it yet). Without this fix outbound
    templates surfaced as "Attachment / welcom_message" in the
    Discuss popup, hiding the actual customer-visible content.
    """
    env = htf_message.env
    msg_type = htf_message.message_type or 'text'
    body = htf_message.body or ''
    if msg_type == 'text':
        return Markup(escape(body).replace('\n', '<br/>'))
    if msg_type == 'template':
        rendered = _render_template_bubble(htf_message)
        if rendered is not None:
            return rendered
        # fall through to generic attachment label
    label = {
        'image': env._('📷 Image'),
        'video': env._('🎥 Video'),
        'audio': env._('🎵 Audio'),
        'document': env._('📎 Document'),
        'location': env._('📍 Location'),
    }.get(msg_type, env._('Attachment'))
    caption = escape(body) if body else ''
    html = f'<em>{escape(label)}</em>' + (f'<br/>{caption}' if caption else '')
    return Markup(html)


def _render_template_bubble(htf_message) -> Optional[Markup]:
    """Resolve the htf.template for an outbound template send and render
    its body_preview with {{N}} substituted by the actual parameters
    used at send time. Returns None when the template can't be located
    OR the admin hasn't pasted body_preview yet — caller falls back to
    the generic attachment-style label.

    The template name we want to look up lives in the htf.message body,
    which was set by ``_render_template_preview`` to
    ``📝 <template_name> — value1 | value2`` (or just ``📝 <name>`` for
    parameter-less templates). We strip the 📝 prefix to recover the
    name. The actual parameter values are pulled from the request
    payload preserved on ``raw_payload`` so the rendered preview
    matches exactly what the customer received.
    """
    import json as _json
    import re as _re
    env = htf_message.env
    body = htf_message.body or ''
    # Body is set by _render_template_preview: "📝 <name> — v1 | v2"
    # Strip emoji + isolate the name (everything before " — " or EOL).
    stripped = body.replace('📝', '', 1).strip()
    template_name = stripped.split(' — ', 1)[0].strip() if stripped else ''
    if not template_name:
        return None
    Template = env['htf.template'].sudo()
    domain = [('name', '=', template_name)]
    if htf_message.channel_id:
        # Prefer the template on the same channel, but fall back to
        # any template with this name — channel-scoped lookups can
        # miss if Hatif moved the template between channels.
        scoped = Template.search(
            domain + [('channel_id', '=', htf_message.channel_id.id)],
            limit=1,
        )
        tmpl = scoped or Template.search(domain, limit=1)
    else:
        tmpl = Template.search(domain, limit=1)
    if not tmpl or not (tmpl.body_preview or '').strip():
        return None
    # Extract Body parameters from the original Hatif request payload
    # we stored on htf.message.raw_payload at send-time.
    values: list[str] = []
    try:
        payload = _json.loads(htf_message.raw_payload or '{}') or {}
        request_body = (payload.get('_request') or {})
        for entry in request_body.get('Parameters') or []:
            if entry.get('Type') == 'Body':
                for v in entry.get('Values') or []:
                    if isinstance(v, dict) and v.get('Type') == 'text':
                        values.append(str(v.get('Text', '')))
                break
    except (TypeError, ValueError):
        values = []
    text = tmpl.body_preview
    if values:
        def _sub(m):
            idx = int(m.group(1)) - 1
            return values[idx] if 0 <= idx < len(values) else m.group(0)
        text = _re.sub(r'\{\{(\d+)\}\}', _sub, text)
    safe = escape(text).replace('\n', '<br/>')
    return Markup(safe)

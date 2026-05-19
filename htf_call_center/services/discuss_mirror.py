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
        body = _render_wa_body(htf_message, direction='inbound')
        channel.with_context(
            mail_create_nosubscribe=True,
            htf_mirror_write=True,
        ).message_post(
            body=body,
            author_id=partner.id,
            subtype_id=subtype,
            message_type='comment',
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
        )
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-discuss] mirror_outbound_wa_from_hatif failed for partner=%s htf.message=%s",
            partner.id, htf_message.id,
        )


def _render_wa_body(htf_message, direction: str) -> str:
    """Render a WA body into the Discuss bubble.

    Plain-text body (escaped) for text messages. For media types
    (image / video / audio / document / location) include a small
    HTML label so the bubble shows context — media itself gets
    attached separately via the attachment_ids mechanism in a later
    iteration (P7.3 already does this for call recordings).
    """
    msg_type = htf_message.message_type or 'text'
    body = htf_message.body or ''
    if msg_type == 'text':
        return escape(body).replace('\n', '<br/>')
    # Media — show the type + caption. URL is intentionally NOT embedded
    # because Hatif's mediaUrl is short-lived and 401s after a few minutes.
    label = {
        'image': _('📷 Image'),
        'video': _('🎥 Video'),
        'audio': _('🎵 Audio'),
        'document': _('📎 Document'),
        'location': _('📍 Location'),
    }.get(msg_type, _('Attachment'))
    caption = escape(body) if body else ''
    return f'<i>{label}</i>' + (f'<br/>{caption}' if caption else '')

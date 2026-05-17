"""Chatter posting helpers (P2 T2.4).

Posts inbound + outbound WhatsApp bubbles to the related ``res.partner``
chatter. Stores the resulting ``mail.message.id`` on
``htf.message.chatter_message_id`` so later STATUS updates can re-render
without creating a duplicate bubble.

Body rendering uses a small inline HTML template — keeps the dependency
graph tight and avoids a full QWeb template file for P2. Templates can
be promoted to ``data/mail_templates.xml`` later if Numo wants brand
customisation per channel.
"""

from __future__ import annotations

import json
import logging
from html import escape

from markupsafe import Markup
from odoo import _

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- #
# Public API                                                       #
# ---------------------------------------------------------------- #

def post_inbound_wa(partner, htf_message):
    """Post an inbound WhatsApp bubble to ``partner`` chatter.

    Returns the ``mail.message`` record (saved to
    ``htf_message.chatter_message_id``).
    """
    if not partner or not htf_message:
        return False
    body = _render_inbound(htf_message)
    subtype = _ref(htf_message.env, 'mail.mt_comment')
    msg = partner.message_post(
        body=body,
        subtype_id=subtype,
        author_id=partner.id,
        message_type='comment',
    )
    if msg:
        htf_message.sudo().write({'chatter_message_id': msg.id})
    return msg


def post_outbound_wa(partner, htf_message):
    """Post an outbound WhatsApp bubble to ``partner`` chatter."""
    if not partner or not htf_message:
        return False
    body = _render_outbound(htf_message)
    subtype = _ref(htf_message.env, 'mail.mt_note')  # internal note style — agent action
    author_id = htf_message.sender_user_id.partner_id.id or False
    kwargs = {
        'body': body,
        'subtype_id': subtype,
        'message_type': 'comment',
    }
    if author_id:
        kwargs['author_id'] = author_id
    msg = partner.message_post(**kwargs)
    if msg:
        htf_message.sudo().write({'chatter_message_id': msg.id})
    return msg


def refresh_status(htf_message):
    """STATUS update (delivered/read/failed) — re-render the existing bubble.

    Avoids creating a duplicate chatter row by editing
    ``htf_message.chatter_message_id.body`` in place.
    """
    mail_msg = htf_message.chatter_message_id
    if not mail_msg:
        return False
    body = (
        _render_outbound(htf_message)
        if htf_message.direction == 'outbound'
        else _render_inbound(htf_message)
    )
    mail_msg.sudo().write({'body': body})
    return mail_msg


# ---------------------------------------------------------------- #
# Internals                                                        #
# ---------------------------------------------------------------- #

def _ref(env, xmlid: str):
    rec = env.ref(xmlid, raise_if_not_found=False)
    return rec.id if rec else False


def _render_inbound(htf_message) -> Markup:
    body_html = _content_block(htf_message)
    via = htf_message.channel_id.display_name or htf_message.channel_id.name or _('Channel')
    parts = [
        '<div class="o_htf_wa_bubble o_htf_wa_inbound">',
        f'<div class="o_htf_wa_meta">📲 <b>{escape(_("WhatsApp"))}</b> · <i>{escape(via)}</i></div>',
        body_html,
        f'<div class="o_htf_wa_footer">{escape(_("Inbound"))}</div>',
        '</div>',
    ]
    return Markup('\n'.join(parts))


def _render_outbound(htf_message) -> Markup:
    body_html = _content_block(htf_message)
    via = htf_message.channel_id.display_name or htf_message.channel_id.name or _('Channel')
    sender = htf_message.sender_user_id.name or _('Agent')
    icon, label = _status_chip(htf_message)
    parts = [
        '<div class="o_htf_wa_bubble o_htf_wa_outbound">',
        f'<div class="o_htf_wa_meta">📲 <b>{escape(_("WhatsApp"))}</b> · <i>{escape(via)}</i> · {escape(sender)}</div>',
        body_html,
        f'<div class="o_htf_wa_footer">{icon} {escape(label)}</div>',
        '</div>',
    ]
    return Markup('\n'.join(parts))


def _content_block(htf_message) -> str:
    """Render the message body per type. Plain HTML, escaped."""
    mt = htf_message.message_type
    body = (htf_message.body or '').strip()

    if mt == 'text':
        return f'<p>{escape(body) or _("(empty message)")}</p>'

    if mt == 'image':
        url = escape(htf_message.media_url or '')
        if url:
            return f'<p><a href="{url}" target="_blank">🖼️ {escape(_("Image"))}</a></p>'
        return f'<p>🖼️ {escape(_("(image, link expired)"))}</p>'

    if mt == 'video':
        url = escape(htf_message.media_url or '')
        if url:
            return f'<p><a href="{url}" target="_blank">🎬 {escape(_("Video"))}</a></p>'
        return f'<p>🎬 {escape(_("(video, link expired)"))}</p>'

    if mt == 'audio':
        url = escape(htf_message.media_url or '')
        if url:
            return f'<p><a href="{url}" target="_blank">🎙️ {escape(_("Voice note"))}</a></p>'
        return f'<p>🎙️ {escape(_("(voice note, link expired)"))}</p>'

    if mt == 'document':
        url = escape(htf_message.media_url or '')
        if url:
            return f'<p><a href="{url}" target="_blank">📄 {escape(_("Document"))}</a></p>'
        return f'<p>📄 {escape(_("(document, link expired)"))}</p>'

    if mt == 'sticker':
        url = escape(htf_message.media_url or '')
        if url:
            return f'<p><a href="{url}" target="_blank">🌟 {escape(_("Sticker"))}</a></p>'
        return f'<p>🌟 {escape(_("(sticker)"))}</p>'

    if mt == 'location':
        lat = htf_message.latitude
        lon = htf_message.longitude
        if lat or lon:
            map_url = f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}'
            return f'<p>📍 <a href="{escape(map_url)}" target="_blank">{lat:.5f}, {lon:.5f}</a></p>'
        return f'<p>📍 {escape(_("(location, no coords)"))}</p>'

    if mt == 'contact':
        snippet = body[:200].replace('\n', '<br/>') if body else _('(vCard)')
        return f'<p>👤 {escape(_("Contact card:"))}<br/>{escape(snippet)}</p>'

    if mt == 'template':
        return f'<p>📝 <i>{escape(_("WhatsApp template"))}</i></p><p>{escape(body) or escape(_("(template body)"))}</p>'

    if mt == 'interactive':
        return f'<p>🟢 <i>{escape(_("Interactive message"))}</i></p><p>{escape(body) or escape(_("(reply)"))}</p>'

    return f'<p><i>{escape(_("Unsupported message type: %s") % mt)}</i></p>'


def _status_chip(htf_message) -> tuple[str, str]:
    """Return (emoji, label) for the outbound delivery state."""
    state = htf_message.state
    if state == 'read':
        return ('✓✓', _('Read'))
    if state == 'delivered':
        return ('✓✓', _('Delivered'))
    if state == 'sent':
        return ('✓', _('Sent'))
    if state == 'failed':
        reason = (htf_message.error_reason or '').strip()
        if reason:
            return ('⚠️', _('Failed — %s') % reason)
        return ('⚠️', _('Failed'))
    return ('⏳', _('Pending'))

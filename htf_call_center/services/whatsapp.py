"""Outbound WhatsApp service (P3 T3.2).

Send free-form text inside the 24h Meta window OR a pre-approved
template anytime. Both flows:

1. Pre-checks: DNC list, 24h window (text only), channel resolution
2. POST to Hatif via :class:`HtfHttpClient` (auth + retry already
   wrapped by ``services/http_client.py``)
3. Persist ``htf.message`` (state=sent on 200, state=failed_pending on
   transient error so the retry cron T3.6 can pick it up, state=failed
   on permanent error)
4. Post outbound chatter bubble (``services/chatter.post_outbound_wa``)
5. Fire ``htf.wa.outbound`` signal

Live-send safety gate
---------------------

Per Q-01 ANSWERED (no sandbox — use prod creds with safety net):

- The actual HTTP POST is gated by ``htf.config.allow_real_outbound``
  (Bool, default False). When False the service does the full
  pre-check + persistence + chatter flow, but **does NOT** call Hatif —
  the message is marked ``state='sent'`` with a synthetic
  ``conversation_event_id`` prefixed ``dryrun:`` and a chatter note
  saying so.
- Admin flips ``allow_real_outbound`` in Settings to go live. The
  switch is per-environment (different value on dev vs staging vs
  prod), held in ``ir.config_parameter``.
- During dev/UAT we also recommend whitelisting destination phones
  via ``htf.config.outbound_phone_whitelist`` (comma-separated E.164)
  so even when the gate is ON, only ``+966561868578`` (Amr's dev
  number per Q-12 ANSWERED) can receive real messages until rollout.

The gate's purpose is to keep us shipping code straight to prod
without giant try/except wrappers, while never accidentally spamming
real customers during a refactor.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from odoo import _

from ..exceptions import (
    HtfApiError, HtfChannelNotFoundError, HtfDncBlockedError,
    HtfServerError, HtfValidationError, HtfWindowExpiredError,
)
from ..signals import htf_signals
from . import channel_resolver, chatter

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- #
# Constants                                                         #
# ----------------------------------------------------------------- #

ENDPOINT_SEND_TEXT = '/v1/whatsapp/service-account/sendText'
ENDPOINT_SEND_TEMPLATE = '/v1/whatsapp/service-account/sendTemplate'

# Local cost estimates per Meta category (USD per message) — Q-09 ASSUMED.
# Numbers are 2024 published WhatsApp Business Platform rates for KSA.
COST_BY_CATEGORY = {
    'marketing':      0.0240,
    'utility':        0.0224,
    'authentication': 0.0265,
    'service':        0.0000,
}


# ----------------------------------------------------------------- #
# Public API                                                        #
# ----------------------------------------------------------------- #

def send_text(  # noqa: PLR0913 — kwarg-only signature
    env,
    *,
    to_number: str,
    text: str,
    partner=None,
    lead=None,
    channel=None,
    sender_user=None,
    category: str = 'service',
):
    """Send a free-form text WhatsApp.

    Returns the persisted ``htf.message`` record. Raises one of the
    typed exceptions on pre-check failure. Hatif API errors are caught
    and persisted as ``state='failed_pending'`` (cron will retry T3.6)
    or ``'failed'`` on permanent rejection.
    """
    sender = sender_user or env.user
    channel = channel or channel_resolver.resolve_outbound_wa(
        env, partner=partner, lead=lead, sender_user=sender,
    )

    _check_dnc(env, partner, to_number)
    _check_window(partner)

    body = {
        'ChannelId': channel.htf_channel_id,
        'Text': text,
        'ToNumber': _strip_plus(to_number),
    }
    return _send(
        env,
        endpoint=ENDPOINT_SEND_TEXT,
        body=body,
        message_type='text',
        message_text=text,
        partner=partner,
        lead=lead,
        channel=channel,
        sender_user=sender,
        category=category,
        to_number=to_number,
    )


def send_template(
    env,
    *,
    template_name: str,
    language: str,
    to_number: str,
    parameters: list[dict] | None = None,
    partner=None,
    lead=None,
    channel=None,
    sender_user=None,
    category: str = 'utility',
):
    """Send a pre-approved WhatsApp template.

    ``parameters`` follows Hatif's nested array shape exactly — see the
    helper functions ``build_body_parameter()``, ``build_header_image()``,
    etc. for ergonomic builders.
    """
    sender = sender_user or env.user
    channel = channel or channel_resolver.resolve_outbound_wa(
        env, partner=partner, lead=lead, sender_user=sender,
    )

    _check_dnc(env, partner, to_number)
    # No window check — templates may be sent outside the 24h window.

    body = {
        'ChannelId': channel.htf_channel_id,
        'TemplateName': template_name,
        'Language': language,
        'ToNumber': _strip_plus(to_number),
        'Parameters': parameters or [],
    }
    return _send(
        env,
        endpoint=ENDPOINT_SEND_TEMPLATE,
        body=body,
        message_type='template',
        message_text=_render_template_preview(template_name, parameters or []),
        partner=partner,
        lead=lead,
        channel=channel,
        sender_user=sender,
        category=category,
        to_number=to_number,
    )


# ----------------------------------------------------------------- #
# Parameter builders                                                #
# ----------------------------------------------------------------- #

def build_body_parameter(*values: str) -> dict:
    """Body variable values — positional, map to ``{{1}}, {{2}}, ...``."""
    return {
        'Type': 'Body',
        'Values': [{'Type': 'text', 'Text': str(v)} for v in values],
    }


def build_header_text(text: str) -> dict:
    return {'Type': 'Header', 'Values': [{'Type': 'text', 'Text': text}]}


def build_header_image(image_url: str) -> dict:
    return {'Type': 'Header', 'Values': [{'Type': 'image', 'ImageUrl': image_url}]}


def build_header_video(video_url: str) -> dict:
    return {'Type': 'Header', 'Values': [{'Type': 'video', 'VideoUrl': video_url}]}


def build_header_document(document_url: str, filename: str | None = None) -> dict:
    values = {'Type': 'document', 'DocumentUrl': document_url}
    if filename:
        values['DocumentFilename'] = filename
    return {'Type': 'Header', 'Values': [values]}


def build_url_button(index: int, dynamic_suffix: str) -> dict:
    return {
        'Type': 'Buttons', 'SubType': 'url', 'Index': str(index),
        'Values': [{'Type': 'text', 'Text': dynamic_suffix}],
    }


def build_quick_reply_button(index: int, payload: str) -> dict:
    return {
        'Type': 'Buttons', 'SubType': 'quick_reply', 'Index': str(index),
        'Values': [{'Type': 'text', 'Text': payload}],
    }


# ----------------------------------------------------------------- #
# Internals                                                         #
# ----------------------------------------------------------------- #

def _send(
    env,
    *,
    endpoint: str,
    body: dict,
    message_type: str,
    message_text: str,
    partner,
    lead,
    channel,
    sender_user,
    category: str,
    to_number: str | None = None,
):
    """Common path: persist row → POST (or dry-run) → update row → chatter + signal.

    ``lead`` is captured for future CRM-side lead_id back-reference on
    htf.message (deferred until htf.message gets a `lead_id` field — see
    P6 CRM Enrichment). Today we still resolve the right channel via the
    lead's team in the resolver chain, just don't persist the link.

    ``to_number`` is unused here (the body already carries the stripped
    number); kept on the signature for symmetry with send_text/template.
    """
    del lead, to_number  # explicitly silence unused-arg lints
    Msg = env['htf.message'].sudo()

    msg = Msg.create({
        'direction': 'outbound',
        'message_type': message_type,
        'state': 'pending',
        'body': message_text,
        'channel_id': channel.id if channel else False,
        'partner_id': partner.id if partner else False,
        'sender_user_id': sender_user.id if sender_user else False,
        'is_billable': category != 'service',
        'meta_category': category if category in COST_BY_CATEGORY else False,
        'meta_cost_estimate': COST_BY_CATEGORY.get(category, 0.0),
        'created_at': datetime.utcnow(),
        'raw_payload': json.dumps({'_request': body}, ensure_ascii=False),
    })

    if not _allow_real_outbound(env, to_number=body.get('ToNumber')):
        # Dry-run mode: simulate a successful send so the rest of the
        # pipeline exercises end-to-end without spamming customers.
        synth_id = f'dryrun:{uuid.uuid4().hex[:12]}'
        msg.write({
            'state': 'sent',
            'conversation_event_id': synth_id,
            'raw_payload': json.dumps({
                '_request': body,
                '_dryrun': True,
                'note': 'allow_real_outbound is OFF — no HTTP call made',
            }, ensure_ascii=False),
        })
        _post_chatter_and_fire(msg, partner, channel)
        return msg

    # Real send path. Note http_client.post returns the parsed JSON
    # body directly (or text on non-JSON, or None on empty).
    try:
        client = env['htf.config'].sudo().get_service('http')
        data = client.post(endpoint, json_body=body) or {}
        if not isinstance(data, dict):
            data = {}
        conv_event_id = data.get('conversationEventId') or ''
        msg_id_hint = data.get('messageId') or ''
        msg.write({
            'state': 'sent',
            'conversation_event_id': conv_event_id or False,
            'htf_message_id': msg_id_hint or False,
            'raw_payload': json.dumps({'_request': body, '_response': data},
                                       ensure_ascii=False),
        })
    except HtfValidationError as exc:
        # 4xx — permanent failure, won't retry.
        msg.write({
            'state': 'failed',
            'error_reason': exc.message or 'validation',
            'error_code': exc.status or 0,
            'raw_payload': json.dumps({'_request': body, '_error': str(exc)},
                                       ensure_ascii=False),
        })
    except (HtfServerError, HtfApiError) as exc:
        # 5xx + network errors — eligible for retry cron.
        msg.write({
            'state': 'failed_pending',
            'error_reason': exc.message or exc.__class__.__name__,
            'error_code': getattr(exc, 'status', 0) or 0,
            'raw_payload': json.dumps({'_request': body, '_error': str(exc)},
                                       ensure_ascii=False),
        })

    _post_chatter_and_fire(msg, partner, channel)
    return msg


def _post_chatter_and_fire(msg, partner, channel):
    if partner:
        try:
            chatter.post_outbound_wa(partner, msg)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[htf-wa] outbound chatter post failed for msg id=%s", msg.id,
            )
    htf_signals.fire('htf.wa.outbound', {
        'message_id': msg.id,
        'partner_id': partner.id if partner else None,
        'channel_id': channel.id if channel else None,
        'state': msg.state,
        'message_type': msg.message_type,
    })


def _check_dnc(env, partner, to_number: str):
    if partner and getattr(partner, 'x_htf_opted_out', False):
        raise HtfDncBlockedError(
            _('Customer %s has opted out of WhatsApp messaging.') % partner.display_name,
            phone=to_number,
        )
    # htf.dnc model doesn't exist yet (P7); fall back to partner flag only.


def _check_window(partner):
    if not partner:
        return
    if getattr(partner, 'x_htf_24h_window_open', False):
        return
    last_inbound = getattr(partner, 'x_htf_last_inbound_at', None)
    raise HtfWindowExpiredError(
        _('24h re-engagement window expired. '
          'Free-form text not allowed — use a pre-approved template.'),
        partner=partner, last_inbound_at=last_inbound,
    )


def _allow_real_outbound(env, *, to_number: str | None = None) -> bool:
    cfg = env['htf.config'].sudo()
    if not _truthy(cfg.get_param('allow_real_outbound')):
        return False
    raw_whitelist = (cfg.get_param('outbound_phone_whitelist') or '').strip()
    if not raw_whitelist:
        return True
    # Canonicalize BOTH sides: strip whitespace, dashes, parens, leading +.
    # Live UAT 2026-05-18 caught this — partner.phone arrives as
    # '+966 56 186 8578' but admins type whitelist as '+966561868578'.
    # Without canonicalization the candidate set never matched the
    # whitelist and every real-send fell back to dry-run silently.
    allowed = {_phone_canonical(p) for p in raw_whitelist.split(',') if p.strip()}
    if not to_number:
        return False
    return _phone_canonical(to_number) in allowed


def _phone_canonical(value: str) -> str:
    """Strip everything except digits — works for E.164 and local formats."""
    if not value:
        return ''
    return ''.join(c for c in str(value) if c.isdigit())


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return False


def _strip_plus(num: str) -> str:
    if not num:
        return ''
    return num.lstrip('+').strip()


def _render_template_preview(template_name: str, parameters: list[dict]) -> str:
    """Render a one-line preview of a template send for chatter body."""
    parts = [f'📝 {template_name}']
    for entry in parameters or []:
        if entry.get('Type') == 'Body':
            vals = [v.get('Text', '') for v in entry.get('Values') or []]
            if vals:
                parts.append('— ' + ' | '.join(vals))
    return ' '.join(parts)


# ----------------------------------------------------------------- #
# Retry cron (T3.6)                                                 #
# ----------------------------------------------------------------- #

def cron_retry_failed_pending(env, max_attempts: int = 6) -> int:
    """Retry messages stuck in ``failed_pending``.

    Each pass retries every row; after ``max_attempts`` total pass-throughs
    (default 6 → 30 min at 5-min cron interval) the row is marked
    ``failed`` so the agent sees it as permanently dead.
    """
    Msg = env['htf.message'].sudo()
    pending = Msg.search([('state', '=', 'failed_pending')])
    retried = 0
    for row in pending:
        attempts = (row.error_code or 0) + 1  # reuse error_code as attempt counter
        if attempts > max_attempts:
            row.write({
                'state': 'failed',
                'error_reason': (row.error_reason or '')
                    + f' [gave up after {max_attempts} attempts]',
            })
            continue

        # Replay original request from raw_payload._request.
        try:
            raw = json.loads(row.raw_payload or '{}') if row.raw_payload else {}
        except (TypeError, ValueError):
            raw = {}
        req_body = raw.get('_request') or {}
        endpoint = (
            ENDPOINT_SEND_TEMPLATE if row.message_type == 'template'
            else ENDPOINT_SEND_TEXT
        )
        try:
            client = env['htf.config'].sudo().get_service('http')
            data = client.post(endpoint, json_body=req_body) or {}
            if not isinstance(data, dict):
                data = {}
            row.write({
                'state': 'sent',
                'conversation_event_id': data.get('conversationEventId') or False,
                'htf_message_id': data.get('messageId') or row.htf_message_id,
                'error_reason': False,
                'error_code': 0,
                'raw_payload': json.dumps(
                    {'_request': req_body, '_response': data, '_retries': attempts},
                    ensure_ascii=False,
                ),
            })
            chatter.refresh_status(row)
            retried += 1
        except HtfValidationError as exc:
            row.write({
                'state': 'failed',
                'error_reason': exc.message or 'validation',
                'error_code': exc.status or 0,
            })
        except HtfApiError as exc:
            row.write({
                'error_code': attempts,
                'error_reason': (exc.message or exc.__class__.__name__)
                    + f' [attempt {attempts}/{max_attempts}]',
            })

    _logger.info("[htf-wa] cron retry: %s rows successfully sent", retried)
    return retried

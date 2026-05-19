"""Call webhook dispatcher (P4 T4.3).

Single entry point ``process()`` invoked by the webhook controller.

Responsibilities:
- Normalise Hatif's int enums (status, type, sentiment) to strings.
- Find or create the partner via E.164 phone match (caller_number for
  inbound, callee_number for outbound). Fall back to a placeholder
  ``Hatif Contact <uuid>`` partner when no phone matches — mirrors P2
  behaviour for unknown inbounds.
- Resolve the handler user via ``htf.user.link`` from ``userId``.
- Persist (or update) the ``htf.call`` row.
- Post call entry to partner chatter via ``services/chatter.post_call``.
- Fire the appropriate signal:
    completed                → htf.call.received
    failed                   → htf.call.failed
    missed family            → htf.call.missed
    active / unknown         → none (call still in flight)

Error budget: ``process()`` raises on hard failures so the controller
returns 500 and Hatif retries.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..signals import htf_signals
from ..utils.phone import normalize_e164
from . import chatter, discuss_mirror
from ..models.htf_call import (
    HATIF_DIRECTION_MAP,
    HATIF_SENTIMENT_MAP,
    HATIF_STATUS_MAP,
)

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- #
# Public entry point                                                #
# ----------------------------------------------------------------- #

def process(env, payload: dict) -> str:
    """Top-level dispatcher. Returns a one-line audit string for
    ``htf.webhook.event.note``.
    """
    direction = HATIF_DIRECTION_MAP.get(payload.get('type'))
    status = HATIF_STATUS_MAP.get(payload.get('status'))
    if not direction or not status:
        # We've seen Hatif ship status values outside their documented
        # 0-7 enum (observed: 8). Log the offending values + a short
        # payload preview so the support email writes itself.
        import json as _json
        preview = _json.dumps({
            k: payload.get(k) for k in
            ('callId', 'workspaceId', 'channelId', 'type', 'status',
             'creationTime', 'callLength')
            if k in payload
        }, ensure_ascii=False)
        _logger.warning(
            "[htf-call] skip: unmapped direction=%r status=%r — "
            "Hatif sent an enum value outside the documented set. "
            "Add it to HATIF_DIRECTION_MAP / HATIF_STATUS_MAP if it "
            "carries useful data. Preview: %s",
            payload.get('type'), payload.get('status'), preview,
        )
        return f'skip: direction={direction!r} status={status!r}'

    channel = _resolve_channel(env, payload.get('channelId'))
    partner = _resolve_partner(env, payload, direction)
    handler = _resolve_handler(env, payload.get('userId'))

    sentiment = HATIF_SENTIMENT_MAP.get(payload.get('sentiment'))
    created_at = _parse_dt(payload.get('creationTime'))
    pickup_at = _parse_dt(payload.get('pickupTime'), allow_none=True)
    hangup_at = _parse_dt(payload.get('hangupTime'), allow_none=True)

    transcription = payload.get('transcription') or {}
    transcription_text = (transcription.get('text') or '') if isinstance(transcription, dict) else ''
    transcription_words = transcription.get('words') if isinstance(transcription, dict) else None

    Call = env['htf.call'].sudo()
    # Hatif's actual payload uses 'callId' (verified 2026-05-19 against
    # erp.amro.pro raw_payloads). Apidog spec implied 'id' might be used
    # too; we accept both for forward compatibility.
    call_id = payload.get('callId') or payload.get('id') or payload.get('CallId') or ''
    existing = Call.find_by_call_id(call_id) if call_id else Call.browse()

    vals = {
        'htf_call_id': call_id or False,
        'workspace_uuid': payload.get('workspaceId') or False,
        'contact_uuid': payload.get('contactId') or False,
        'direction': direction,
        'status': status,
        'caller_number': payload.get('callerNumber') or False,
        'callee_number': payload.get('calleeNumber') or False,
        'contact_number': payload.get('contactNumber') or False,
        'created_at': created_at,
        'pickup_time': pickup_at,
        'hangup_time': hangup_at,
        'call_length_raw': payload.get('callLength') or False,
        'channel_id': channel.id if channel else False,
        'partner_id': partner.id if partner else False,
        'handler_user_id': handler.id if handler else False,
        'hatif_user_name': payload.get('userName') or False,
        'ai_agent_uuid': payload.get('aiAgentId') or False,
        'recording_url': payload.get('recordingUrl') or False,
        'transcription_text': transcription_text or False,
        'transcription_words_json': (
            json.dumps(transcription_words, ensure_ascii=False)
            if transcription_words else False
        ),
        'summary': payload.get('summary') or False,
        'sentiment': sentiment or False,
        'evaluation_criteria_json': (
            json.dumps(payload.get('evaluationCriteriaResult'),
                       ensure_ascii=False)
            if payload.get('evaluationCriteriaResult') else False
        ),
        # CSAT + AI flag — present on Hatif's real payload but not in
        # the apidog spec. Verified 2026-05-19.
        'csat_rating': payload.get('csatRating') or 0,
        'csat_method': payload.get('csatMethod') or False,
        'csat_collected_at': _parse_dt(payload.get('csatCollectedAt'),
                                        allow_none=True),
        'is_ai_call': bool(payload.get('isAiCall')),
        'raw_payload': json.dumps(payload, ensure_ascii=False, default=str),
    }

    if existing:
        existing.write(vals)
        row = existing
        outcome_verb = 'updated'
    else:
        row = Call.create(vals)
        outcome_verb = 'created'

    # Post chatter (best-effort — don't fail the webhook on render error).
    if partner:
        try:
            chatter.post_call(partner, row)
        except Exception:  # noqa: BLE001 — chatter is non-critical
            _logger.exception(
                "[htf-call] chatter post_call failed for partner=%s call=%s",
                partner.id, row.id,
            )
        # P7 — Mirror call into the partner's Discuss channel with native
        # voice-note rendering. No-op when discuss_mirror_calls flag is
        # off. discuss_mirror.mirror_call swallows its own exceptions so
        # the webhook never breaks here.
        discuss_mirror.mirror_call(env, partner, row, payload)

    # Fire the appropriate signal.
    signal_name = row.signal_bucket()
    if signal_name:
        try:
            htf_signals.fire(signal_name, {
                'call_id': row.id,
                'partner_id': partner.id if partner else None,
                'channel_id': channel.id if channel else None,
                'handler_user_id': handler.id if handler else None,
                'direction': direction,
                'status': status,
                'sentiment': sentiment,
                'duration_seconds': row.duration_seconds,
                'raw': payload,
            })
        except Exception:  # noqa: BLE001 — signal subscriber raised; surface for visibility
            _logger.exception("[htf-call] signal %s subscriber raised", signal_name)
            raise

    return f'call:{outcome_verb} id={row.id} {direction}/{status}'


# ----------------------------------------------------------------- #
# Resolvers                                                         #
# ----------------------------------------------------------------- #

def _resolve_channel(env, hatif_channel_id):
    if not hatif_channel_id:
        return env['htf.channel'].browse()
    return env['htf.channel'].sudo().search(
        [('htf_channel_id', '=', hatif_channel_id)], limit=1,
    )


def _resolve_partner(env, payload: dict, direction: str):
    """Find or create partner by phone.

    Strategy:
    1. Lookup via htf.contact.link if contactId present (most reliable —
       matches the WA inbound path so the same contact lands on the same
       partner across channels).
    2. Lookup by E.164-normalized phone (caller for inbound, callee for
       outbound). Try res.partner.phone direct match.
    3. Fall back to placeholder partner with Hatif Contact <uuid> name,
       linked via htf.contact.link with sync_state='pending'.
    """
    Partner = env['res.partner'].sudo()
    Link = env['htf.contact.link'].sudo()

    hatif_contact_id = payload.get('contactId')
    if hatif_contact_id:
        link = Link.search([('htf_contact_id', '=', hatif_contact_id)], limit=1)
        if link and link.partner_id:
            return link.partner_id

    # Phone-based match.
    candidate_phone = payload.get('callerNumber') if direction == 'inbound' \
        else payload.get('calleeNumber')
    candidate_phone = candidate_phone or payload.get('contactNumber') or ''
    normalised = normalize_e164(candidate_phone)
    if normalised:
        # Build the domain dynamically — Odoo 19 dropped the `mobile`
        # field on res.partner, but some custom installs reintroduce
        # it. Defensive check via _fields keeps us portable.
        domain = [('phone', '!=', False)]
        has_mobile = 'mobile' in Partner._fields
        if has_mobile:
            domain = ['|', ('phone', '!=', False), ('mobile', '!=', False)]
        candidates = Partner.search(domain, limit=500)
        phone_attrs = ('phone',) if not has_mobile else ('phone', 'mobile')
        for p in candidates:
            for attr in phone_attrs:
                raw = getattr(p, attr, False)
                if not raw:
                    continue
                if normalize_e164(raw) == normalised:
                    # Backfill the link only if BOTH sides are unlinked:
                    # the partner has no existing htf.contact.link AND
                    # the contact_id isn't already mapped elsewhere.
                    # The model enforces partner-link uniqueness; we
                    # respect it to keep the dispatcher idempotent.
                    if hatif_contact_id:
                        partner_already_linked = Link.search_count(
                            [('partner_id', '=', p.id)]
                        )
                        contact_already_linked = Link.search_count(
                            [('htf_contact_id', '=', hatif_contact_id)]
                        )
                        if not partner_already_linked and not contact_already_linked:
                            Link.create({
                                'partner_id': p.id,
                                'htf_contact_id': hatif_contact_id,
                                'sync_state': 'pending',
                            })
                    return p

    # Placeholder fallback.
    if hatif_contact_id:
        short = hatif_contact_id[:8] + '…'
        name = f'Hatif Contact {short}'
    elif normalised:
        name = f'Hatif Caller {normalised}'
    else:
        name = 'Hatif Caller (unknown)'

    partner = Partner.create({
        'name': name,
        'phone': normalised or candidate_phone or False,
        'comment': (
            f'[htf] Auto-created from call webhook. '
            f'contactId={hatif_contact_id or "—"} caller={candidate_phone or "—"} '
            f'direction={direction}.'
        ),
    })
    if hatif_contact_id:
        Link.create({
            'partner_id': partner.id,
            'htf_contact_id': hatif_contact_id,
            'sync_state': 'pending',
        })
    _logger.info(
        "[htf-call] placeholder partner id=%s created for "
        "contactId=%s phone=%s direction=%s",
        partner.id, hatif_contact_id, candidate_phone, direction,
    )
    return partner


def _resolve_handler(env, hatif_user_id):
    if not hatif_user_id:
        return env['res.users'].browse()
    return env['res.users'].sudo().search(
        [('x_htf_user_id', '=', hatif_user_id)], limit=1,
    )


# ----------------------------------------------------------------- #
# Helpers                                                           #
# ----------------------------------------------------------------- #

def _parse_dt(value, allow_none: bool = False):
    """Tolerate ISO8601 with trailing Z; fall back to now() unless allow_none."""
    if not value:
        if allow_none:
            return False
        from odoo.fields import Datetime as Dt
        return Dt.now()
    try:
        s = value.replace('Z', '+00:00') if isinstance(value, str) else value
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            from datetime import timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        if allow_none:
            return False
        from odoo.fields import Datetime as Dt
        return Dt.now()

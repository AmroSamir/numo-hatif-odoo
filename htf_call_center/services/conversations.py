"""Conversations lookup against Hatif's ``/v2/conversations`` API.

Used by the 19.0.1.14.0 backfill migration to populate
``res.partner.x_htf_last_conversation_id`` for partners who already
had Hatif conversations BEFORE the discuss-mirror ``_stamp_conversation_metadata``
code shipped (or before ``discuss_mirror_enabled`` was turned on).
Once backfilled, the ``htf_phone`` widget can deep-link the lead-form
Call button straight into the customer's Hatif conversation instead of
falling back to a ``?phone=`` query the portal may or may not honour.

Hatif endpoint:
    GET /v2/conversations/service-account/channels/{channelId}
        ?PhoneNumber=<E.164>
        &Sorting=LastActivityAt DESC
        &MaxResultCount=1

The endpoint is per-channel, so when a partner has been reached on
multiple Hatif channels the lookup tries each active channel and
returns the most recently active conversation overall.

Best-effort: never raises. Returns ``None`` on any error so the
caller can keep walking the partner list without aborting the whole
backfill.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..exceptions import HtfApiError
from ..utils.phone import normalize_e164

_logger = logging.getLogger(__name__)

# Meta's WhatsApp Business Platform customer-service-window: free-form
# (non-template) messages are only deliverable for 24 hours AFTER the
# last INBOUND message from the customer. Templates re-engage outside
# the window but DO NOT reset it — only the customer's reply does.
_META_WINDOW_HOURS = 24

# Hatif timeline ``Direction`` enum value for inbound events. Outbound
# is 2. We look at the most recent ``Direction == 1`` event in the
# conversation timeline to know when the customer last spoke.
_DIRECTION_INBOUND = 1

# How many timeline events to ask Hatif for. The most-recent-first sort
# means a few entries is plenty in normal traffic; bumping it costs
# almost nothing on the wire and protects us against weird threads
# where the last few events were system / status updates with no
# direction set.
_TIMELINE_FETCH_LIMIT = 50


def lookup_latest_conversation_id(env, phone: str) -> Optional[str]:
    """Return the most recently active Hatif conversationId for ``phone``.

    - Normalises ``phone`` to E.164 via ``utils.phone.normalize_e164``;
      returns ``None`` immediately if normalisation fails (invalid phone).
    - Iterates every active ``htf.channel`` and asks Hatif's
      ``/v2/conversations`` for the latest conversation matching the
      phone on that channel.
    - Returns the ``Id`` of whichever channel had the most recent
      ``LastActivityAt``, or ``None`` if Hatif has no conversation
      for that phone anywhere.

    Network / API failures on a single channel are swallowed + logged
    (one bad channel shouldn't sink the whole lookup). Total failure
    returns ``None``.
    """
    e164 = normalize_e164(phone)
    if not e164:
        return None

    channels = env['htf.channel'].sudo().search([('state', '=', 'active')])
    if not channels:
        return None

    http = env['htf.config'].get_service('http')
    best_id: Optional[str] = None
    best_when: str = ''  # ISO-8601 string compares lexicographically

    for ch in channels:
        if not ch.htf_channel_id:
            continue
        try:
            resp = http.get(
                f'/v2/conversations/service-account/channels/{ch.htf_channel_id}',
                params={
                    'PhoneNumber': e164,
                    'Sorting': 'LastActivityAt DESC',
                    'MaxResultCount': 1,
                },
            )
        except HtfApiError as exc:
            _logger.debug(
                "[htf-conversations] lookup failed on channel=%s phone=%s: %s",
                ch.htf_channel_id, e164, exc,
            )
            continue
        except Exception:  # noqa: BLE001 — defensive; never abort the loop
            _logger.exception(
                "[htf-conversations] unexpected error on channel=%s phone=%s",
                ch.htf_channel_id, e164,
            )
            continue

        items = (resp or {}).get('Items') if isinstance(resp, dict) else None
        if not items:
            continue
        top = items[0] or {}
        conv_id = top.get('Id') or top.get('id')
        last_at = top.get('LastActivityAt') or top.get('lastActivityAt') or ''
        if conv_id and (not best_when or last_at > best_when):
            best_id = conv_id
            best_when = last_at or ''

    return best_id


def get_latest_inbound_at(env, conversation_id: str) -> Optional[datetime]:
    """Return the timezone-aware UTC timestamp of the most recent
    INBOUND timeline event in a Hatif conversation, or ``None`` when
    Hatif has no inbound history (or the lookup fails).

    The function only inspects ``Direction == 1`` (inbound) events.
    Outbound sends and system / status entries are skipped — only the
    customer's actual incoming traffic resets Meta's 24h window.

    Best-effort: every API / parse failure returns ``None`` so the
    caller can fall back to the locally-cached window flag without
    propagating the exception.
    """
    if not conversation_id:
        return None
    http = env['htf.config'].get_service('http')
    try:
        resp = http.get(
            f'/v2/conversations/service-account/{conversation_id}/timeline',
            params={
                'Sorting': 'CreationTime DESC',
                'MaxResultCount': _TIMELINE_FETCH_LIMIT,
            },
        )
    except HtfApiError as exc:
        _logger.debug(
            "[htf-window] timeline lookup failed for conv=%s: %s",
            conversation_id, exc,
        )
        return None
    except Exception:  # noqa: BLE001 — defensive; never raise from this getter
        _logger.exception(
            "[htf-window] unexpected error fetching timeline for conv=%s",
            conversation_id,
        )
        return None

    items = (resp or {}).get('Items') if isinstance(resp, dict) else None
    if not items:
        return None

    for ev in items:
        if ev.get('Direction') != _DIRECTION_INBOUND:
            continue
        when = ev.get('CreationTime') or ev.get('creationTime')
        if not when:
            continue
        try:
            # Hatif returns ISO 8601 with a trailing ``Z``; Python's
            # fromisoformat doesn't parse ``Z`` until 3.11, so normalise.
            if isinstance(when, str) and when.endswith('Z'):
                when = when[:-1] + '+00:00'
            parsed = datetime.fromisoformat(when)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def refresh_window_from_hatif(env, partner, channel=None) -> bool:
    """Sync the partner's ``x_htf_24h_window_open`` /
    ``x_htf_last_inbound_at`` fields with Hatif's live conversation
    timeline. Returns the new window-open boolean.

    Why this exists: ``services.whatsapp_inbound`` is supposed to flip
    these fields on every inbound webhook, but webhooks can fail
    (network, Hatif outage, misconfigured callback URL). When the
    wizard opens we'd then see ``window_open=False`` and gate the
    free-form send even though the customer just replied 30 seconds
    ago. Calling this in ``default_get`` makes the wizard authoritative
    about window state regardless of webhook reliability.

    Behaviour:
    - ``partner`` is falsy → returns False, no write.
    - Partner has no ``x_htf_last_conversation_id`` → returns the
      partner's currently-stored flag unchanged (no conversation to
      query Hatif about).
    - Hatif timeline returns no inbound → keeps the partner's
      currently-stored flag unchanged (we don't assume "no result"
      means "no inbound ever" — Hatif may have paged it out).
    - Latest inbound found → compares to now-UTC, sets the flag, and
      writes to the partner record only if values actually changed.

    Never raises — Hatif outages fall back to whatever was last
    persisted, which preserves prior wizard behaviour.
    """
    if not partner:
        return False
    convo_id = partner.x_htf_last_conversation_id
    # v19.0.1.47.0: when Odoo has no local conversation id (history
    # wiped, inbound webhook missed, OR the conversation was started on
    # the Hatif platform and the agent comes to Odoo to continue), fall
    # back to asking Hatif for the latest conversation by phone. Hatif
    # is the source of truth for the 24h window — Odoo's local mirror is
    # only a cache. Without this the composer would wrongly block
    # free-form replies even when the customer replied <24h ago.
    if not convo_id:
        phone = partner.phone or partner.mobile or ''
        if phone:
            convo_id = lookup_latest_conversation_id(env, phone)

    if not convo_id:
        return bool(partner.x_htf_24h_window_open)

    latest = get_latest_inbound_at(env, convo_id)
    if not latest:
        return bool(partner.x_htf_24h_window_open)

    now_utc = datetime.now(timezone.utc)
    open_now = (now_utc - latest) < timedelta(hours=_META_WINDOW_HOURS)
    # Strip tzinfo for Odoo's Datetime field (naive UTC convention).
    last_inbound_naive = latest.astimezone(timezone.utc).replace(tzinfo=None)

    updates = {}
    if bool(partner.x_htf_24h_window_open) != open_now:
        updates['x_htf_24h_window_open'] = open_now
    if (not partner.x_htf_last_inbound_at) or (
        partner.x_htf_last_inbound_at != last_inbound_naive
    ):
        updates['x_htf_last_inbound_at'] = last_inbound_naive
    if convo_id and partner.x_htf_last_conversation_id != convo_id:
        updates['x_htf_last_conversation_id'] = convo_id
    if updates:
        try:
            partner.sudo().write(updates)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[htf-window] partner write failed for id=%s", partner.id,
            )

    # v19.0.1.47.0: stamp the discuss channel so the composer's window
    # gate (which reads discuss.channel.x_htf_last_inbound_at, robust to
    # duplicate-partner records) reflects the Hatif truth immediately on
    # chat-open — even with zero local message history.
    if channel and open_now:
        try:
            channel._htf_stamp_inbound_now(when=last_inbound_naive)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[htf-window] channel stamp failed for channel=%s",
                getattr(channel, 'id', None),
            )
    return open_now

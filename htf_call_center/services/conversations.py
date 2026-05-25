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

# How many conversations to scan per channel when resolving the one that
# belongs to a phone. Hatif's ``PhoneNumber`` query param is IGNORED by
# the API (verified live 2026-05-25): it returns the channel's most-recent
# conversations for ANY number, so we must match the phone ourselves over
# a window of recent conversations.
_CONVO_SCAN_LIMIT = 50


def _digits(value) -> str:
    """Digits-only form of a phone string (separator-insensitive match)."""
    return ''.join(c for c in str(value or '') if c.isdigit())


def _htf_close_channel_window(channel) -> None:
    """Clear a discuss.channel's open-window stamp and push the close to
    connected composers, so the 24h gate locks. No-op when nothing to
    clear. Used on the fail-closed paths of ``refresh_window_from_hatif``.
    """
    if not channel or not channel.x_htf_last_inbound_at:
        return
    try:
        channel.sudo().write({'x_htf_last_inbound_at': False})
        from odoo.addons.mail.tools.discuss import Store
        Store(bus_channel=channel).add(
            channel, {'x_htf_last_inbound_at': False},
        ).bus_send()
    except Exception:  # noqa: BLE001
        _logger.exception(
            "[htf-window] failed to close window on channel=%s",
            getattr(channel, 'id', None),
        )


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

    return _lookup_latest_conversation(env, e164)[0]


def _lookup_latest_conversation(env, e164: str):
    """Internal: return ``(conversation_id, htf_channel_record)`` for the
    most recently active conversation matching ``e164`` across all
    active Hatif channels, or ``(None, empty recordset)``.

    v19.0.1.49.0: tracks WHICH htf.channel the winning conversation
    lives on so callers (the chat-open window sync) can record
    ``x_htf_last_htf_channel_id`` — otherwise a free-form reply sent
    right after the window opens has no channel to route through and
    fails resolution.
    """
    empty_channel = env['htf.channel'].browse()
    http = env['htf.config'].get_service('http')
    want = _digits(e164)
    want_tail = want[-9:] if len(want) >= 9 else want
    best_id = None
    best_channel = empty_channel
    best_when = ''  # ISO-8601 string compares lexicographically

    for ch in env['htf.channel'].sudo().search([('state', '=', 'active')]):
        if not ch.htf_channel_id:
            continue
        try:
            resp = http.get(
                f'/v2/conversations/service-account/channels/{ch.htf_channel_id}',
                params={
                    'PhoneNumber': e164,
                    'Sorting': 'LastActivityAt DESC',
                    'MaxResultCount': _CONVO_SCAN_LIMIT,
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

        # v19.0.1.48.0: Hatif returns lowercase keys (items/id/
        # lastActivityAt); read those first, PascalCase as fallback.
        items = None
        if isinstance(resp, dict):
            items = resp.get('items') or resp.get('Items')
        if not items:
            continue
        # v19.0.1.67.0: Hatif IGNORES the PhoneNumber filter and returns
        # the channel's most-recent conversations for ANY number (verified
        # live — a query for +966500000000 came back with +966557349515,
        # +966566925142, ...). Taking items[0] therefore grabbed an
        # UNRELATED customer's conversation, whose recent inbound then
        # wrongly opened this partner's 24h window. Match the phone
        # ourselves and pick the most-recent conversation that ACTUALLY
        # belongs to the requested number.
        for conv in items:
            if not isinstance(conv, dict):
                continue
            cdig = _digits(
                conv.get('phoneNumber')
                or conv.get('phone')
                or conv.get('contactPhoneNumber')
                or ''
            )
            if not cdig:
                continue
            if cdig != want and not (want_tail and cdig.endswith(want_tail)):
                continue
            conv_id = conv.get('id') or conv.get('Id')
            last_at = (
                conv.get('lastActivityAt') or conv.get('LastActivityAt') or ''
            )
            if conv_id and (not best_when or last_at > best_when):
                best_id = conv_id
                best_channel = ch
                best_when = last_at or ''
            break  # items are LastActivityAt DESC — first phone match wins

    return best_id, best_channel


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

    # v19.0.1.48.0: Hatif's timeline API returns lowercase/camelCase
    # keys (items / direction / creationTime), NOT the PascalCase the
    # original code assumed (Items / Direction / CreationTime). With the
    # wrong case ev.get('Direction') was always None, so the inbound
    # filter never matched and this returned None for EVERY conversation
    # — silently breaking the 24h-window refresh. Read lowercase first,
    # fall back to PascalCase for cross-version safety.
    items = None
    if isinstance(resp, dict):
        items = resp.get('items') or resp.get('Items')
    if not items:
        return None

    for ev in items:
        direction = ev.get('direction')
        if direction is None:
            direction = ev.get('Direction')
        if direction != _DIRECTION_INBOUND:
            continue
        when = (
            ev.get('creationTime')
            or ev.get('CreationTime')
        )
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
    # v19.0.1.67.0: LEAD with the phone-matched Hatif lookup rather than
    # trusting partner.x_htf_last_conversation_id. A prior buggy run (the
    # ignored-PhoneNumber-filter, see _lookup_latest_conversation) could
    # have cached an UNRELATED customer's conversation id on the partner;
    # reading its inbound time then wrongly kept the window open. The
    # phone-matched lookup is authoritative. The stored id is only a
    # fallback when the partner has no phone to resolve with.
    resolved_channel = env['htf.channel'].browse()
    convo_id = None
    phone = partner.phone or ''  # Odoo 19 dropped res.partner.mobile
    if phone:
        e164 = normalize_e164(phone)
        if e164:
            convo_id, resolved_channel = _lookup_latest_conversation(env, e164)
    elif partner.x_htf_last_conversation_id:
        convo_id = partner.x_htf_last_conversation_id

    if not convo_id:
        # v19.0.1.67.0: no Hatif conversation matches this phone → the 24h
        # window is closed. Clear any stale "open" stamp so the composer
        # locks. FAIL-CLOSED: requiring a template is always safe, whereas
        # the old fail-open behaviour let agents send into a closed window
        # (and even read an unrelated customer's window — see the
        # PhoneNumber-filter bug in _lookup_latest_conversation). A real
        # inbound webhook re-opens it later.
        _htf_close_channel_window(channel)
        return False

    # v19.0.1.49.0: record which Hatif channel this conversation lives
    # on so a free-form reply sent right after the window opens has a
    # channel to route through (v41 reads channel.x_htf_last_htf_channel_id).
    if resolved_channel and channel and not channel.x_htf_last_htf_channel_id:
        try:
            channel.sudo().write({
                'x_htf_last_htf_channel_id': resolved_channel.id,
            })
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[htf-window] failed to set channel htf_channel for channel=%s",
                getattr(channel, 'id', None),
            )

    latest = get_latest_inbound_at(env, convo_id)
    if not latest:
        # Conversation exists but has no inbound in its recent timeline →
        # window closed. Clear stale stamp (fail-closed, see above).
        _htf_close_channel_window(channel)
        return False

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
    # v19.0.1.67.0: stamp with the REAL last-inbound time whenever we have
    # it (not only when open). If that time is >24h old, the channel's
    # within-24h gate computes closed and OVERWRITES a stale recent stamp
    # — self-healing the wrong-window bug on the next chat open.
    if channel and latest:
        try:
            channel._htf_stamp_inbound_now(when=last_inbound_naive)
        except Exception:  # noqa: BLE001
            _logger.exception(
                "[htf-window] channel stamp failed for channel=%s",
                getattr(channel, 'id', None),
            )
    return open_now

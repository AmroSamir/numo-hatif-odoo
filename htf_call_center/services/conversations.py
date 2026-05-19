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
from typing import Optional

from ..exceptions import HtfApiError
from ..utils.phone import normalize_e164

_logger = logging.getLogger(__name__)


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

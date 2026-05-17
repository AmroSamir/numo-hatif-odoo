"""Channel resolver for outbound WhatsApp + calls (P3 T3.1b).

Picks the right ``htf.channel`` for an outbound action by walking a
deterministic chain so agents never pick a channel manually for the
default case. The chain is locked in 00_OVERVIEW.md §8 and per Q-16
ANSWERED (one channel per sales team, 99% outbound).

Resolution chain for outbound WhatsApp (first match wins):

1. ``lead.team_id.x_htf_default_outbound_wa_channel_id`` (if lead given)
2. ``partner.team_id.x_htf_default_outbound_wa_channel_id`` (if partner has team)
3. ``partner.x_htf_default_channel_id`` (per-partner override)
4. ``sender_user.sale_team_id.x_htf_default_outbound_wa_channel_id``
5. ``htf.config.default_outbound_wa_channel_id`` (workspace fallback)
6. → ``HtfChannelNotFoundError`` with a remediation hint

Outbound calls follow the same chain replacing ``_wa_`` → ``_call_``.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..exceptions import HtfChannelNotFoundError

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------- #
# Public API                                                    #
# ------------------------------------------------------------- #

def resolve_outbound_wa(
    env,
    *,
    partner=None,
    lead=None,
    sender_user=None,
):
    """Return the resolved ``htf.channel`` for an outbound WA send.

    Raises ``HtfChannelNotFoundError`` if no channel can be chosen.
    """
    channel = _walk_chain(env, partner=partner, lead=lead,
                           sender_user=sender_user, mode='wa')
    if not channel:
        raise HtfChannelNotFoundError(_remediation('WhatsApp', partner, lead, sender_user))
    return channel


def resolve_outbound_call(
    env,
    *,
    partner=None,
    lead=None,
    sender_user=None,
):
    """Return the resolved ``htf.channel`` for an outbound call deep-link."""
    channel = _walk_chain(env, partner=partner, lead=lead,
                           sender_user=sender_user, mode='call')
    if not channel:
        raise HtfChannelNotFoundError(_remediation('Call', partner, lead, sender_user))
    return channel


# ------------------------------------------------------------- #
# Internals                                                     #
# ------------------------------------------------------------- #

def _team_default(team, mode: str):
    """Return team's default outbound channel for ``mode`` ('wa' or 'call')."""
    if not team:
        return None
    Channel = team.env['htf.channel']
    field = 'default_for_outbound_wa' if mode == 'wa' else 'default_for_outbound_call'
    return Channel.sudo().search([
        ('team_id', '=', team.id),
        ('state', '=', 'active'),
        (field, '=', True),
    ], limit=1) or None


def _walk_chain(env, *, partner, lead, sender_user, mode: str):
    # 1. Lead's team default.
    if lead and lead.team_id:
        ch = _team_default(lead.team_id, mode)
        if ch:
            return ch

    # 2. Partner's team default (partner sometimes has a team override).
    if partner and getattr(partner, 'team_id', False):
        ch = _team_default(partner.team_id, mode)
        if ch:
            return ch

    # 3. Per-partner override (only meaningful for WA — partners don't
    #    pin call channels in v1).
    if mode == 'wa' and partner and getattr(partner, 'x_htf_default_channel_id', False):
        if partner.x_htf_default_channel_id.state == 'active':
            return partner.x_htf_default_channel_id

    # 4. Sender's team default.
    if sender_user and getattr(sender_user, 'sale_team_id', False):
        ch = _team_default(sender_user.sale_team_id, mode)
        if ch:
            return ch

    # 5. Workspace fallback in htf.config.
    cfg = env['htf.config'].sudo()
    key = 'default_outbound_wa_channel_id' if mode == 'wa' else 'default_outbound_call_channel_id'
    fallback_id = cfg.get_param(key)
    if fallback_id:
        try:
            ch = env['htf.channel'].sudo().browse(int(fallback_id))
            if ch.exists() and ch.state == 'active':
                return ch
        except (TypeError, ValueError):
            pass

    return None


def _remediation(kind: str, partner, lead, sender_user) -> str:
    """Build an actionable error message for the admin."""
    parts = [
        f'No {kind} channel could be resolved for this contact.',
        'Resolution chain (first match wins):',
        '  1. Lead → Team → Default channel',
        '  2. Partner → Team → Default channel',
    ]
    if kind == 'WhatsApp':
        parts.append('  3. Partner override (x_htf_default_channel_id)')
    parts += [
        '  4. Sender user → Team → Default channel',
        f'  5. htf.config workspace fallback',
        '',
        'Fix: open Settings → CRM → Sales Teams, pick the team, '
        f'and set "Default outbound {kind}" to one of the synced Hatif channels.',
    ]
    if partner:
        parts.append(f'Partner: {partner.display_name} (id={partner.id})')
    if lead:
        parts.append(f'Lead: {lead.display_name} (id={lead.id})')
    if sender_user:
        parts.append(f'Sender: {sender_user.display_name} (id={sender_user.id})')
    return '\n'.join(parts)

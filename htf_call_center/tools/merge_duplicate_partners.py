"""Merge duplicate ``res.partner`` records by normalized phone number.

Problem this solves: the Hatif inbound webhook (``services/whatsapp_inbound.py:_resolve_partner``)
only looks up partners by Hatif's ``contactId`` — when an inbound
message arrives for a phone that already has a CRM-side ``res.partner``
(but no ``htf.contact.link`` yet), the resolver auto-creates a NEW
placeholder partner instead of reusing the existing one. Result: the
CRM lead and the Hatif activity sit on two different partner records,
the wizard's 24h-window check looks at the wrong record, and free-form
sends get gated even when the customer has replied.

This tool finds those duplicates by normalized phone, picks a primary
(prefers a record with a non-placeholder readable name; ties broken by
most htf.message activity), reparents htf.message / htf.contact.link /
htf.call / crm.lead / x_htf_discuss_channel_id from the duplicates onto
the primary, then archives the duplicates (we don't ``unlink`` to keep
audit trail intact — ``active=False`` hides them everywhere and is
reversible).

Run via the wrapper:
    bash htf_call_center/tools/merge_duplicate_partners.sh

Env-var knobs:
    HTF_DRY_RUN=1                  → print what would be merged, write nothing
    HTF_PHONE_HINT='+966...'       → only merge partners matching this hint
    HTF_LIMIT=N                    → process at most N phone groups

Idempotent — re-runs find zero remaining duplicates and exit cleanly.
"""

import logging
import os
import re
from collections import defaultdict

_logger = logging.getLogger(__name__)

DRY_RUN = bool(os.environ.get('HTF_DRY_RUN'))
PHONE_HINT = (os.environ.get('HTF_PHONE_HINT') or '').strip()
LIMIT = int(os.environ.get('HTF_LIMIT') or '0') or None


def _norm_phone(raw):
    """Reduce a phone string to digits only, preserving a leading ``+``.

    Doesn't try to add country codes — partners with the same digits
    but different prefixes (e.g. ``5XXXXXXXX`` vs ``+9665XXXXXXXX``) are
    intentionally NOT merged here. Run the canonical
    ``utils.phone.normalize_e164`` on the phone field first if you
    want cross-prefix dedup.
    """
    if not raw:
        return ''
    raw = str(raw).strip()
    if not raw:
        return ''
    digits = re.sub(r'\D+', '', raw)
    if raw.startswith('+'):
        return f'+{digits}'
    return digits


def _pick_primary(group):
    """Choose which partner to keep when merging a duplicate group.

    Preference order:
    1. Partners whose ``name`` does NOT look like a placeholder
       (raw phone, partial UUID, or ``Hatif Contact ...`` pattern).
    2. The one with the most htf.message activity (biggest history).
    3. Lowest id (oldest record).
    """
    def looks_placeholder(p):
        name = (p.name or '').strip()
        if not name:
            return True
        if name.startswith('+'):
            return True
        # 8-char UUID prefix + ellipsis
        if re.match(r'^[0-9a-f]{8}…?$', name):
            return True
        if name.startswith('Hatif Contact '):
            return True
        return False

    env = group[0].env
    Msg = env['htf.message'].sudo()
    counts = {p.id: Msg.search_count([('partner_id', '=', p.id)]) for p in group}
    non_placeholder = [p for p in group if not looks_placeholder(p)]
    pool = non_placeholder or list(group)
    pool.sort(key=lambda p: (-counts[p.id], p.id))
    return pool[0]


def _merge(env, primary, duplicates):
    """Reparent everything from duplicates onto primary, archive dups."""
    if not duplicates:
        return 0
    dup_ids = duplicates.ids
    primary_id = primary.id
    moved = 0

    Msg = env['htf.message'].sudo()
    msgs = Msg.search([('partner_id', 'in', dup_ids)])
    if msgs:
        msgs.write({'partner_id': primary_id})
        moved += len(msgs)

    Call = env['htf.call'].sudo()
    calls = Call.search([('partner_id', 'in', dup_ids)])
    if calls:
        calls.write({'partner_id': primary_id})
        moved += len(calls)

    Link = env['htf.contact.link'].sudo()
    links = Link.search([('partner_id', 'in', dup_ids)])
    for link in links:
        existing_on_primary = Link.search([
            ('partner_id', '=', primary_id),
            ('htf_contact_id', '=', link.htf_contact_id),
        ], limit=1)
        if existing_on_primary:
            link.unlink()
        else:
            link.write({'partner_id': primary_id})
            moved += 1

    leads = env['crm.lead'].sudo().search([('partner_id', 'in', dup_ids)])
    if leads:
        leads.write({'partner_id': primary_id})
        moved += len(leads)

    # Hatif-side denorm fields — copy from the most-recent dup if primary is empty
    for field in (
        'x_htf_last_inbound_at',
        'x_htf_last_conversation_id',
        'x_htf_default_channel_id',
        'x_htf_synced_at',
        'x_htf_contact_id',
        'x_htf_discuss_channel_id',
    ):
        primary_val = getattr(primary, field, None)
        if primary_val:
            continue
        for dup in duplicates:
            dup_val = getattr(dup, field, None)
            if dup_val:
                try:
                    primary.write({
                        field: dup_val.id if hasattr(dup_val, 'id') else dup_val,
                    })
                except Exception:  # noqa: BLE001
                    pass
                break

    duplicates.write({'active': False})
    return moved


def run(env):
    Partner = env['res.partner'].sudo()
    domain = [('phone', '!=', False), ('phone', '!=', ''), ('active', '=', True)]
    if PHONE_HINT:
        digits = re.sub(r'\D+', '', PHONE_HINT)
        domain += ['|', ('phone', 'ilike', PHONE_HINT), ('phone', 'ilike', digits)]
    partners = Partner.search(domain)
    print(f'scanning {len(partners)} active partners with a phone...')

    by_phone = defaultdict(list)
    for p in partners:
        key = _norm_phone(p.phone)
        if not key or len(key) < 6:  # ignore garbage
            continue
        by_phone[key].append(p)

    groups = [g for g in by_phone.values() if len(g) > 1]
    if LIMIT:
        groups = groups[:LIMIT]
    print(f'found {len(groups)} phone(s) with duplicate partners')

    if not groups:
        print('nothing to merge — exiting clean')
        return

    total_moved = 0
    total_archived = 0
    for group in groups:
        # Refresh recordset in case earlier merges affected it
        group_recs = Partner.browse([p.id for p in group]).filtered(lambda r: r.active)
        if len(group_recs) < 2:
            continue
        primary = _pick_primary(group_recs)
        dups = group_recs - primary
        n_msgs_dup = env['htf.message'].sudo().search_count([('partner_id', 'in', dups.ids)])
        print(f'  phone={_norm_phone(primary.phone)!r}  '
              f'keeping id={primary.id} name={primary.name!r}  '
              f'merging {len(dups)} dup(s) (carrying {n_msgs_dup} htf.message(s))')
        if DRY_RUN:
            for d in dups:
                print(f'    [DRY-RUN] would archive id={d.id} name={d.name!r}')
            continue
        moved = _merge(env, primary, dups)
        total_moved += moved
        total_archived += len(dups)

    if DRY_RUN:
        print(f'[DRY-RUN] no writes performed.')
    else:
        env.cr.commit()
        print(f'done — moved {total_moved} child record(s), archived {total_archived} duplicate partner(s).')


# `self` is bound to res.users(uid) inside odoo shell.
try:
    _env = self.env  # type: ignore[name-defined]  # noqa: F821
except NameError:  # pragma: no cover
    _env = None

if _env is None:
    print('ERROR: this script must be run inside `odoo shell`.')
else:
    run(_env)

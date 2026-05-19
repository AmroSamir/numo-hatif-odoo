"""Migration 19.0.1.5.0 — rename placeholder Hatif partners (and their
Discuss channels) to use the phone number as a usable fallback.

Placeholders auto-created from the call + WhatsApp webhooks landed as
'Hatif Contact <uuid-short>...' / 'Hatif Caller <phone>'. The
contactId-short pattern reads as a useless UUID in Discuss / CRM lists.

This migration walks every res.partner whose name matches one of those
two synthetic patterns AND has a phone, and renames:

  partner.name        : 'Hatif Contact 3a210a15…'  ->  '+966500000001'
  discuss.channel.name: 'Hatif Contact 3a210a15…'  ->  '+966500000001'

Idempotent — re-runs leave already-renamed rows alone.
"""

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


_PLACEHOLDER_RE = re.compile(
    r'^(Hatif Contact .+|Hatif Caller .+|Hatif Caller \(unknown\))',
    re.IGNORECASE,
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        renamed_partners = _rename_partners(env)
        renamed_channels = _rename_channels(env)
        _logger.info(
            "[htf-rename] done — partners_renamed=%d channels_renamed=%d",
            renamed_partners, renamed_channels,
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-rename] migration failed — non-fatal")


def _is_placeholder(name):
    if not name:
        return False
    return bool(_PLACEHOLDER_RE.match(name.strip()))


def _better_name(partner):
    """Pick a usable display name for a placeholder partner.

    Phone first. Otherwise, strip the "Hatif Contact " / "Hatif Caller "
    prefix from the existing name and keep just the suffix (uuid short
    or whatever was after the prefix) — the Hatif logo on the avatar
    already conveys "this is a Hatif contact", so the prefix is noise.
    """
    phone = (partner.phone or '').strip()
    if phone:
        return phone
    raw = (partner.name or '').strip()
    for prefix in ('Hatif Contact ', 'Hatif Caller '):
        if raw.startswith(prefix):
            suffix = raw[len(prefix):].strip()
            if suffix:
                return suffix
    return None


def _rename_partners(env):
    Partner = env['res.partner'].sudo()
    partners = Partner.search([('x_htf_discuss_channel_id', '!=', False)])
    count = 0
    for p in partners:
        if not _is_placeholder(p.name):
            continue
        new_name = _better_name(p)
        if not new_name or new_name == p.name:
            continue
        p.write({'name': new_name})
        count += 1
    return count


def _rename_channels(env):
    Ch = env['discuss.channel'].sudo()
    chs = Ch.with_context(active_test=False).search(
        [('x_htf_partner_id', '!=', False)],
    )
    count = 0
    for ch in chs:
        if not ch.x_htf_partner_id:
            continue
        target_name = ch.x_htf_partner_id.display_name or ch.x_htf_partner_id.name
        if not target_name:
            continue
        if ch.name != target_name:
            ch.write({'name': target_name[:200]})
            count += 1
    return count

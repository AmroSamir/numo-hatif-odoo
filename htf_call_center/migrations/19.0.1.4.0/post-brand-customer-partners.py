"""Migration 19.0.1.4.0 — Hatif logo on every Hatif customer partner +
reattribute OdooBot/Public-user mirror messages to the customer.

UAT feedback (Numo, 2026-05-19): the bottom-right Discuss popup
showed mirror bubbles attributed to "OdooBot" with the OdooBot eye
icon. The desired behaviour is that EVERY Hatif-channel bubble
renders with the customer's name and the Hatif logo as avatar.

This migration does three things:

  1. For every res.partner that has an associated Hatif channel
     (x_htf_discuss_channel_id IS NOT NULL) and currently has no
     custom avatar set, write the Hatif logo into image_1920. The
     customer's avatar now renders as the Hatif logo everywhere in
     Odoo (CRM cards, contact lists, AND the Discuss bubbles).

  2. For every mirror mail.message in a Hatif-linked discuss.channel
     whose author_id is OdooBot OR the public-user partner,
     reattribute to the channel's customer partner. The bubble now
     reads with the customer's name and Hatif logo.

  3. Idempotent — re-runs leave already-correct rows alone.
"""

import base64
import logging
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        logo_b64 = _load_logo()
        avatared = _brand_partners(env, logo_b64)
        reattributed = _reattribute_messages(env)
        _logger.info(
            "[htf-brand] done — partners_avatared=%d messages_reattributed=%d",
            avatared, reattributed,
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-brand] migration failed — non-fatal")


def _load_logo():
    here = os.path.dirname(__file__)
    module_root = os.path.abspath(os.path.join(here, '..', '..'))
    png_path = os.path.join(module_root, 'static', 'src', 'img', 'hatif-logo.png')
    if not os.path.isfile(png_path):
        _logger.warning("[htf-brand] hatif-logo.png missing at %s", png_path)
        return None
    with open(png_path, 'rb') as f:
        return base64.b64encode(f.read())


def _brand_partners(env, logo_b64):
    if not logo_b64:
        return 0
    Partner = env['res.partner'].sudo()
    partners = Partner.search([('x_htf_discuss_channel_id', '!=', False)])
    count = 0
    for p in partners:
        if not p.image_1920:
            p.write({'image_1920': logo_b64})
            count += 1
    return count


def _reattribute_messages(env):
    public_partner = env.ref('base.public_partner', raise_if_not_found=False)
    bot_partner = env.ref('base.partner_root', raise_if_not_found=False)
    bad_partner_ids = [p.id for p in (public_partner, bot_partner) if p]
    if not bad_partner_ids:
        return 0

    Channel = env['discuss.channel'].sudo()
    chs = Channel.with_context(active_test=False).search([
        ('x_htf_partner_id', '!=', False),
    ])
    count = 0
    for ch in chs:
        customer_partner_id = ch.x_htf_partner_id.id
        if not customer_partner_id:
            continue
        bad_msgs = env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', ch.id),
            ('message_id', '=like', '<htf-%@htf_call_center>'),
            ('author_id', 'in', bad_partner_ids),
        ])
        for m in bad_msgs:
            m.write({'author_id': customer_partner_id})
            count += 1
    return count

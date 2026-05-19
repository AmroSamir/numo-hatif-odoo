"""Migration 19.0.1.2.0 — strip the 📞 prefix and set the Hatif logo
as the avatar of every existing Hatif Discuss channel.

Earlier (19.0.1.1.0) we set the Hatif logo as the avatar of
`base.public_partner` so any "Public user" fallback bubble looks
branded. With that in place the 📞 emoji prefix on channel names
became redundant — the Hatif logo on the channel itself (image_128)
is a cleaner visual cue in the Discuss sidebar.

This migration:
  1. drops the leading '📞 ' from every channel name where set
  2. writes the Hatif logo bytes to channel.image_128 for every
     Hatif-linked channel that currently has no image set

Idempotent.
"""

import base64
import logging
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return  # fresh-install handled by post_init_hook + create logic
    env = api.Environment(cr, SUPERUSER_ID, {})

    here = os.path.dirname(__file__)
    module_root = os.path.abspath(os.path.join(here, '..', '..'))
    png_path = os.path.join(module_root, 'static', 'src', 'img', 'hatif-logo.png')
    logo_b64 = None
    if os.path.isfile(png_path):
        with open(png_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read())
    else:
        _logger.warning("[htf-rebrand] hatif-logo.png missing at %s", png_path)

    chs = env['discuss.channel'].sudo().with_context(active_test=False).search([
        ('x_htf_partner_id', '!=', False),
    ])
    renamed = 0
    logo_set = 0
    for ch in chs:
        updates = {}
        if ch.name and ch.name.startswith('📞'):
            new_name = ch.name.lstrip('📞 ').strip() or ch.name
            if new_name != ch.name:
                updates['name'] = new_name
        if logo_b64 and not ch.image_128:
            updates['image_128'] = logo_b64
        if updates:
            ch.write(updates)
            if 'name' in updates:
                renamed += 1
            if 'image_128' in updates:
                logo_set += 1
    _logger.info(
        "[htf-rebrand] processed %d channels — renamed=%d logo_applied=%d",
        len(chs), renamed, logo_set,
    )

"""Migration 19.0.1.1.0 — set the Hatif logo as the public partner avatar.

`post_init_hook` only fires on fresh install. For environments where
the module is already installed and the user runs `-u htf_call_center`,
Odoo's migration mechanism (this script) is the canonical way to apply
one-shot data changes.

Odoo runs every `post-*.py` file in
`<module>/migrations/<version>/` after the module's data files are
loaded but before the upgrade commits. The script receives `(cr, version)`.

Idempotent — re-runs leave the same bytes in place.
"""

import base64
import logging
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Fresh install path — post_init_hook handles it
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        partner = env.ref('base.public_partner', raise_if_not_found=False)
        if not partner:
            _logger.warning("[htf-avatar:migration] base.public_partner missing")
            return
        here = os.path.dirname(__file__)
        module_root = os.path.abspath(os.path.join(here, '..', '..'))
        png_path = os.path.join(module_root, 'static', 'src', 'img', 'hatif-logo.png')
        if not os.path.isfile(png_path):
            _logger.warning("[htf-avatar:migration] %s missing", png_path)
            return
        with open(png_path, 'rb') as f:
            new_image = base64.b64encode(f.read())
        if partner.image_1920 == new_image:
            return  # idempotent
        partner.sudo().write({'image_1920': new_image})
        _logger.info(
            "[htf-avatar:migration] public partner avatar set to Hatif logo (%d bytes)",
            len(new_image),
        )
    except Exception:  # noqa: BLE001
        _logger.exception("[htf-avatar:migration] failed — non-fatal")

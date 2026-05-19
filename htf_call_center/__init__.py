from . import constants
from . import exceptions
from . import signals
from . import models
from . import services
from . import controllers
from . import wizards
from . import log_redaction

log_redaction.install()


def _set_public_user_avatar(env):
    """Apply the Hatif logo as the avatar for `base.public_partner`.

    Runs on every install/upgrade. The same logic in
    data/htf_public_user_avatar.xml failed to apply for unknown reasons
    in Odoo 19 — the data file loads but the field=base64/file= path
    doesn't persist the image. Doing it from Python guarantees the bytes
    land in the DB.

    Idempotent: skips when the image is already in place. Best-effort —
    catches and logs any exception so a broken upgrade never hard-fails
    the whole module install.
    """
    import base64
    import logging
    import os
    _logger = logging.getLogger(__name__)
    try:
        partner = env.ref('base.public_partner', raise_if_not_found=False)
        if not partner:
            _logger.warning("[htf-avatar] base.public_partner not found — skipping")
            return
        here = os.path.dirname(__file__)
        path = os.path.join(here, 'static', 'src', 'img', 'hatif-logo.png')
        if not os.path.isfile(path):
            _logger.warning("[htf-avatar] %s missing — skipping", path)
            return
        with open(path, 'rb') as f:
            new_image = base64.b64encode(f.read())
        if partner.image_1920 == new_image:
            return  # idempotent — same bytes already there
        partner.sudo().write({'image_1920': new_image})
        _logger.info(
            "[htf-avatar] base.public_partner avatar set to Hatif logo (%d bytes)",
            len(new_image),
        )
    except Exception:  # noqa: BLE001 — never fail install
        _logger.exception("[htf-avatar] failed to set public partner avatar")


def post_init_hook(env):
    """Module install/upgrade hook."""
    _set_public_user_avatar(env)

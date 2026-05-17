"""Lightweight sync triggers exposed as buttons on `htf.config`.

Lets an admin force a channels/tags/workspace re-sync from the Settings
page or a menu button without going through the cron schedule.
"""

from __future__ import annotations

import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class HtfConfigSync(models.AbstractModel):
    _inherit = 'htf.config'

    @api.model
    def action_sync_channels(self):
        recs = self.get_service('channels').sync_from_htf()
        return self._notify('success', _('Channels synced'),
                            _('%s active channels.') % len(recs))

    @api.model
    def action_sync_tags(self):
        count = self.get_service('tags').sync_from_htf()
        return self._notify('success', _('Tags synced'),
                            _('%s tags synchronised.') % count)

    @api.model
    def action_sync_workspace_users(self):
        links = self.get_service('workspace').sync_users()
        return self._notify('success', _('Workspace users synced'),
                            _('%s user link rows.') % len(links))

    @api.model
    def cron_poll_contacts(self):
        """Cron entry point — implemented in P1.5 as incremental pull.

        For now this is a placeholder no-op; the cron exists so future
        ops scripts depending on it survive the upgrade.
        """
        _logger.debug("[htf] cron_poll_contacts noop until incremental "
                      "delta endpoint is wired (Q-10 follow-up).")
        return 0

    def _notify(self, ntype, title, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': ntype,
                'title': title,
                'message': message,
                'sticky': False,
            },
        }

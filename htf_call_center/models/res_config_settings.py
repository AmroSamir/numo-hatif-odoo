"""Settings → Hatif page.

Mirrors every htf.config parameter to a TransientModel so the standard Odoo
settings view machinery handles save/load via `config_parameter` attribute.
Secret fields are guarded by `group_admin`.
"""

from odoo import fields, models

from ..constants import CONFIG_PARAM_PREFIX


def _p(name: str) -> str:
    return f'{CONFIG_PARAM_PREFIX}{name}'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ---- Connection ----
    htf_client_id = fields.Char(
        string='Client ID',
        config_parameter=_p('client_id'),
        groups='htf_call_center.group_admin',
    )
    htf_client_secret = fields.Char(
        string='Client Secret',
        config_parameter=_p('client_secret'),
        groups='htf_call_center.group_admin',
    )
    htf_base_url = fields.Char(
        string='Base URL',
        config_parameter=_p('base_url'),
        default='https://api.voxa.sa',
        groups='htf_call_center.group_admin',
    )
    htf_scope = fields.Char(
        string='OAuth Scope',
        config_parameter=_p('scope'),
        default='VoxaAPI',
        groups='htf_call_center.group_admin',
    )

    # ---- Webhook secrets (HMAC) ----
    htf_webhook_secret_current = fields.Char(
        string='Webhook Secret (current)',
        config_parameter=_p('webhook_secret_current'),
        groups='htf_call_center.group_admin',
    )
    htf_webhook_secret_previous = fields.Char(
        string='Webhook Secret (previous)',
        config_parameter=_p('webhook_secret_previous'),
        groups='htf_call_center.group_admin',
        help='Rotation overlap window — kept valid for 7 days after rotation.',
    )

    # ---- Polling ----
    htf_poll_contacts_interval_min = fields.Integer(
        string='Contacts Poll Interval (min)',
        config_parameter=_p('poll_contacts_interval_min'),
        default=30,
        groups='htf_call_center.group_admin',
    )
    htf_poll_conversations_interval_min = fields.Integer(
        string='Conversations Poll Interval (min)',
        config_parameter=_p('poll_conversations_interval_min'),
        default=15,
        groups='htf_call_center.group_admin',
    )

    # ---- Defaults ----
    htf_default_voice = fields.Selection(
        selection=[('male', 'Male'), ('female', 'Female')],
        string='Default TTS Voice',
        config_parameter=_p('default_voice'),
        default='female',
        groups='htf_call_center.group_admin',
    )
    htf_timezone_offset_for_filters = fields.Char(
        string='Timezone Offset (for Hatif filters)',
        config_parameter=_p('timezone_offset_for_filters'),
        default='+03:00',
        groups='htf_call_center.group_admin',
    )

    # ---- Debug ----
    htf_debug_log_enabled = fields.Boolean(
        string='Debug Logging',
        config_parameter=_p('debug_log_enabled'),
        default=False,
        groups='htf_call_center.group_admin',
        help='When ON, log full request/response bodies. Secrets stripped.',
    )

    # ---- Dev mode flag (must stay OFF in production) ----
    htf_dev_mode_skip_hmac = fields.Boolean(
        string='DEV MODE — skip webhook HMAC',
        config_parameter=_p('dev_mode_skip_hmac'),
        default=False,
        groups='htf_call_center.group_admin',
        help='Local development only. MUST be OFF in production — verified '
             'in the pre-prod checklist.',
    )

    # ---- Test Connection button ----
    def action_test_connection(self):
        # Persist any unsaved values first (Odoo wizard pattern).
        self.execute()
        return self.env['htf.config'].action_test_connection()

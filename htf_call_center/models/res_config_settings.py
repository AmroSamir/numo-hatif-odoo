"""Settings → Hatif page.

Mirrors every htf.config parameter to a TransientModel so the standard Odoo
settings view machinery handles save/load via `config_parameter` attribute.
Secret fields are guarded by `group_admin`.
"""

from odoo import api, fields, models

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

    # ---- Webhook URLs (read-only; what to paste into the Hatif portal) ----
    # Derived from web.base.url so dev / staging / prod each show their own
    # absolute URL. Not stored — every load recomputes from the system
    # parameter so an admin changing web.base.url is reflected instantly.
    htf_webhook_url_call = fields.Char(
        string='Post-call Webhook URL',
        compute='_compute_htf_webhook_urls',
        help='Paste this into app.hatif.io → Settings → API Connect → '
             '<each channel> → Post-call Webhook URL.',
    )
    htf_webhook_url_whatsapp = fields.Char(
        string='WhatsApp Webhook URL',
        compute='_compute_htf_webhook_urls',
        help='Paste this into app.hatif.io → Settings → API Connect → '
             '<each channel> → WhatsApp Webhook URL.',
    )

    @api.depends_context('uid')
    def _compute_htf_webhook_urls(self):
        base = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        for rec in self:
            rec.htf_webhook_url_call = (
                f'{base}/htf/webhook/call' if base else ''
            )
            rec.htf_webhook_url_whatsapp = (
                f'{base}/htf/webhook/whatsapp' if base else ''
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

    # ---- HMAC kill switch ----
    # Defaults to True because Hatif's live webhook deliveries do NOT
    # include the X-Voxa-Signature header (see
    # docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md). With this OFF,
    # every inbound call/WhatsApp event is rejected at the HMAC gate
    # and the integration looks broken. Admins should flip it OFF the
    # moment Hatif enables signing AND the Webhook Secrets (above) are
    # configured per channel.
    htf_dev_mode_skip_hmac = fields.Boolean(
        string='Skip webhook HMAC verification',
        config_parameter=_p('dev_mode_skip_hmac'),
        default=True,
        groups='htf_call_center.group_admin',
        help='When ON, inbound webhooks are accepted without checking the '
             'HMAC signature. Required today because Hatif does not yet '
             'include X-Voxa-Signature on deliveries. Flip OFF once Hatif '
             'turns on signing and the per-channel Webhook Secrets above '
             'are set. Defence-in-depth recommendation: allowlist Hatif '
             "source IP (8.213.48.16) on your reverse proxy while this is ON.",
    )

    # ------------------------------------------------------------------ #
    # Buttons on the Settings page                                        #
    # ------------------------------------------------------------------ #
    # Odoo resolves `<button name="X" type="object"/>` against the form's
    # MODEL (here res.config.settings), so we expose thin wrappers that
    # delegate to htf.config. Each one saves the form first so any newly
    # pasted creds / secrets are persisted before the call goes out.

    def action_test_connection(self):
        self.execute()
        return self.env['htf.config'].action_test_connection()

    def action_sync_channels(self):
        self.execute()
        return self.env['htf.config'].action_sync_channels()

    def action_sync_tags(self):
        self.execute()
        return self.env['htf.config'].action_sync_tags()

    def action_sync_workspace_users(self):
        self.execute()
        return self.env['htf.config'].action_sync_workspace_users()

"""htf.config — singleton-style configuration + service factory.

The actual values live in `ir.config_parameter` (so they survive module
upgrade and don't add a custom table). This AbstractModel just exposes a
typed accessor and the `get_service(name)` factory documented in
API_CONTRACT.md.

Usage from anywhere in Odoo:

    token = env['htf.config'].get_service('auth').get_token()
    client = env['htf.config'].get_service('http')
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from odoo import _, api, models
from odoo.exceptions import UserError

from ..constants import (
    CONFIG_PARAM_PREFIX,
    SERVICE_AUTH,
    SERVICE_HTTP,
    TOKEN_REFRESH_LEEWAY_SECONDS,
)
from ..exceptions import HtfConfigError

_logger = logging.getLogger(__name__)


# Internal map of every config key the wrapper understands, with default
# value and a coercion function (string from ir.config_parameter → typed).
# Keys WITHOUT the module prefix; `_param_key` adds it.
_PARAM_SCHEMA = {
    # Connection
    'client_id': ('', str),
    'client_secret': ('', str),
    'base_url': ('https://api.voxa.sa', str),
    'scope': ('VoxaAPI', str),
    # Webhook signing — per-channel webhookSecret with rotation overlap.
    'webhook_secret_current': ('', str),
    'webhook_secret_previous': ('', str),
    # OAuth token cache
    'token_cache': ('', str),
    'token_expires_at': ('', str),  # ISO 8601 in UTC
    # Polling intervals (minutes)
    'poll_contacts_interval_min': ('30', int),
    'poll_conversations_interval_min': ('15', int),
    # Defaults / UX
    'default_voice': ('female', str),
    'timezone_offset_for_filters': ('+03:00', str),
    'debug_log_enabled': ('False', lambda v: v == 'True'),
    # P0.5 dev-mode skip-HMAC flag; default OFF. Defined here so production
    # checklists can verify it. Webhook controllers honor it in later phases.
    'dev_mode_skip_hmac': ('False', lambda v: v == 'True'),
    # P2 opt-out detector — comma-separated keywords; empty = use defaults.
    'dnc_keywords': ('', str),
    # P3 outbound safety gate. Default OFF so dev/UAT never spams real
    # customers; admin flips ON in Settings per environment (dev/staging/prod).
    'allow_real_outbound': ('False', lambda v: v == 'True'),
    # P3 outbound phone whitelist (comma-separated E.164). When non-empty
    # AND allow_real_outbound is ON, only listed destinations receive
    # real HTTP sends; everything else falls back to dry-run.
    'outbound_phone_whitelist': ('', str),
    # P3 outbound channel resolver — workspace-wide fallback when no team
    # chain matches. Stored as integer id of htf.channel (or empty).
    'default_outbound_wa_channel_id': ('', str),
    'default_outbound_call_channel_id': ('', str),
    # P7 — Mirror Hatif activity into per-partner discuss.channel rows so
    # Odoo's native Discuss popup becomes the conversation surface.
    # Master flag + 4 per-feature sub-flags. ALL default OFF — the module
    # is shipping behaviour-neutral and is opted-in per environment via
    # Settings → Technical → Parameters (or the helper method below).
    # Toggle the master flag OFF to instantly disable every P7 codepath.
    'discuss_mirror_enabled': ('False', lambda v: v == 'True'),
    'discuss_mirror_inbound': ('False', lambda v: v == 'True'),
    'discuss_mirror_calls': ('False', lambda v: v == 'True'),
    'discuss_outbound_route': ('False', lambda v: v == 'True'),
    'discuss_ui_override': ('False', lambda v: v == 'True'),
    # v19.0.1.35.0 — Discuss-first WhatsApp UX (Option C).
    # When ON, the WhatsApp buttons on partner / lead forms open the
    # per-partner Hatif Discuss popup instead of the Send wizard, and
    # the composer disables free-form text when Meta's 24h window is
    # closed (showing a "Send Template" button that launches the
    # existing wizard in template mode).
    # This master toggle ALSO acts as a runtime override for the four
    # mirror sub-flags above: when True, ``discuss_mirror_active``
    # returns True regardless of the underlying stored sub-flag values
    # (sub-flag rows are left untouched, so toggling this OFF restores
    # whatever the admin previously chose).
    'whatsapp_button_opens_discuss': ('True', lambda v: v == 'True'),
}


def _param_key(short_name: str) -> str:
    return f'{CONFIG_PARAM_PREFIX}{short_name}'


class HtfConfig(models.AbstractModel):
    _name = 'htf.config'
    _description = 'HTF Call Center — Configuration & Service Factory'

    # ------------------------------------------------------------------ #
    # Param accessors                                                    #
    # ------------------------------------------------------------------ #

    @api.model
    def get_param(self, name: str):
        """Typed accessor for a single configuration parameter."""
        if name not in _PARAM_SCHEMA:
            raise HtfConfigError(_('Unknown htf.config parameter: %s') % name)
        default, coerce = _PARAM_SCHEMA[name]
        raw = self.env['ir.config_parameter'].sudo().get_param(_param_key(name), default)
        try:
            return coerce(raw)
        except (TypeError, ValueError):
            _logger.warning(
                "[htf] config param %s has invalid value %r, returning default",
                name, raw,
            )
            return coerce(default)

    @api.model
    def set_param(self, name: str, value) -> None:
        if name not in _PARAM_SCHEMA:
            raise HtfConfigError(_('Unknown htf.config parameter: %s') % name)
        # Stored as string in ir.config_parameter. Booleans become 'True'/'False'.
        stored = '' if value is None else str(value)
        self.env['ir.config_parameter'].sudo().set_param(_param_key(name), stored)

    @api.model
    def get_all_params(self) -> dict:
        """Snapshot of every parameter (for debug + test fixtures)."""
        return {name: self.get_param(name) for name in _PARAM_SCHEMA}

    # ------------------------------------------------------------------ #
    # P7 — Discuss mirror feature-flag helper                             #
    # ------------------------------------------------------------------ #

    @api.model
    def discuss_mirror_active(self, sub_flag: str | None = None) -> bool:
        """True iff the master flag AND (optionally) the named sub-flag are on.

        Every P7 codepath must call this in its first line and bail out if
        False. With the master flag off the module behaves exactly like
        the pre-P7 codebase (commit 0a4d674).

        Known sub-flag names: 'inbound', 'calls', 'outbound', 'ui'.
        Pass None to check only the master flag.

        v19.0.1.35.0: ``whatsapp_button_opens_discuss`` acts as a runtime
        override — when True it forces the master + every sub-flag to
        be reported active without mutating the stored sub-flag rows.
        Admins who toggle the discuss-first UX off get back exactly the
        granular state they had before.
        """
        if self.get_param('whatsapp_button_opens_discuss'):
            # The discuss-first UX requires every mirror codepath to be
            # active, so treat the override as covering the master and
            # every sub-flag without touching their stored values.
            return True
        if not self.get_param('discuss_mirror_enabled'):
            return False
        if sub_flag is None:
            return True
        key = {
            'inbound': 'discuss_mirror_inbound',
            'calls': 'discuss_mirror_calls',
            'outbound': 'discuss_outbound_route',
            'ui': 'discuss_ui_override',
        }.get(sub_flag)
        if key is None:
            raise HtfConfigError(_('Unknown discuss sub-flag: %s') % sub_flag)
        return bool(self.get_param(key))

    # ------------------------------------------------------------------ #
    # Token cache helpers (auth service uses these)                       #
    # ------------------------------------------------------------------ #

    @api.model
    def get_cached_token(self) -> tuple[str, datetime | None]:
        token = self.get_param('token_cache')
        raw_expiry = self.env['ir.config_parameter'].sudo().get_param(
            _param_key('token_expires_at'), ''
        )
        expires_at = None
        if raw_expiry:
            try:
                expires_at = datetime.fromisoformat(raw_expiry)
            except ValueError:
                expires_at = None
        return token, expires_at

    @api.model
    def cache_token(self, token: str, expires_in_seconds: int) -> None:
        expires_at = datetime.utcnow() + timedelta(
            seconds=max(0, int(expires_in_seconds) - TOKEN_REFRESH_LEEWAY_SECONDS)
        )
        self.set_param('token_cache', token)
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_expires_at'), expires_at.isoformat()
        )

    @api.model
    def clear_cached_token(self) -> None:
        self.set_param('token_cache', '')
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_expires_at'), ''
        )

    # ------------------------------------------------------------------ #
    # Webhook secrets (HMAC verifier reads these)                        #
    # ------------------------------------------------------------------ #

    @api.model
    def webhook_secrets(self) -> list[str]:
        """Return [current, previous] — non-empty only. Used by hmac_verify."""
        out = []
        for key in ('webhook_secret_current', 'webhook_secret_previous'):
            val = self.get_param(key)
            if val:
                out.append(val)
        return out

    # ------------------------------------------------------------------ #
    # Service factory                                                    #
    # ------------------------------------------------------------------ #

    @api.model
    def get_service(self, name: str):
        """Return a service instance bound to the current env.

        Public surface — bridges and other consumers MUST use this rather
        than importing service modules directly. See API_CONTRACT.md.
        """
        factory = _SERVICE_REGISTRY.get(name)
        if factory is None:
            raise HtfConfigError(
                _('Unknown HTF service %r. Known: %s')
                % (name, sorted(_SERVICE_REGISTRY))
            )
        return factory(self.env)

    # ------------------------------------------------------------------ #
    # Test Connection action (Settings UI button)                         #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Cron entry points                                                   #
    # ------------------------------------------------------------------ #
    # Odoo's safe_eval forbids `import` inside ir.cron `state='code'`
    # bodies, so the cron XML calls `model.<method>()` and the method
    # delegates to the service.

    @api.model
    def cron_refresh_token(self) -> None:
        from ..services.auth import AuthService
        AuthService.cron_refresh(self.env)

    @api.model
    def action_test_connection(self) -> dict:
        """Acquire a token against Hatif and return a user-facing notification."""
        if not self.get_param('client_id') or not self.get_param('client_secret'):
            raise UserError(_('Set client_id and client_secret first.'))
        try:
            auth = self.get_service('auth')
            token = auth.refresh_token()
        except Exception as exc:  # surface concise message
            _logger.exception("[htf] test connection failed")
            raise UserError(
                _('Connection to Hatif failed: %s') % exc
            ) from exc

        # Note: never name a throwaway variable `_` in a method that also
        # calls the gettext `_()`. Python scope-analyses any assignment to
        # `_` as a local, which then shadows the imported function across
        # the whole method body (UnboundLocalError on earlier _() calls).
        _cached_token, expires_at = self.get_cached_token()
        expires_in = ''
        if expires_at:
            delta = expires_at - datetime.utcnow()
            mins = max(0, int(delta.total_seconds() // 60))
            expires_in = _(' Expires in %s min.') % mins

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Hatif connected'),
                'message': _('Token acquired (%(prefix)s…).%(expiry)s') % {
                    'prefix': token[:8] if token else '?',
                    'expiry': expires_in,
                },
                'sticky': False,
            },
        }


# ---------------------------------------------------------------------- #
# Service registry                                                       #
# ---------------------------------------------------------------------- #
# Populated by services/__init__.py at module load. Kept here so the
# factory method above can resolve services without importing service
# modules at class-definition time (avoids circular imports).

_SERVICE_REGISTRY: dict[str, callable] = {}


def register_service(name: str, factory) -> None:
    """Register a service factory. Called from services/__init__.py."""
    _SERVICE_REGISTRY[name] = factory

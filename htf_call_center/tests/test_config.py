"""htf.config — param accessors, token cache, service factory, settings UI."""

from datetime import datetime, timedelta

from odoo.exceptions import UserError

from .common import HtfTransactionCase
from ..exceptions import HtfConfigError
from ..services.auth import AuthService
from ..services.http_client import HtfHttpClient


class TestHtfConfig(HtfTransactionCase):

    # ---- get_param / set_param ----

    def test_get_unknown_param_raises(self):
        with self.assertRaises(HtfConfigError):
            self.HtfConfig.get_param('nonexistent_thing')

    def test_set_unknown_param_raises(self):
        with self.assertRaises(HtfConfigError):
            self.HtfConfig.set_param('nope', 'x')

    def test_int_coercion(self):
        self.HtfConfig.set_param('poll_contacts_interval_min', '45')
        self.assertEqual(self.HtfConfig.get_param('poll_contacts_interval_min'), 45)

    def test_int_coercion_invalid_falls_back_to_default(self):
        from ..models.htf_config import _param_key
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('poll_contacts_interval_min'), 'notanumber'
        )
        self.assertEqual(self.HtfConfig.get_param('poll_contacts_interval_min'), 30)

    def test_bool_coercion(self):
        self.HtfConfig.set_param('debug_log_enabled', True)
        self.assertIs(self.HtfConfig.get_param('debug_log_enabled'), True)
        self.HtfConfig.set_param('debug_log_enabled', False)
        self.assertIs(self.HtfConfig.get_param('debug_log_enabled'), False)

    def test_get_all_params_returns_full_snapshot(self):
        snap = self.HtfConfig.get_all_params()
        self.assertIn('client_id', snap)
        self.assertIn('base_url', snap)
        self.assertIn('webhook_secret_current', snap)

    # ---- token cache ----

    def test_token_cache_roundtrip(self):
        self.HtfConfig.cache_token('abc.def.ghi', 600)
        token, expires_at = self.HtfConfig.get_cached_token()
        self.assertEqual(token, 'abc.def.ghi')
        self.assertIsNotNone(expires_at)
        self.assertGreater(expires_at, datetime.utcnow())
        # leeway applied → not the full 600s
        self.assertLess(expires_at, datetime.utcnow() + timedelta(seconds=600))

    def test_clear_cached_token(self):
        self.HtfConfig.cache_token('x', 600)
        self.HtfConfig.clear_cached_token()
        token, expires_at = self.HtfConfig.get_cached_token()
        self.assertEqual(token, '')
        self.assertIsNone(expires_at)

    def test_cache_token_short_ttl_still_returns_expiry(self):
        self.HtfConfig.cache_token('x', 30)  # less than leeway
        _, expires_at = self.HtfConfig.get_cached_token()
        self.assertIsNotNone(expires_at)

    # ---- webhook secrets ----

    def test_webhook_secrets_returns_non_empty_only(self):
        self.HtfConfig.set_param('webhook_secret_current', 'c')
        self.HtfConfig.set_param('webhook_secret_previous', '')
        self.assertEqual(self.HtfConfig.webhook_secrets(), ['c'])
        self.HtfConfig.set_param('webhook_secret_previous', 'p')
        self.assertEqual(self.HtfConfig.webhook_secrets(), ['c', 'p'])
        self.HtfConfig.set_param('webhook_secret_current', '')
        self.assertEqual(self.HtfConfig.webhook_secrets(), ['p'])

    # ---- service factory ----

    def test_get_service_auth_returns_auth_service(self):
        svc = self.HtfConfig.get_service('auth')
        self.assertIsInstance(svc, AuthService)

    def test_get_service_http_returns_http_client(self):
        svc = self.HtfConfig.get_service('http')
        self.assertIsInstance(svc, HtfHttpClient)

    def test_get_service_unknown_raises(self):
        with self.assertRaises(HtfConfigError):
            self.HtfConfig.get_service('nonexistent-service')

    # ---- test connection action ----

    def test_action_test_connection_requires_credentials(self):
        self.HtfConfig.set_param('client_id', '')
        with self.assertRaises(UserError):
            self.HtfConfig.action_test_connection()

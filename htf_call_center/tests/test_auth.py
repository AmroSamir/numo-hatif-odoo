"""Auth service — token cache, refresh, 401 invalidation, cron."""

from datetime import datetime, timedelta
from unittest.mock import patch

import requests

from .common import HtfTransactionCase
from ..exceptions import HtfAuthenticationError, HtfConfigError, HtfServerError
from ..services.auth import AuthService, cron_refresh_token


class TestAuthService(HtfTransactionCase):

    def setUp(self):
        super().setUp()
        self.svc = self.HtfConfig.get_service('auth')

    def test_get_token_returns_cached_when_valid(self):
        self.seed_valid_token('cached-tok', ttl_seconds=3600)
        with patch('requests.post') as p:
            token = self.svc.get_token()
        self.assertEqual(token, 'cached-tok')
        p.assert_not_called()

    def test_get_token_refreshes_when_expired(self):
        self.seed_expired_token('old-tok')
        with self.patch_requests_post(
            response=self.fake_response(
                200, {'access_token': 'fresh-tok', 'expires_in': 3600}
            )
        ):
            token = self.svc.get_token()
        self.assertEqual(token, 'fresh-tok')

    def test_get_token_refreshes_when_missing(self):
        self.HtfConfig.clear_cached_token()
        with self.patch_requests_post(
            response=self.fake_response(
                200, {'access_token': 'new-tok', 'expires_in': 1800}
            )
        ):
            token = self.svc.get_token()
        self.assertEqual(token, 'new-tok')

    def test_refresh_token_persists_to_cache(self):
        with self.patch_requests_post(
            response=self.fake_response(
                200, {'access_token': 'persisted', 'expires_in': 600}
            )
        ):
            self.svc.refresh_token()
        cached, expires_at = self.HtfConfig.get_cached_token()
        self.assertEqual(cached, 'persisted')
        self.assertIsNotNone(expires_at)

    def test_refresh_token_missing_credentials_raises(self):
        self.HtfConfig.set_param('client_id', '')
        with self.assertRaises(HtfConfigError):
            self.svc.refresh_token()

    def test_refresh_token_non_200_raises_auth_error(self):
        with self.patch_requests_post(
            response=self.fake_response(401, text_body='bad creds')
        ):
            with self.assertRaises(HtfAuthenticationError):
                self.svc.refresh_token()

    def test_refresh_token_missing_access_token_raises(self):
        with self.patch_requests_post(
            response=self.fake_response(200, {'expires_in': 600})
        ):
            with self.assertRaises(HtfAuthenticationError):
                self.svc.refresh_token()

    def test_refresh_token_transport_error_raises_server_error(self):
        with self.patch_requests_post(
            side_effect=requests.exceptions.ConnectionError('boom')
        ):
            with self.assertRaises(HtfServerError):
                self.svc.refresh_token()

    def test_invalidate_token_clears_cache(self):
        self.seed_valid_token('to-be-cleared')
        self.svc.invalidate_token()
        cached, _ = self.HtfConfig.get_cached_token()
        self.assertEqual(cached, '')

    def test_cron_no_op_when_no_token(self):
        self.HtfConfig.clear_cached_token()
        with patch('requests.post') as p:
            cron_refresh_token(self.env)
        p.assert_not_called()

    def test_cron_no_op_when_token_fresh(self):
        self.seed_valid_token('still-good', ttl_seconds=3600)
        with patch('requests.post') as p:
            cron_refresh_token(self.env)
        p.assert_not_called()

    def test_cron_refreshes_when_token_about_to_expire(self):
        # Set token with very near expiry.
        from ..models.htf_config import _param_key
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_cache'), 'about-to-die'
        )
        soon = datetime.utcnow() + timedelta(seconds=60)
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_expires_at'), soon.isoformat()
        )
        with self.patch_requests_post(
            response=self.fake_response(
                200, {'access_token': 'reborn', 'expires_in': 3600}
            )
        ) as p:
            cron_refresh_token(self.env)
        p.assert_called_once()
        cached, _ = self.HtfConfig.get_cached_token()
        self.assertEqual(cached, 'reborn')

    def test_cron_clears_token_with_missing_expiry(self):
        from ..models.htf_config import _param_key
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_cache'), 'orphan'
        )
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_expires_at'), ''
        )
        cron_refresh_token(self.env)
        cached, _ = self.HtfConfig.get_cached_token()
        self.assertEqual(cached, '')

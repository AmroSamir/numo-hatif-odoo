"""Shared test base classes + helpers for htf_call_center.

All tests inherit from `HtfTransactionCase`, which:

- seeds `htf.config` with fake credentials so services don't blow up
- exposes `set_param` / `get_param` shortcuts
- isolates the signal bus across tests so subscribers don't leak between cases
- exposes a helper to issue a fake `requests`-like response (no network)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

from ..signals import htf_signals


@tagged('-at_install', 'post_install', 'htf_p0')
class HtfTransactionCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.HtfConfig = cls.env['htf.config']
        cls.HtfConfig.set_param('client_id', 'test-client')
        cls.HtfConfig.set_param('client_secret', 'test-secret')
        cls.HtfConfig.set_param('base_url', 'https://api.example.test')
        cls.HtfConfig.set_param('scope', 'VoxaAPI')
        cls.HtfConfig.set_param('webhook_secret_current', 'whsec-current')
        cls.HtfConfig.set_param('webhook_secret_previous', '')
        cls.HtfConfig.set_param('debug_log_enabled', False)
        cls.HtfConfig.clear_cached_token()

    def setUp(self):
        super().setUp()
        # Snapshot + restore the signal registry so tests can subscribe freely.
        self._signal_snapshot = {k: list(v) for k, v in htf_signals._subs.items()}
        self.addCleanup(self._restore_signals)

    def _restore_signals(self):
        htf_signals.clear()
        for name, callbacks in self._signal_snapshot.items():
            for cb in callbacks:
                htf_signals.subscribe(name, cb)

    # ------------------------------------------------------------------ #
    # `requests` mocking helpers                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def fake_response(status_code=200, json_body=None, text_body=None, headers=None):
        resp = MagicMock()
        resp.status_code = status_code
        if json_body is not None:
            payload = json.dumps(json_body)
            resp.content = payload.encode('utf-8')
            resp.text = payload
            resp.json.return_value = json_body
            resp.headers = {'Content-Type': 'application/json', **(headers or {})}
        elif text_body is not None:
            resp.content = text_body.encode('utf-8')
            resp.text = text_body
            resp.headers = headers or {}
            resp.json.side_effect = ValueError('not json')
        else:
            resp.content = b''
            resp.text = ''
            resp.headers = headers or {}
            resp.json.side_effect = ValueError('not json')
        return resp

    @contextmanager
    def patch_requests_request(self, side_effect=None, responses=None):
        """Patch `requests.request` with either a side_effect or an
        iterable of canned responses returned in order.
        """
        with patch('requests.request') as mocked:
            if responses is not None:
                mocked.side_effect = list(responses)
            elif side_effect is not None:
                mocked.side_effect = side_effect
            yield mocked

    @contextmanager
    def patch_requests_post(self, response=None, side_effect=None):
        with patch('requests.post') as mocked:
            if response is not None:
                mocked.return_value = response
            if side_effect is not None:
                mocked.side_effect = side_effect
            yield mocked

    # ------------------------------------------------------------------ #
    # Token shortcuts                                                     #
    # ------------------------------------------------------------------ #

    def seed_valid_token(self, value='cached-token', ttl_seconds=3600):
        self.HtfConfig.cache_token(value, ttl_seconds)

    def seed_expired_token(self, value='expired-token'):
        # Force an expiry in the past via ir.config_parameter directly.
        from ..models.htf_config import _param_key
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_cache'), value
        )
        past = datetime.utcnow() - timedelta(minutes=10)
        self.env['ir.config_parameter'].sudo().set_param(
            _param_key('token_expires_at'), past.isoformat()
        )

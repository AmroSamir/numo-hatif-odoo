"""HTTP client wrapper — retry budget, 401 refresh, typed exception mapping."""

from unittest.mock import patch

import requests

from .common import HtfTransactionCase
from ..exceptions import (
    HtfAuthenticationError,
    HtfAuthorizationError,
    HtfNotFoundError,
    HtfRateLimitError,
    HtfServerError,
    HtfValidationError,
)


class TestHttpClient(HtfTransactionCase):

    def setUp(self):
        super().setUp()
        self.client = self.HtfConfig.get_service('http')
        # Pre-seed a valid token so the client doesn't trigger a real /connect/token POST.
        self.seed_valid_token('fake-token', ttl_seconds=3600)

    def test_successful_get_returns_parsed_json(self):
        with self.patch_requests_request(
            responses=[self.fake_response(200, {'ok': True})]
        ):
            result = self.client.get('/v1/health')
        self.assertEqual(result, {'ok': True})

    def test_successful_post_returns_parsed_json(self):
        with self.patch_requests_request(
            responses=[self.fake_response(200, {'id': 'abc'})]
        ) as mocked:
            result = self.client.post('/v1/things', json_body={'name': 'x'})
        self.assertEqual(result, {'id': 'abc'})
        # Bearer + UA injected on the wire.
        call_kwargs = mocked.call_args.kwargs
        self.assertEqual(call_kwargs['headers']['Authorization'], 'Bearer fake-token')
        self.assertIn('HtfCallCenter', call_kwargs['headers']['User-Agent'])

    def test_post_form_uses_data(self):
        with self.patch_requests_request(
            responses=[self.fake_response(200, {'ok': True})]
        ) as mocked:
            self.client.post_form('/whatever', data={'a': 1})
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['data'], {'a': 1})
        self.assertIsNone(kwargs['json'])

    def test_401_invalidates_and_retries_once_then_succeeds(self):
        # First call: 401 → invalidate token + retry. Second call: 200.
        with self.patch_requests_request(
            responses=[
                self.fake_response(401),
                self.fake_response(200, {'recovered': True}),
            ]
        ):
            # Mock refresh_token so retry doesn't hit network.
            with patch.object(
                self.HtfConfig.get_service('auth').__class__,
                'refresh_token',
                return_value='fresh-tok',
            ):
                self.seed_valid_token('initial', ttl_seconds=10)
                result = self.client.get('/v1/x')
        self.assertEqual(result, {'recovered': True})

    def test_401_persistent_raises_auth_error(self):
        with self.patch_requests_request(
            responses=[self.fake_response(401), self.fake_response(401), self.fake_response(401)]
        ):
            with patch.object(
                self.HtfConfig.get_service('auth').__class__,
                'refresh_token',
                return_value='still-bad',
            ):
                with self.assertRaises(HtfAuthenticationError):
                    self.client.get('/v1/x')

    def test_5xx_retries_then_succeeds(self):
        with patch('time.sleep'):
            with self.patch_requests_request(
                responses=[
                    self.fake_response(503, text_body='upstream down'),
                    self.fake_response(200, {'ok': True}),
                ]
            ):
                result = self.client.get('/v1/x')
        self.assertEqual(result, {'ok': True})

    def test_5xx_persistent_raises_server_error(self):
        with patch('time.sleep'):
            with self.patch_requests_request(
                responses=[
                    self.fake_response(500),
                    self.fake_response(502),
                    self.fake_response(503),
                ]
            ):
                with self.assertRaises(HtfServerError):
                    self.client.get('/v1/x')

    def test_4xx_not_retried(self):
        with self.patch_requests_request(
            responses=[self.fake_response(400, text_body='bad shape')]
        ) as mocked:
            with self.assertRaises(HtfValidationError):
                self.client.post('/v1/x', json_body={'a': 1})
        self.assertEqual(mocked.call_count, 1)

    def test_403_raises_authorization_error(self):
        with self.patch_requests_request(
            responses=[self.fake_response(403, text_body='nope')]
        ):
            with self.assertRaises(HtfAuthorizationError):
                self.client.get('/v1/secret')

    def test_404_raises_not_found_error(self):
        with self.patch_requests_request(
            responses=[self.fake_response(404, text_body='gone')]
        ):
            with self.assertRaises(HtfNotFoundError):
                self.client.get('/v1/missing')

    def test_429_with_retry_after_eventually_raises(self):
        with patch('time.sleep'):
            with self.patch_requests_request(
                responses=[
                    self.fake_response(429, headers={'Retry-After': '1'}),
                    self.fake_response(429),
                    self.fake_response(429),
                ]
            ):
                with self.assertRaises(HtfRateLimitError):
                    self.client.get('/v1/x')

    def test_connection_error_retries_then_raises_server_error(self):
        with patch('time.sleep'):
            with self.patch_requests_request(
                side_effect=[
                    requests.exceptions.ConnectionError('no route'),
                    requests.exceptions.ConnectionError('still no route'),
                    requests.exceptions.ConnectionError('really no route'),
                ]
            ):
                with self.assertRaises(HtfServerError):
                    self.client.get('/v1/x')

    def test_empty_response_returns_none(self):
        with self.patch_requests_request(
            responses=[self.fake_response(200)]
        ):
            result = self.client.get('/v1/empty')
        self.assertIsNone(result)

    def test_non_json_content_returns_text(self):
        with self.patch_requests_request(
            responses=[self.fake_response(200, text_body='hello world',
                                          headers={'Content-Type': 'text/plain'})]
        ):
            result = self.client.get('/v1/text')
        self.assertEqual(result, 'hello world')

    def test_request_id_propagates_to_exception(self):
        with self.patch_requests_request(
            responses=[
                self.fake_response(400, text_body='bad',
                                   headers={'X-Request-Id': 'req-xyz'})
            ]
        ):
            try:
                self.client.get('/v1/x')
            except HtfValidationError as exc:
                self.assertEqual(exc.request_id, 'req-xyz')
            else:
                self.fail('expected HtfValidationError')

    def test_base_url_required(self):
        self.HtfConfig.set_param('base_url', '')
        with self.assertRaises(Exception):
            self.client.get('/v1/x')

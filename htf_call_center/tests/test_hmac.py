"""HMAC verifier — 100% coverage target per P0."""

import hashlib
import hmac

from .common import HtfTransactionCase
from ..services import hmac_verify
from ..constants import WEBHOOK_SIGNATURE_HEADER


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


class TestHmacVerify(HtfTransactionCase):

    def test_valid_signature_passes(self):
        body = b'{"hello": "world"}'
        sig = _sign('whsec-current', body)
        self.assertTrue(hmac_verify.verify(body, sig, ['whsec-current']))

    def test_invalid_signature_fails(self):
        body = b'{"hello": "world"}'
        self.assertFalse(
            hmac_verify.verify(body, 'deadbeef', ['whsec-current'])
        )

    def test_missing_signature_fails(self):
        body = b'{"hello": "world"}'
        self.assertFalse(hmac_verify.verify(body, '', ['whsec-current']))
        self.assertFalse(hmac_verify.verify(body, None, ['whsec-current']))

    def test_no_secret_fails(self):
        body = b'x'
        sig = _sign('whsec-current', body)
        self.assertFalse(hmac_verify.verify(body, sig, []))
        self.assertFalse(hmac_verify.verify(body, sig, ['']))

    def test_rotation_overlap_accepts_previous(self):
        body = b'{"a": 1}'
        sig_with_old = _sign('whsec-previous', body)
        self.assertTrue(
            hmac_verify.verify(body, sig_with_old, ['whsec-current', 'whsec-previous'])
        )

    def test_uppercase_signature_normalized(self):
        body = b'x'
        sig = _sign('whsec-current', body).upper()
        self.assertTrue(hmac_verify.verify(body, sig, ['whsec-current']))

    def test_sha256_prefix_tolerated(self):
        body = b'x'
        sig = 'sha256=' + _sign('whsec-current', body)
        self.assertTrue(hmac_verify.verify(body, sig, ['whsec-current']))

    def test_string_body_accepted(self):
        body_str = '{"hello": "world"}'
        sig = _sign('whsec-current', body_str.encode('utf-8'))
        self.assertTrue(
            hmac_verify.verify(body_str, sig, ['whsec-current'])
        )

    def test_empty_body_with_correct_sig_passes(self):
        body = b''
        sig = _sign('whsec-current', body)
        self.assertTrue(hmac_verify.verify(body, sig, ['whsec-current']))

    def test_verify_from_request_reads_config_secrets(self):
        body = b'{"x": 1}'
        sig = _sign('whsec-current', body)
        headers = {WEBHOOK_SIGNATURE_HEADER: sig}
        self.assertTrue(
            hmac_verify.verify_from_request(self.env, body, headers)
        )

    def test_verify_from_request_lowercase_header(self):
        body = b'{"x": 1}'
        sig = _sign('whsec-current', body)
        headers = {WEBHOOK_SIGNATURE_HEADER.lower(): sig}
        self.assertTrue(
            hmac_verify.verify_from_request(self.env, body, headers)
        )

    def test_verify_from_request_no_signature_header(self):
        self.assertFalse(
            hmac_verify.verify_from_request(self.env, b'x', {})
        )

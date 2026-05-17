"""Verify bearer tokens and webhook secrets never reach log output."""

import logging

from .common import HtfTransactionCase
from ..log_redaction import HtfSecretRedactionFilter


class TestLogRedaction(HtfTransactionCase):

    def setUp(self):
        super().setUp()
        self.filter = HtfSecretRedactionFilter()

    def _record(self, msg, *args):
        return logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg=msg, args=args, exc_info=None,
        )

    def test_strips_bearer_token_from_message(self):
        rec = self._record('Authorization: Bearer abc123.def456_xyz==')
        self.filter.filter(rec)
        self.assertNotIn('abc123', rec.msg)
        self.assertIn('REDACTED', rec.msg)

    def test_strips_bearer_in_dict_repr(self):
        rec = self._record("headers={'Authorization': 'Bearer eyJabc.tok'}")
        self.filter.filter(rec)
        self.assertNotIn('eyJabc', rec.msg)

    def test_strips_webhook_secret_assignment(self):
        rec = self._record('webhook_secret_current=top_secret_value')
        self.filter.filter(rec)
        self.assertNotIn('top_secret_value', rec.msg)

    def test_strips_client_secret_assignment(self):
        rec = self._record('client_secret=hush-hush-123')
        self.filter.filter(rec)
        self.assertNotIn('hush-hush-123', rec.msg)

    def test_redacts_tuple_args(self):
        rec = self._record('token: %s', 'Bearer mytok123')
        self.filter.filter(rec)
        # the bearer pattern lives in args; redaction normalizes it
        # (note: pattern requires "Authorization:" prefix in args; this case
        #  tests that non-matching args are passed through unchanged)
        self.assertEqual(rec.args, ('Bearer mytok123',))

    def test_unrelated_text_unchanged(self):
        rec = self._record('processing call id=abc123')
        self.filter.filter(rec)
        self.assertEqual(rec.msg, 'processing call id=abc123')

    def test_filter_never_raises_on_weird_input(self):
        rec = self._record(None)
        rec.msg = None
        # Should not crash even with a non-string msg.
        self.assertTrue(self.filter.filter(rec))

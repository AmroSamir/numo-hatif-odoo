"""Exception hierarchy — class identity + attribute carrying."""

from .common import HtfTransactionCase
from ..exceptions import (
    HtfApiError,
    HtfAuthenticationError,
    HtfAuthorizationError,
    HtfChannelNotFoundError,
    HtfDncBlockedError,
    HtfNotFoundError,
    HtfNotMappedError,
    HtfRateLimitError,
    HtfServerError,
    HtfValidationError,
    HtfWindowExpiredError,
)


class TestExceptions(HtfTransactionCase):

    def test_all_inherit_from_base(self):
        for cls in (
            HtfAuthenticationError, HtfAuthorizationError, HtfNotFoundError,
            HtfRateLimitError, HtfServerError, HtfValidationError,
            HtfDncBlockedError, HtfWindowExpiredError, HtfNotMappedError,
            HtfChannelNotFoundError,
        ):
            self.assertTrue(issubclass(cls, HtfApiError), cls)

    def test_carries_status_and_body(self):
        exc = HtfValidationError('bad body', status=422, body='nope', request_id='r1')
        self.assertEqual(exc.status, 422)
        self.assertEqual(exc.body, 'nope')
        self.assertEqual(exc.request_id, 'r1')
        self.assertIn('bad body', str(exc))

    def test_rate_limit_carries_retry_after(self):
        exc = HtfRateLimitError('slow down', retry_after=42, status=429)
        self.assertEqual(exc.retry_after, 42)
        self.assertEqual(exc.status, 429)

    def test_dnc_carries_phone(self):
        exc = HtfDncBlockedError('blocked', phone='+966500000000')
        self.assertEqual(exc.phone, '+966500000000')

    def test_window_carries_partner(self):
        partner = self.env['res.partner'].create({'name': 'x'})
        exc = HtfWindowExpiredError('expired', partner=partner)
        self.assertEqual(exc.partner, partner)

    def test_not_mapped_carries_user(self):
        exc = HtfNotMappedError('no x_htf_user_id', user=self.env.user)
        self.assertEqual(exc.user, self.env.user)

    def test_repr_shape(self):
        exc = HtfAuthorizationError('forbidden', status=403, request_id='r9')
        rep = repr(exc)
        self.assertIn('HtfAuthorizationError', rep)
        self.assertIn('403', rep)
        self.assertIn('r9', rep)

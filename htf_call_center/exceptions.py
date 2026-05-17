"""Public exception hierarchy raised by the HTF Call Center service layer.

The bridge module catches these by class. Adding new subclasses is non-breaking;
removing or renaming an existing one is a MAJOR version bump per API_CONTRACT.md.
"""


class HtfApiError(Exception):
    """Base class for every error raised by the vendor wrapper."""

    def __init__(self, message='', *, status=None, body=None, request_id=None):
        super().__init__(message or self.__class__.__name__)
        self.message = message
        self.status = status
        self.body = body
        self.request_id = request_id

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(status={self.status!r}, "
            f"request_id={self.request_id!r}, message={self.message!r})"
        )


class HtfAuthenticationError(HtfApiError):
    """401 from Hatif — token rejected and refresh failed."""


class HtfAuthorizationError(HtfApiError):
    """403 from Hatif — token valid but operation not permitted."""


class HtfNotFoundError(HtfApiError):
    """404 from Hatif — resource missing."""


class HtfRateLimitError(HtfApiError):
    """429 from Hatif — back off per retry_after seconds."""

    def __init__(self, message='', *, retry_after=None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class HtfServerError(HtfApiError):
    """5xx from Hatif — retried per RETRY_BUDGET then surfaced."""


class HtfValidationError(HtfApiError):
    """4xx other than 401/403/404/429 — request shape rejected."""


class HtfDncBlockedError(HtfApiError):
    """Local pre-check: destination number is on the do-not-contact list."""

    def __init__(self, message='', *, phone=None, dnc_row=None, **kwargs):
        super().__init__(message, **kwargs)
        self.phone = phone
        self.dnc_row = dnc_row


class HtfWindowExpiredError(HtfApiError):
    """Local pre-check: 24h Meta window expired, free-form text not allowed."""

    def __init__(self, message='', *, partner=None, last_inbound_at=None, **kwargs):
        super().__init__(message, **kwargs)
        self.partner = partner
        self.last_inbound_at = last_inbound_at


class HtfNotMappedError(HtfApiError):
    """res.users has no x_htf_user_id — admin must run the mapping wizard."""

    def __init__(self, message='', *, user=None, **kwargs):
        super().__init__(message, **kwargs)
        self.user = user


class HtfChannelNotFoundError(HtfApiError):
    """No active htf.channel resolves for the requested send."""


class HtfWebhookSignatureError(HtfApiError):
    """HMAC verification failed on an inbound webhook request."""


class HtfConfigError(HtfApiError):
    """Settings are missing or malformed — surface clearly to admin."""

"""OAuth client_credentials flow against Hatif/Voxa.

Hatif's `/connect/token` endpoint accepts client_id + client_secret +
grant_type=client_credentials + scope and returns an access_token with a
TTL (typically 1h). We cache the token in `htf.config` so concurrent
workers share it across the Odoo cluster.

The cron `htf.cron.refresh_token` proactively refreshes when < 5 minutes
remain. The HTTP client also calls `invalidate_token()` + retries once on
a 401, so a token revoked mid-flight self-heals.

Concurrent-refresh storm protection: we wrap the refresh path in a
PostgreSQL advisory lock keyed on the module name. The cluster sees at
most one refresh per moment; everyone else reads the cache after.
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urljoin

import requests

from ..constants import (
    TIMEOUT_CONNECT_SECONDS,
    TIMEOUT_READ_SECONDS,
    TOKEN_CRON_REFRESH_THRESHOLD_SECONDS,
    USER_AGENT,
)
from ..exceptions import (
    HtfAuthenticationError,
    HtfConfigError,
    HtfServerError,
)

_logger = logging.getLogger(__name__)

# Postgres advisory lock: arbitrary 64-bit int, unique per process concern.
# Computed as a hash of a stable string; reused below.
_TOKEN_LOCK_KEY = 0x68_74_66_61_75_74_68_00  # 'htfauth\0' in hex bytes
_TOKEN_ENDPOINT = '/connect/token'


class AuthService:
    """Service factory target. Bound to a specific Odoo env."""

    name = 'auth'

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------ #
    # Public surface — used by HTTP client and by the Test Connection btn #
    # ------------------------------------------------------------------ #

    def get_token(self) -> str:
        """Return a valid bearer token, refreshing transparently if needed."""
        token, expires_at = self.env['htf.config'].get_cached_token()
        if token and expires_at and expires_at > datetime.utcnow():
            return token
        return self.refresh_token()

    def refresh_token(self) -> str:
        """Force a token refresh via /connect/token. Caches on success."""
        config = self.env['htf.config']
        client_id = config.get_param('client_id')
        client_secret = config.get_param('client_secret')
        base_url = config.get_param('base_url')
        scope = config.get_param('scope')

        if not client_id or not client_secret:
            raise HtfConfigError(
                'client_id and client_secret must be set in Settings → Hatif'
            )

        # Cluster-wide single-flight: another worker may already be refreshing.
        # If we can't acquire the advisory lock, just re-read the cache once
        # (the other worker should have just finished).
        acquired = self._try_advisory_lock()
        try:
            if not acquired:
                token, expires_at = config.get_cached_token()
                if token and expires_at and expires_at > datetime.utcnow():
                    return token
                # No fresh token in cache → fall through and refresh ourselves.

            url = urljoin(base_url.rstrip('/') + '/', _TOKEN_ENDPOINT.lstrip('/'))
            try:
                resp = requests.post(
                    url,
                    data={
                        'grant_type': 'client_credentials',
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'scope': scope or 'VoxaAPI',
                    },
                    headers={
                        'Accept': 'application/json',
                        'User-Agent': USER_AGENT,
                    },
                    timeout=(TIMEOUT_CONNECT_SECONDS, TIMEOUT_READ_SECONDS),
                )
            except requests.exceptions.RequestException as exc:
                _logger.warning("[htf] token refresh transport error: %s", exc)
                raise HtfServerError(
                    'Could not reach Hatif token endpoint',
                    body=str(exc),
                ) from exc

            if resp.status_code != 200:
                body_text = (resp.text or '')[:500]
                _logger.warning(
                    "[htf] token refresh failed status=%s body=%s",
                    resp.status_code, body_text,
                )
                raise HtfAuthenticationError(
                    f'Hatif rejected credentials (HTTP {resp.status_code})',
                    status=resp.status_code,
                    body=body_text,
                )

            payload = resp.json() if resp.content else {}
            token = payload.get('access_token')
            expires_in = int(payload.get('expires_in') or 0)
            if not token or expires_in <= 0:
                raise HtfAuthenticationError(
                    'Hatif token response missing access_token or expires_in',
                    body=str(payload)[:500],
                )
            config.cache_token(token, expires_in)
            _logger.info("[htf] token refreshed, expires_in=%ss", expires_in)
            return token
        finally:
            if acquired:
                self._release_advisory_lock()

    def invalidate_token(self) -> None:
        """Drop the cached token so the next get_token() forces a refresh."""
        self.env['htf.config'].clear_cached_token()

    # ------------------------------------------------------------------ #
    # Cron entry point                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def cron_refresh(cls, env) -> None:
        """Scheduled refresh — runs every 30 min if token expires soon."""
        token, expires_at = env['htf.config'].get_cached_token()
        if not token:
            return
        if expires_at is None:
            env['htf.config'].clear_cached_token()
            return
        seconds_left = (expires_at - datetime.utcnow()).total_seconds()
        if seconds_left > TOKEN_CRON_REFRESH_THRESHOLD_SECONDS:
            return
        cls(env).refresh_token()

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _try_advisory_lock(self) -> bool:
        try:
            self.env.cr.execute(
                "SELECT pg_try_advisory_xact_lock(%s)", (_TOKEN_LOCK_KEY,)
            )
            row = self.env.cr.fetchone()
            return bool(row and row[0])
        except Exception:  # pragma: no cover — pg always supports this
            return True  # degrade to non-locking refresh rather than break

    def _release_advisory_lock(self) -> None:
        # `pg_try_advisory_xact_lock` releases at transaction end, so no
        # explicit release call is needed. Method kept for symmetry / future
        # session-level lock variant.
        return


def cron_refresh_token(env):
    """Module-level cron target referenced from data/ir_cron.xml."""
    AuthService.cron_refresh(env)

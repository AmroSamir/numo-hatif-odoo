"""Authenticated HTTP client for Hatif/Voxa.

Wraps ``requests`` with:

- automatic bearer-token injection (via AuthService)
- 3-attempt exponential backoff on 5xx + ConnectionError
- single-shot retry on 401 after invalidating + refreshing the token
- typed exception mapping (per API_CONTRACT.md error model)
- a debug-mode flag that logs full request/response, with secrets stripped
- standard User-Agent and connect/read timeouts

The bridge never instantiates this directly; it goes through
``env['htf.config'].get_service('http')`` (or, more commonly, a higher-level
service that wraps this).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping
from urllib.parse import urljoin

import requests

from ..constants import (
    RETRY_BACKOFF_SECONDS,
    RETRY_BUDGET,
    TIMEOUT_CONNECT_SECONDS,
    TIMEOUT_READ_SECONDS,
    USER_AGENT,
)
from ..exceptions import (
    HtfApiError,
    HtfAuthenticationError,
    HtfAuthorizationError,
    HtfNotFoundError,
    HtfRateLimitError,
    HtfServerError,
    HtfValidationError,
)

_logger = logging.getLogger(__name__)


class HtfHttpClient:
    """Service factory target. Bound to a specific Odoo env."""

    name = 'http'

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------ #
    # Public methods                                                      #
    # ------------------------------------------------------------------ #

    def get(self, path: str, *, params=None, headers=None) -> Any:
        return self._request('GET', path, params=params, headers=headers)

    def post(self, path: str, *, json_body=None, headers=None) -> Any:
        return self._request('POST', path, json_body=json_body, headers=headers)

    def put(self, path: str, *, json_body=None, headers=None) -> Any:
        return self._request('PUT', path, json_body=json_body, headers=headers)

    def delete(self, path: str, *, params=None, headers=None) -> Any:
        return self._request('DELETE', path, params=params, headers=headers)

    def post_form(self, path: str, *, data: Mapping, headers=None) -> Any:
        return self._request('POST', path, form_data=data, headers=headers)

    # ------------------------------------------------------------------ #
    # Core request loop                                                   #
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        form_data: Mapping | None = None,
        params: Mapping | None = None,
        headers: Mapping | None = None,
    ):
        url = self._absolute_url(path)
        auth_service = self.env['htf.config'].get_service('auth')
        debug = self.env['htf.config'].get_param('debug_log_enabled')

        last_exc: Exception | None = None
        for attempt in range(RETRY_BUDGET):
            token = auth_service.get_token()
            req_headers = self._build_headers(token, headers)

            if debug:
                self._log_request(method, url, req_headers, json_body, form_data, params)

            try:
                resp = requests.request(
                    method,
                    url,
                    headers=req_headers,
                    params=params,
                    json=json_body if form_data is None else None,
                    data=form_data,
                    timeout=(TIMEOUT_CONNECT_SECONDS, TIMEOUT_READ_SECONDS),
                )
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                _logger.warning(
                    "[htf] %s %s transport error attempt=%s: %s",
                    method, _safe_url(url), attempt + 1, exc,
                )
                if attempt < RETRY_BUDGET - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise HtfServerError(
                    f'Transport failed against {_safe_url(url)}',
                    body=str(exc),
                ) from exc

            if debug:
                self._log_response(resp)

            # 401 → invalidate + retry ONCE.
            if resp.status_code == 401 and attempt == 0:
                _logger.info("[htf] 401 on %s, invalidating token and retrying", path)
                auth_service.invalidate_token()
                continue

            # Retry on 5xx (idempotent boundary). For 429, honor Retry-After
            # once when possible.
            if resp.status_code >= 500 and attempt < RETRY_BUDGET - 1:
                _logger.warning(
                    "[htf] %s %s status=%s attempt=%s — retrying",
                    method, _safe_url(url), resp.status_code, attempt + 1,
                )
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue

            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers.get('Retry-After'))
                if attempt < RETRY_BUDGET - 1:
                    _logger.warning(
                        "[htf] 429 from Hatif, sleeping %ss before retry",
                        retry_after or RETRY_BACKOFF_SECONDS[attempt],
                    )
                    time.sleep(retry_after or RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise HtfRateLimitError(
                    'Hatif rate limit exceeded',
                    status=429,
                    retry_after=retry_after,
                    body=(resp.text or '')[:500],
                )

            # Map 4xx/5xx to typed exceptions; otherwise return parsed body.
            if 200 <= resp.status_code < 300:
                return self._parse_response(resp)

            self._raise_for_status(method, url, resp)

        # Loop exhausted without success
        raise HtfServerError(
            f'Retries exhausted against {_safe_url(url)}',
            body=str(last_exc) if last_exc else None,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _absolute_url(self, path: str) -> str:
        base = self.env['htf.config'].get_param('base_url') or ''
        if not base:
            raise HtfApiError('base_url is not configured')
        return urljoin(base.rstrip('/') + '/', path.lstrip('/'))

    def _build_headers(self, token: str, extra: Mapping | None) -> dict:
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}',
            'User-Agent': USER_AGENT,
        }
        if extra:
            headers.update({k: v for k, v in extra.items() if v is not None})
        return headers

    def _parse_response(self, resp):
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if not resp.content:
            return None
        if 'application/json' in ctype:
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return resp.text

    def _raise_for_status(self, method, url, resp) -> None:
        body = (resp.text or '')[:500]
        request_id = resp.headers.get('X-Request-Id') or resp.headers.get('x-request-id')
        status = resp.status_code
        common = {'status': status, 'body': body, 'request_id': request_id}
        if status == 401:
            raise HtfAuthenticationError(
                f'{method} {_safe_url(url)} unauthorized', **common
            )
        if status == 403:
            raise HtfAuthorizationError(
                f'{method} {_safe_url(url)} forbidden', **common
            )
        if status == 404:
            raise HtfNotFoundError(
                f'{method} {_safe_url(url)} not found', **common
            )
        if 400 <= status < 500:
            raise HtfValidationError(
                f'{method} {_safe_url(url)} rejected', **common
            )
        if status >= 500:
            raise HtfServerError(
                f'{method} {_safe_url(url)} server error', **common
            )
        raise HtfApiError(
            f'{method} {_safe_url(url)} unexpected status {status}', **common
        )

    def _log_request(self, method, url, headers, json_body, form_data, params):
        # log_redaction.py strips Authorization values; safe to log headers.
        try:
            body_repr = json.dumps(json_body)[:500] if json_body is not None else None
            form_repr = dict(form_data) if form_data else None
            _logger.info(
                "[htf] >>> %s %s headers=%s params=%s json=%s form=%s",
                method, _safe_url(url), headers, params, body_repr, form_repr,
            )
        except Exception:  # pragma: no cover — never crash on logging
            pass

    def _log_response(self, resp):
        try:
            _logger.info(
                "[htf] <<< status=%s len=%s body=%s",
                resp.status_code,
                len(resp.content or b''),
                (resp.text or '')[:500],
            )
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------- #
# Helpers reused outside the class                                       #
# ---------------------------------------------------------------------- #

def _parse_retry_after(value):
    if not value:
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _safe_url(url: str) -> str:
    # `requests` never embeds bearer tokens in the URL, but defensive in case
    # a query string later carries a token-ish value. Keep this trivial for now.
    return url

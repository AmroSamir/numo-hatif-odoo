#!/usr/bin/env python3
"""Replay a fixture WhatsApp webhook against a local Odoo (P2 T2.7).

Useful for:

- Reproducing bug reports from Hatif team — paste their payload into a
  ``.json`` file and replay it locally
- Driving E2E tests during P2/P3/P4 work without registering a real
  Hatif webhook URL
- Smoke-checking signature rotation: pass ``--secret old-secret`` to
  confirm the previous-secret slot still verifies

Usage::

    # Send a single fixture with current webhook secret
    python3 -m htf_call_center.tools.replay_webhook \\
        --url http://localhost:8069 \\
        --db  odoo \\
        --login admin --password admin \\
        --secret p2-test-secret \\
        --payload fixtures/inbound_text.json

    # All flags except --payload have env-var defaults.

The script auths once, signs each payload with HMAC-SHA256, POSTs to
``<url>/htf/webhook/whatsapp``, and reports status + response body.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request


def _login(opener, base_url: str, db: str, login: str, password: str) -> dict:
    """Authenticate against /web/session/authenticate. Required so the
    multi-db host knows which db to dispatch the webhook to.
    """
    body = json.dumps({
        'jsonrpc': '2.0',
        'params': {'db': db, 'login': login, 'password': password},
    }).encode()
    req = urllib.request.Request(
        f'{base_url}/web/session/authenticate',
        data=body, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=10) as resp:
        return json.loads(resp.read())


def replay(
    payload: dict | bytes,
    *,
    url: str,
    secret: str,
    opener: urllib.request.OpenerDirector,
    timeout: float = 10.0,
) -> tuple[int, str]:
    """POST a signed payload to ``<url>/htf/webhook/whatsapp``.

    ``payload`` may be a dict (will be JSON-serialised) or raw bytes
    (sent as-is — useful when reproducing a Hatif-captured body byte
    for byte, since signature must match the raw bytes).
    """
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload, ensure_ascii=False).encode()
    elif isinstance(payload, bytes):
        body = payload
    else:
        raise TypeError(f'unsupported payload type: {type(payload).__name__}')
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        f'{url}/htf/webhook/whatsapp',
        data=body, method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Voxa-Signature': sig,
        },
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        body_resp = exc.read() or b''
        return exc.code, body_resp.decode('utf-8', errors='replace')


def _build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--url',
                    default=os.environ.get('HTF_URL', 'http://localhost:8069'),
                    help='Odoo base URL (default: http://localhost:8069)')
    ap.add_argument('--db', default=os.environ.get('HTF_DB', 'odoo'))
    ap.add_argument('--login', default=os.environ.get('HTF_LOGIN', 'admin'))
    ap.add_argument('--password', default=os.environ.get('HTF_PASSWORD', 'admin'))
    ap.add_argument('--secret', default=os.environ.get('HTF_WEBHOOK_SECRET', 'p2-test-secret'),
                    help='HMAC secret matching htf.config.webhook_secret_current')
    ap.add_argument('--payload', required=True,
                    help='Path to JSON fixture (use - for stdin)')
    ap.add_argument('--no-login', action='store_true',
                    help='Skip /web/session/authenticate (useful on single-db hosts)')
    args = ap.parse_args(argv)

    # Read payload.
    if args.payload == '-':
        raw_text = sys.stdin.read()
    else:
        with open(args.payload, 'r', encoding='utf-8') as fh:
            raw_text = fh.read()
    payload = json.loads(raw_text)

    # Auth + replay.
    opener = _build_opener()
    if not args.no_login:
        auth = _login(opener, args.url, args.db, args.login, args.password)
        if not (auth.get('result') or {}).get('uid'):
            print('LOGIN FAILED', file=sys.stderr)
            print(json.dumps(auth, indent=2), file=sys.stderr)
            return 2
    status, body = replay(payload, url=args.url, secret=args.secret, opener=opener)

    print(f'status: {status}')
    print(f'body:   {body!r}')
    return 0 if 200 <= status < 300 else 1


if __name__ == '__main__':
    raise SystemExit(main())

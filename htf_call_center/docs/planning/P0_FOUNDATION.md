# Phase P0 — Foundation

**Module:** `htf_call_center`
**Effort:** 6–10 dev hrs
**Depends on:** none
**Blocks:** all later phases

## Goal

Stand up the empty-but-correct vendor wrapper module: scaffolding, settings, auth, HTTP client, HMAC verifier, signal bus, error model. No business endpoints yet.

## Blocked-by

- Q-03 (HMAC header name + format) — required before T0.6 finalizes
- Q-22 (concurrent webhook delivery rate) — informs T0.4 retry budget tuning

## Mitigates

- R-02 (Webhook spoof) → T0.6 + T0.11
- R-03 (Token leak) → T0.4 + T0.8
- R-05 (numo_crm modified) → T0.10 (CI rule)

## Acceptance criteria

- [ ] Module installs + uninstalls cleanly on staging
- [ ] `Settings → Hatif` page renders with credentials fields (encrypted)
- [ ] `Test Connection` button posts to `/connect/token` with creds and returns success
- [ ] Token cached in `htf.config.token_cache` with `token_expires_at`
- [ ] HTTP client retries on 5xx (3 attempts, exponential backoff), refreshes token on 401
- [ ] HMAC verifier with timestamp window passes valid sigs and rejects invalid
- [ ] Signal bus accepts subscribers + fires synchronously
- [ ] Custom log filter strips `Authorization: Bearer ...` headers
- [ ] 100% coverage on `auth` and `hmac_verify` modules
- [ ] Pylint custom rule installed (blocks bridge importing wrapper internals)

## Tasks

### T0.1 — Scaffolding (1h)
- Create `htf_call_center/` skeleton
- `__manifest__.py` (depends: base, mail, contacts)
- `__init__.py` files
- Empty dirs: models/, services/, controllers/, wizards/, data/, security/, views/, static/, tests/
- `security/security_groups.xml` with `group_user`, `group_admin`
- `security/ir.model.access.csv` (empty placeholder)

### T0.2 — `htf.config` model (1.5h)
- Singleton via `ir.config_parameter` pattern
- Fields per DATA_MODEL.md: client_id, client_secret, base_url, scope, webhook_secret_current/previous, token_cache, token_expires_at, default_voice, timezone_offset_for_filters, debug_log_enabled
- `get_service(name)` factory returning typed service instances
- View: Settings → Hatif page with grouped sections (Connection, Webhooks, Defaults)
- Encryption via `groups='htf_call_center.group_admin'` field-level groups

### T0.3 — Auth service (1.5h)
- `services/auth.py` with `AuthService(env)` class
- `get_token()`: returns cached token if valid, else refresh
- `refresh_token()`: POST `/connect/token` form-encoded with creds; persist response + expiry
- `invalidate_token()`: clears cache (called on 401)
- Lock to prevent concurrent refresh storm
- Cron `htf.cron.refresh_token` (every 30 min, refreshes if < 5 min to expiry)
- Tests: 100% coverage including network failure, 401, expired, valid cache

### T0.4 — HTTP client wrapper (1.5h)
- `services/http_client.py` with `HtfHttpClient(env)` class
- Methods: `get`, `post`, `put`, `delete`, `post_form`
- Retry policy: 3 attempts, exponential backoff (1s, 2s, 4s) on 5xx + ConnectionError
- 401 → refresh token + retry once
- Timeout 30s read, 5s connect
- Custom User-Agent
- Logger redacts `Authorization: Bearer...` and `webhook_secret*`
- Raises typed exceptions from API_CONTRACT.md error model
- Tests: timeout, retry, no-retry-on-4xx, refresh-on-401, redaction

### T0.5 — Exceptions module (0.5h)
- `exceptions.py` with `HtfApiError` base + all subclasses from API_CONTRACT.md
- Each carries `status`, `body`, `request_id`, `message`

### T0.6 — HMAC verifier (1h)
- `services/hmac_verify.py`
- `verify(timestamp, body, signature, *, secrets=[current, previous]) -> bool`
- Timestamp window check (±5 min, configurable via constant)
- Tries each secret; returns True on first match
- `compare_digest` for timing safety
- Tests: 100% — valid, missing sig, wrong sig, expired ts, future ts, rotation overlap

### T0.7 — Signal bus (1h)
- `signals.py` with `htf_signals` singleton
- API: `subscribe(name, callback)`, `fire(name, payload)`, `unsubscribe(name, callback)`
- Synchronous, in-process, error-propagating
- `register_hook` integration (subscribes when models load)
- Tests: registration, firing, unsubscribe, error propagation

### T0.8 — Logger setup (0.5h)
- Custom logging.Filter class redacting bearer tokens + secrets
- Wired into `__init__.py` boot
- Test: feed a log line with bearer → assert redacted

### T0.9 — Test infrastructure (1h)
- `tests/__init__.py`
- `tests/common.py` — `HtfTransactionCase` base with config seeded
- `tests/fixtures/` dir
- `tests/test_auth.py`, `tests/test_http_client.py`, `tests/test_hmac.py`, `tests/test_signals.py`
- `responses` library for HTTP mocking
- `freezegun` for time mocking

### T0.10 — Pylint custom rule (1h)
- `tools/pylint_htf_no_internal_import.py`
- **Blocks** `from htf_call_center.services.* import` in any non-htf_call_center package
- **Allowlist** (legitimate cross-module imports for the bridge):
  - `from htf_call_center.signals import htf_signals`
  - `from htf_call_center.exceptions import HtfApiError, HtfDncBlockedError, ...`
  - `from htf_call_center.constants import *`
  - `env['htf.config'].get_service('<name>')` for everything else
- Also blocks any edit to `numo_crm/*` from PRs not labelled `crm-core`
- CI step: `pylint --load-plugins=tools.pylint_htf_no_internal_import numo_crm_htf/`
- Doc in CONTRIBUTING.md

### T0.11 — `htf.webhook.event` model + cron (0.5h)
- Create `htf.webhook.event` per DATA_MODEL.md (event_id, route, received_at, processed, payload_hash, UNIQUE (event_id, route))
- Cron `htf.cron.purge_webhook_events` (nightly 03:00) archives rows older than 90 days
- Used by P2/P4/P5 webhook controllers for idempotency — owning phase = P0 (foundation)
- Tests: dedup, archive

### T0.12 — Record rules baseline (0.5h)
- `security/record_rules.xml` baseline rules (empty domain for admin, restricted for user)
- Each model later phases ship adds to this file via xpath in their phase task
- Tests: admin sees all, user sees only own

### T0.13 — Settings UI test (0.5h)
- Manual: open Settings → Hatif, fill creds, click Test Connection, see success toast
- Document UAT steps in P0_UAT_CHECKLIST below

## P0 UAT checklist

1. [ ] Install module on fresh staging DB
2. [ ] Open Settings → Hatif
3. [ ] Enter `client_id`, `client_secret` (real Hatif creds)
4. [ ] Set `base_url` to Hatif sandbox if available, else prod
5. [ ] Save
6. [ ] Click Test Connection → green toast "Token acquired, expires in N minutes"
7. [ ] Check logs: no secret leaks
8. [ ] Toggle `debug_log_enabled`, repeat → verify body logs masked
9. [ ] Wait 30 min → verify cron refreshed token
10. [ ] Uninstall module → DB clean, no residual rows in `ir.config_parameter` namespace

## Files delivered

```
htf_call_center/
├── __manifest__.py
├── __init__.py
├── exceptions.py
├── constants.py
├── signals.py
├── tools/
│   └── pylint_htf_no_internal_import.py
├── models/
│   ├── __init__.py
│   ├── htf_config.py
│   └── htf_webhook_event.py
├── services/
│   ├── __init__.py
│   ├── auth.py
│   ├── http_client.py
│   └── hmac_verify.py
├── data/
│   └── ir_cron.xml         # token refresh cron
├── security/
│   ├── ir.model.access.csv
│   ├── security_groups.xml
│   └── record_rules.xml
├── views/
│   └── res_config_settings.xml
└── tests/
    ├── __init__.py
    ├── common.py
    ├── test_auth.py
    ├── test_http_client.py
    ├── test_hmac.py
    └── test_signals.py
```

## Done definition

- All tasks complete + tested + reviewed
- All tests green
- Coverage gates met
- UAT signed off by Amr
- STATUS.md updated
- Tag `htf-p0-done` pushed

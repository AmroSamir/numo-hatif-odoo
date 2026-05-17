# Testing Strategy

TDD for every phase. Coverage gates enforced in CI.

---

## Pyramid

```
         ┌────────────┐
         │   E2E      │   ~5–10 scenarios, real Hatif sandbox, Playwright
         ├────────────┤
         │ Integration │   ~50, mocked HTTP boundary, real DB
         ├────────────┤
         │   Unit      │   200+, services, helpers, validators
         └────────────┘
```

## Tools

- `pytest` + `pytest-odoo` (Odoo's test infrastructure)
- `responses` for HTTP mocking
- `freezegun` for time
- `phonenumbers` for E.164 fixtures
- Playwright for E2E (already used by team for Numo platforms)

## Per-module coverage targets

| Module | Target |
|---|---|
| `htf_call_center.services.auth` | 100% |
| `htf_call_center.services.hmac_verify` | 100% |
| `htf_call_center.services.*` (rest) | 90% |
| `htf_call_center.controllers` | 90% |
| `htf_call_center.models` | 80% |
| `numo_crm_htf` (bridge) | 80% |

## Test categories per phase

### P0 (Foundation)
- token cache: refresh on expiry, refresh on 401, retry budget
- HMAC: pass with valid sig, fail without, fail wrong, replay window
- HTTP client: timeout, retry on 5xx, no retry on 4xx, log redaction
- Settings save/load, encrypted-field readback

### P1 (Channels + Contacts + Users)
- channel sync: idempotent, archives on remote-delete
- contact upsert: matches by E.164, dedupe partners
- user mapping wizard: auto-match by email, manual override, idempotent
- vCard import: success + per-row failure handling

### P2 (WA inbound)
- webhook: HMAC fail → 401, idempotency dedupe, schema variations
- partner auto-create when unknown
- chatter post: correct author_id, correct body
- 24h-window updates `last_inbound_at`
- signal fires with correct payload

### P3 (WA outbound)
- send_text: success, failure (network), DNC blocked, window expired
- send_template: param binding (Body/Header/Buttons), sample preview matches Hatif
- chatter composer: WA toggle persists, send button calls service
- bulk send wizard: pre-flight excludes DNC, progress bar, per-recipient state

### P4 (Calls webhook)
- call status mapping (0–7 → enum)
- partner resolution by phone (E.164 normalization edge cases)
- transcription word-level timing parses correctly
- audio player widget loads URL, doesn't leak token
- evaluation criteria render as table
- missed-call → activity created (signal subscriber)

### P5 (IVR)
- trigger: idempotency by external_id
- digit → action mapping fires correct server action
- webhook idempotent on retry
- partner_id + lead_id resolution

### P6 (Conversations)
- list: filters convert UTC+3 correctly
- timeline pagination
- assign: user XOR ai_agent (mutex enforcement)

### P7 (CRM enrichment)
- auto-link to most-relevant open lead — covers ties, no-match, multiple matches
- auto-stage progression rules (positive sentiment + duration > 60s)
- AI summary card displays
- sentiment trend computes from last 10 events
- daily digest cron: only sends to users with content
- bulk WA send: respects DNC + window
- Won/lost hooks fire exactly once
- classify wizard integration

### P8 (Differentiators)
- DNC keyword listener: STOP / إلغاء / variants
- cost tracking: marketing vs utility vs service rates
- PII redaction: regex over transcripts
- Won-back cron: 30/60/90d windows

## Fixtures

`htf_call_center/tests/fixtures/`:
- `webhook_call_completed.json` — real-shaped sample
- `webhook_call_missed.json`
- `webhook_wa_inbound_text.json`
- `webhook_wa_inbound_image.json`
- `webhook_wa_status_delivered.json`
- `webhook_wa_status_read.json`
- `webhook_ivr_digit_pressed.json`
- `webhook_ivr_no_input.json`
- `api_response_token.json`
- `api_response_channels.json`
- `api_response_workspace_users.json`
- `vcards_sample.txt`

## E2E scenarios (Playwright on staging)

1. Inbound call simulation → chatter post visible on lead
2. Send WA template from chatter → message appears, status updates
3. Bulk WA send: 5 leads, 1 DNC → 4 sent
4. Outbound IVR confirm flow: digit 1 confirms appointment
5. Admin user mapping wizard runs end-to-end
6. Webhook spoof attempt → 401, no chatter post
7. 24h-window expired → composer disabled

## CI workflow

```
on: [push, pull_request]
jobs:
  - lint (pylint-odoo + flake8 + black --check)
  - unit + integration (pytest)
  - coverage report (fail if < gate)
  - install + uninstall test on fresh DB
  - data migration test (upgrade from previous version)
```

## Manual UAT (per phase)

A `UAT_CHECKLIST.md` per phase doc captures the exact buttons clicked and expected output. Amr signs off before promotion.

## Regression suite

After each phase, all prior tests must still pass. CI runs full suite on every PR.

## Schema drift detection (R-04)

Each phase that consumes a Hatif response shape ships a `test_schema_drift_<endpoint>.py`:
- Compares `tests/fixtures/<endpoint>.json` to a hash recorded in `tests/fixtures/_drift_hashes.txt`
- Fails CI if Hatif sandbox response differs from fixture (run nightly against sandbox via dedicated CI job)
- Forces explicit acknowledgment + fixture update + bump of vendor module MINOR version when Hatif schema changes
- Prevents silent breaking changes from leaking to prod

## Performance budgets

- Webhook handler: p95 < 500 ms (excluding signal-subscriber work)
- Send WA: p95 < 2s
- Channel sync: < 5s for 50 channels
- Daily digest cron: < 10 min for 1000 users

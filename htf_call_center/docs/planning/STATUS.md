# Live Status

Updated as phases progress. **Single source of truth for "where are we?"**.

---

## Snapshot

| Field | Value |
|---|---|
| Project | htf_call_center + numo_crm_htf |
| Today | 2026-05-17 |
| Plan version | 0.1.1-DRAFT |
| Plan approved by | Amr (verbal, 2026-05-17 — proceed with P0) |
| Active phase | P0 — Foundation (awaiting UAT) |
| Branch | main |

---

## Phase status

| Phase | Status | Started | Completed | Notes |
|---|---|---|---|---|
| P0 — Foundation | In review | 2026-05-17 | — | Code shipped, awaiting UAT on staging |
| **P0.5 — UI Skeleton + Mock Data** | Not started | — | — | UAT gate before P1+ |
| P1 — Channels + Contacts + Users | Not started | — | — | |
| P2 — WA Inbound | Not started | — | — | |
| P3 — WA Outbound | Not started | — | — | |
| P4 — Calls | Not started | — | — | |
| P5 — IVR (slim) | Not started | — | — | |
| P6 — Conversations | Not started | — | — | |
| P7 — CRM Enrichment | Not started | — | — | |
| P8 — Differentiators (optional) | Not started | — | — | |
| P9 — Outbound Sales Acceleration | Not started | — | — | NEW — outbound-first reality |
| P10 — Speech Analytics | Not started | — | — | NEW — leverages transcripts via Claude API or local embeddings |
| ~~P11~~ — ~~Voice AI Agent~~ | **DEFERRED** | — | — | Hatif AI API not ready; revisit when Hatif publishes AI config/training/handoff endpoints |

Status legend: `Not started` | `In progress` | `Blocked` | `In review` | `On staging` | `On prod` | `Done`

---

## Open Questions blocking work

See [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md). Critical for green-light:

- Q-01 (sandbox) — blocks any real E2E
- Q-03 (HMAC format) — blocks P0 webhook code
- Q-05 (workspace count) — blocks channel model decisions
- Q-12 (sandbox phone) — blocks UAT

---

## Risk highlights

See [RISK_REGISTER.md](./RISK_REGISTER.md). Top 3:

1. R-01 Bridge↔wrapper coupling
2. R-02 Webhook spoof
3. R-04 API breaking change

---

## Per-phase change log

> Add entries below per phase as they progress. Format:
>
> `### YYYY-MM-DD — Phase X — Title`
> Outcome / lessons / next step.

### 2026-05-06 — Plan v0.1.0-DRAFT
Initial planning docs landed under `docs/planning/`. Awaiting Amr's approval before P0 starts. Naming convention `htf` locked. Module split (vendor + bridge) locked. Hatif app handles live calls, Hatif portal handles IVR scripts — both confirmed.

### 2026-05-06 — Plan v0.1.1
- Confirmed no streaming API in Hatif (apidog export searched verbatim — all websocket/sse/streaming hits = false positives in words like "pressedDigit").
- Found 3 missed metrics endpoints: `/v1/metrics/general`, `/v1/metrics/voice`, `/v1/metrics/team` — total endpoint count 37 (was 34). Folded into P8 differentiators.
- Reframed plan for **outbound-heavy sales reality** (majority of agent activity = outbound dialing, not inbound screen-pop). Added P9 Outbound Sales Acceleration (pre-call brief + post-call wrap-up + daily queue).
- Added P10 Speech Analytics (per-call insights + aggregates).
- **Voice AI Agent Integration DEFERRED** until Hatif team publishes AI config/training/handoff API. Currently API exposes only AI agent assignment + identification — black box from automation perspective.

### 2026-05-17 — P0 Foundation code shipped (awaiting UAT)
- Module `htf_call_center` scaffolded under `extra-addons/custom/call center modules/`.
- Tasks T0.1–T0.13 complete: scaffolding, htf.config singleton + Settings UI with Test Connection, exceptions module, constants, HMAC verifier (per Q-03 ANSWERED: `X-Voxa-Signature`, raw-body, no timestamp window), signal bus, log redaction filter, auth service with cron + advisory-lock single-flight refresh, HTTP client with 3-attempt backoff + 401 single-retry + typed exception mapping, `htf.webhook.event` idempotency model + nightly purge cron, security groups (group_user / group_admin) + ACL CSV + baseline record rules, pylint custom rule enforcing the module boundary.
- Tests: 60+ unit tests across HMAC, signals, log redaction, exceptions, config, webhook event, auth, http client. Targets per P0 doc (100% auth + hmac_verify, 90% services, 80% overall).
- Sanity checks: every `.py` compiles, every XML parses, manifest valid, access CSV valid, boundary rule confirmed working (flags forbidden bridge imports, allows public surface).
- **Pending UAT**: install on staging, run Settings → Hatif → Test Connection against real creds, verify token cached, toggle debug logging and verify bodies log but secrets stripped, wait 30 min and verify cron refresh, uninstall and verify clean DB.

---

## Sign-offs

| Phase | UAT signed off by | Date | Comments |
|---|---|---|---|
| P0 | _pending_ | | |
| P1 | _pending_ | | |
| P2 | _pending_ | | |
| P3 | _pending_ | | |
| P4 | _pending_ | | |
| P5 | _pending_ | | |
| P6 | _pending_ | | |
| P7 | _pending_ | | |
| P8 | _pending_ | | |

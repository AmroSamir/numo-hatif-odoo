# Risk Register

Continuously updated. Add new rows as discovered. Never delete — mark `MITIGATED` or `ACCEPTED`.

| ID | Severity | Likelihood | Risk | Mitigation | Owner | Status |
|----|----------|------------|------|------------|-------|--------|
| R-01 | HIGH | MEDIUM | Bridge accidentally couples to vendor internals | Pylint custom rule blocks `from htf_call_center.services.*` in bridge (P0 T0.10); code review checklist | Amr | OPEN |
| R-02 | HIGH | LOW | Webhook spoof | HMAC required (P0 T0.6); replay window ±5 min (P0 T0.6); idempotency (P0 T0.11); admin alert on N failures (P2/P4 controllers) | Amr | OPEN |
| R-03 | HIGH | LOW | Token leaked in log | Custom log filter strips `Authorization: Bearer` (P0 T0.8) | Amr | OPEN |
| R-04 | HIGH | MEDIUM | Hatif API breaking change mid-release | Schema drift test per endpoint (TESTING.md §Schema drift); fixture vs live-sandbox nightly CI job; bump MINOR on drift | Amr | OPEN |
| R-05 | HIGH | LOW | numo_crm source modified inadvertently | CI rule fails build if numo_crm/* changes in PR not labelled `crm-core` (P0 T0.10) | Amr | OPEN |
| R-06 | MEDIUM | MEDIUM | Webhook duplicate processing | `htf.webhook.event` UNIQUE on `(event_id, route)`; dedup before signal fire | Amr | OPEN |
| R-07 | MEDIUM | MEDIUM | res.users ↔ Hatif user mapping drift | Daily sync cron + admin notification on mismatches | Amr | OPEN |
| R-08 | MEDIUM | MEDIUM | Phone widget override breaks core Odoo modules | Conditional on `x_htf_enabled`, gracefully fall back to native | Amr | OPEN |
| R-09 | MEDIUM | LOW | 24h window enforcement bug → wrong-cost messages | Service-layer hard guard + tests; monitor cost reports | Amr | OPEN |
| R-10 | MEDIUM | LOW | numo_crm_htf auto-stage rules misfire on legacy leads | Feature flag + opt-in per pipeline; backfill plan | Amr | OPEN |
| R-11 | MEDIUM | LOW | Audio recording URL expires before user opens | Optional cache to ir.attachment on first play | Amr | OPEN |
| R-12 | MEDIUM | MEDIUM | Hatif sandbox unavailable for testing | Negotiate sandbox; fallback to webhook.site replay | Amr | OPEN |
| R-13 | MEDIUM | MEDIUM | Multiple Numo brands need separate channels | Channel model has team_id link; channels-per-team supported by design | Amr | OPEN |
| R-14 | LOW | MEDIUM | AI extraction proposes wrong field values | User-accept gate; never auto-apply; rollback button | Amr | OPEN |
| R-15 | LOW | LOW | vCard import partial failure | Per-row error log; transactional commit per row | Amr | OPEN |
| R-16 | LOW | MEDIUM | Hatif rate-limit on bulk WA send | Local rate limiter (5 msg/sec default); honor 429 retry-after | Amr | OPEN |
| R-17 | MEDIUM | MEDIUM | DNC keyword false positives (e.g. "Stop, that's right") | Strict pattern (case-insensitive whole-message match for STOP); admin can override | Amr | OPEN |
| R-18 | LOW | LOW | Recording URL leaks (no auth) | Hatif issues short-lived signed URLs; verify ToS; consider ir.attachment cache with Odoo ACL | Amr | OPEN |
| R-19 | MEDIUM | LOW | PDPL data residency compliance | Confirm Hatif KSA-hosted; no PII flows to non-KSA region | Amr | OPEN |
| R-20 | LOW | MEDIUM | Phone widget UX collision with existing modules (e.g. asterisk_click2dial) | Detect and yield gracefully; document conflicts | Amr | OPEN |
| R-21 | LOW | LOW | Webhook IP allowlist not provided by Hatif | Document; rely on HMAC alone if not provided; revisit | Amr | OPEN |
| R-22 | LOW | MEDIUM | Module bloat (too many features in v1) | Phase boundaries strictly enforced; differentiator phase optional | Amr | OPEN |
| R-23 | LOW | LOW | UTC+3 ↔ UTC mismatch on conversation list filters | Service layer normalizes; tests with edge cases (DST, offsets) | Amr | OPEN |
| R-24 | LOW | LOW | Bridge depends on numo_crm version drift | Bridge `__manifest__.py` version range constraint on numo_crm | Amr | OPEN |

## Severity scale
- HIGH = data loss, security breach, prod outage
- MEDIUM = functionality break, customer-visible bug
- LOW = cosmetic, recoverable, low blast radius

## Likelihood scale
- HIGH = expected unless prevented
- MEDIUM = plausible
- LOW = edge case

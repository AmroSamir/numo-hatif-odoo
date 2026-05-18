# Live Status

Updated as phases progress. **Single source of truth for "where are we?"**.

---

## Snapshot

| Field | Value |
|---|---|
| Project | htf_call_center + numo_crm_htf |
| Today | 2026-05-19 |
| Plan version | 0.3.0-LIVE (P2 + P3 live-verified against real Hatif on erp.amro.pro) |
| Plan approved by | Amr (live UAT round-trip passed both ways 2026-05-19) |
| Active phase | P4 — Calls Webhook (next, same pattern as P2) |
| Branch | main |
| Repo | https://github.com/AmroSamir/numo-hatif-odoo |
| Local dev DB | `test` (on OrbStack `odoo-app`, port 8069), bind-mount `~/numo-hatif-odoo/{htf_call_center,numo_crm_htf}` |
| Staging deploy | `https://erp.amro.pro` — DB `numo`, container `web-erp-amro-pro`, addons at `/opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/` |
| Prod target | `https://erp.numo.sa` — same DB `numo`, deploy pattern mirrors staging |

---

## Phase status

| Phase | Status | Started | Completed | Notes |
|---|---|---|---|---|
| P0 — Foundation | **Done** | 2026-05-17 | 2026-05-17 | Token refresh against real api.voxa.sa works; 59/59 E2E green; Settings page renders Hatif tab |
| **P0.5 — UI Skeleton + Mock Data** | **Skipped** | — | — | Skipped per Amr's call — fast local-Odoo loop + 130+ E2E checks replaced the mocks-first gate |
| P1 — Channels + Contacts + Users | **Done** | 2026-05-17 | 2026-05-17 | Live-UAT'd against the real Numo workspace: 2 channels, 7 users, 1 tag synced; Map Users wizard persists assignments; 73/73 P1 E2E green |
| P2 — WA Inbound | **✅ LIVE on erp.amro.pro** | 2026-05-18 | 2026-05-19 | Real WhatsApp from Amr's phone → Hatif → /htf/webhook/whatsapp → htf.message + placeholder partner + chatter bubble. P2 E2E 63/63 green + live UAT confirmed. Caveat: Hatif does NOT sign webhooks despite docs (Q-03) — dev_mode_skip_hmac=True until Hatif support clarifies. |
| P3 — WA Outbound | **✅ LIVE on erp.amro.pro** | 2026-05-18 | 2026-05-19 | Phone widget + Send WA wizard + channel resolver + retry cron + cost-by-category all live-verified. Sent a real WA from the wizard, customer phone received it within seconds. P3 backend E2E 24/24 + UI E2E 17/17 + live UAT confirmed. T3.4 full chatter composer patch still deferred (lite header button covers the UX). |
| P4 — Calls | Not started | — | — | Ingest Hatif transcription/Summary/sentiment on call object |
| ~~P5~~ — ~~IVR (slim)~~ | **SKIPPED** | — | — | IVR + bulk campaigns run on Hatif portal directly (decision 2026-05-18) |
| P5 — Conversations | Not started | — | — | Was P6. Polling backfill insurance against missed webhooks |
| P6 — CRM Enrichment | Not started | — | — | Was P7. Smart buttons + chatter glue |
| P7 — Differentiators (optional) | Not started | — | — | Was P8. DNC, cost, Arabic prompts, dashboard tiles |
| P8 — Outbound Sales Acceleration | Not started | — | — | Was P9. Daily call queue + pre-call brief + wrap-up (critical given 99% outbound) |
| P9 — Speech Analytics via n8n | Not started | — | — | Was P10. Hatif transcripts → n8n → LLM → CRM stage + agent scorecards |
| ~~P10~~ — ~~Voice AI Agent~~ | **DEFERRED** | — | — | Hatif AI agent API not published (Q-28). Gate behind feature flag for future activation. |

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

### 2026-05-17 — P0 + P1 DONE (live-verified against real Numo workspace)

Source-of-truth repo moved to https://github.com/AmroSamir/numo-hatif-odoo (public).
Local dev runs against the `test` DB on OrbStack `odoo-app` container,
bind-mount `~/numo-hatif-odoo/{htf_call_center,numo_crm_htf} → /mnt/extra-addons/`.

P0 verified via JSON-RPC + Settings → Hatif → Test Connection against
real `api.voxa.sa`: token cached, JWT round-trip OK. 59/59 E2E green
(/tmp/htf_e2e_check.py).

P1 shipped: models (htf.channel, htf.tag, htf.user.link, htf.contact.link
+ res.partner / res.users / crm.team extension fields), services
(channels, tags, workspace, contacts, contact_properties), phone E.164
normalizer (KSA-aware), 3 wizards (Bind Channels, Map Users, Import vCards),
nightly channel sync cron, contacts poll cron (placeholder until Hatif
delta endpoint lands per Q-10).

P1 live-UAT proof against Numo workspace:
- 2 channels synced (أكاديمية نمو + الدعم الفني, type=both,
  +966115001591 / +966115001592)
- 7 workspace users synced with real Arabic display names (سامي العنزي
  as owner, others as member)
- 1 tag synced (مهتم, pinned)
- Re-sync idempotent
- Map Users wizard end-to-end working — assigns user_id on htf.user.link
- 73/73 P1 E2E green (/tmp/htf_p1_check.py)

Odoo-19 footguns caught + logged in CLAUDE.md THE DRILL (in priority order):
1. `res.groups.users → user_ids` + `res.users.groups_id → group_ids`
   rename
2. `category_id`, `comment` removed from `res.groups`
3. `numbercall`, `nextcall` removed from `ir.cron`
4. search views: no `string=` on `<search>`, no `<group>` wrapper for
   group-by filters
5. `ir.actions.act_window.target='inline'` removed (use `current`)
6. `_sql_constraints` deprecated → `models.Constraint(...)`
7. `<app data-key="...">` (17) → `<app name="...">` (19)
8. `<app>` tabs in Settings need `application: True` AND user must be
   in listed `groups=`
9. Server-action menus don't render in Odoo 19's flat top navbar — put
   sync buttons on forms with wrappers on res.config.settings
10. Implied groups don't propagate retroactively — set `user_ids`
    directly on the group XML
11. `safe_eval` for `ir.cron.code` forbids `import` — move to model
    method, call `model.<method>()` from cron body
12. **`readonly=True` + `required=True` + populated by `default_get` =
    save-round-trip footgun** (OWL strips readonly from write payload)
13. Wizard line list views must include every required Many2one
    (`<field name="x" column_invisible="1"/>`) — Odoo only persists
    fields present in the rendered view
14. Never name a custom field `display_name` — Odoo auto-computes one
    that shadows your stored value
15. Never put literal `<app>` markup inside an XML comment — Odoo
    re-emits comment text as live tags, breaking SettingsFormCompiler
16. Never name a throwaway variable `_` in a method that also calls
    `gettext _()` — UnboundLocalError shadows
17. Always defensively handle vendor response shapes: Hatif's `role`
    is int (not str), `phoneNumber` is dict (not str), channel type
    key is `type` (not `channelType`)

OPEN Amr-owned questions for P2+ still pending:
Q-05, Q-13, Q-14, Q-15, Q-16, Q-17, Q-18, Q-19, Q-20, Q-23, Q-24,
Q-25, Q-30 — see OPEN_QUESTIONS.md.

**Next session starts here → P2 (WhatsApp Inbound webhook).** Read
NEXT_SESSION.md for the pickup checklist.

### 2026-05-19 — P2 + P3 LIVE-VERIFIED on erp.amro.pro

Deployment landed cleanly. Real-Hatif round trip working both directions.

Deploy details:
- Server: Contabo VPS, container `web-erp-amro-pro` (Odoo 19 Enterprise),
  DB `numo`, addons-path includes `/opt/odoo-erp-amro-pro/extra-addons/`
- Module installed via `docker compose run --rm web odoo -d numo
  -i htf_call_center --stop-after-init --no-http` (running container's
  port 8069 conflicts with `--no-http` skip)
- `phonenumbers 8.12.57` already Debian-packaged on the image — no
  pip install needed
- Both Hatif channels (أكاديمية نمو / الدعم الفني) bound to sales teams
  with default outbound WA set

Live UAT proof:

**Inbound (real WA from Amr's phone):**
- Hatif POSTs from `8.213.48.16` to `/htf/webhook/whatsapp`
- HMAC verification was failing — diagnostic logging proved Hatif
  sends NO signature header at all (despite Q-03 ANSWERED docs)
- `htf.config.dev_mode_skip_hmac=True` flipped on; bridge now accepts
  unsigned and processes the payload
- Placeholder partner `id=101704` auto-created for the inbound contactId
- All 4 status transitions (Pending → Sent → Delivered → Read) dispatched
- Hatif retries deduplicated via composite event-id key

**Outbound (Odoo wizard → real WA on Amr's phone):**
- Whitelist canonicalization bug found + fixed: partner phone arrived as
  `+966 56 186 8578` (with spaces) but `outbound_phone_whitelist` was
  `+966XXXXXXXXX` — naive comparison missed. Now uses
  `utils.phone.normalize_e164` to canonicalize both sides.
- `allow_real_outbound=True` + whitelist set + container restarted
  (to bust ormcache from raw-SQL writes)
- Wizard → action_send → real POST to `api.voxa.sa/v1/whatsapp/sendText`
- Phone received the WA within seconds

UX fixes shipped alongside:
- Channels list `create='0'` (no manual creation; sync-only)
- "Sync Channels from Hatif" + "Bind Channels to Teams" surfaced in
  ⚙ Actions menu instead of as separate navbar tabs
- "Send WhatsApp" header button on res.partner + crm.lead forms
  (alongside the 💬 button in the htf_phone widget)
- WhatsApp Messages menu entry added under Hatif (was missing — only
  reachable via Settings before)
- `crm` added to depends — htf_phone widget + Send WA button now apply
  to crm.lead forms too (was missed because htf_call_center was
  intentionally CRM-agnostic; reality: Numo always has CRM installed)

Known caveat carried to next session:
- Hatif webhooks are unsigned. Defense-in-depth via Nginx IP allowlist
  for `8.213.48.16` is the next hardening task. Email to Hatif support
  drafted at `docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md`.

PII scrubbed:
- Amr's personal phone number replaced with `+966XXXXXXXXX` placeholder
  across all docs and code comments. Git history still has it.

**Next session starts here → P4 Calls Webhook.** Same pattern as P2.
See NEXT_SESSION.md for the pickup checklist.

---

## Sign-offs

| Phase | UAT signed off by | Date | Comments |
|---|---|---|---|
| P0 | Amr | 2026-05-17 | Test Connection green against real api.voxa.sa |
| P1 | Amr | 2026-05-17 | 2 channels + 7 users + 1 tag synced from real Numo workspace |
| P2 | Amr | 2026-05-19 | Live WA inbound on erp.amro.pro — real phone → Odoo chatter |
| P3 | Amr | 2026-05-19 | Live WA outbound on erp.amro.pro — Odoo wizard → real phone |
| P4 | _pending_ | | |
| P5 | _pending_ | | |
| P6 | _pending_ | | |
| P7 | _pending_ | | |
| P8 | _pending_ | | |

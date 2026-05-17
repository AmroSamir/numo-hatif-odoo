# Open Questions

Source of truth for things we still need to confirm with Hatif team or Amr. Each row tracked until ANSWERED or DEFERRED.

| ID | Owner | Question | Why it matters | Status | Answer |
|----|-------|----------|----------------|--------|--------|
| Q-01 | Hatif team | Do you offer a sandbox / test workspace? | E2E tests need a non-prod target | ANSWERED | **Decision: skip sandbox, use prod creds for all dev/UAT.** Mitigations: dev calls + WA only to `+966561868578`; outbound campaigns gated behind `HTF_ALLOW_REAL_OUTBOUND=1` env flag (default OFF on staging). |
| Q-02 | Hatif team | Webhook IP allowlist? | Defense-in-depth alongside HMAC | OPEN | |
| Q-03 | Hatif team | HMAC header name + format | Locks signature verification code | ANSWERED | Found in apidog export L5088. Header = `X-Voxa-Signature` (Hatif white-labels Voxa). Algo = HMAC-SHA256. Encoding = lowercase hex. Signed payload = **raw JSON request body only** (NO timestamp prefix). Per-channel `webhookSecret`. NO timestamp header → drop replay-window check, rely on event-id idempotency instead. |
| Q-04 | Hatif team | HMAC secret rotation cadence + UX | Drives multi-secret support window | ANSWERED-PARTIAL | Per-channel `webhookSecret` configured manually by Hatif team (no self-serve UI documented). Plan: store current+previous secrets in `htf.config`, accept either during rotation overlap. |
| Q-05 | Hatif team | Single workspace for all Numo brands or per-brand workspaces? | Channel model design + team mapping | OPEN | |
| Q-06 | Hatif team | Recording retention period + URL expiry | Whether to cache locally or rely on Hatif | OPEN | |
| Q-07 | Hatif team | Does `customPropertyFilters.operator` support more than `1=equals`? | Bulk search query power | OPEN | |
| Q-08 | Hatif team | Are AI agents auto-assigned per channel rule or always manual? | Bridge auto-assign logic | OPEN | |
| Q-09 | Hatif team | Per-message cost API or computed locally? | Cost tracking accuracy | OPEN | |
| Q-10 | Hatif team | Is there a webhook for contact create/update? | Polling cron may be unnecessary | ANSWERED | NO. docs.hatif.io confirms only 2 webhooks: Call Webhook + WhatsApp Message Webhook. Must poll `/v1/contacts` if Numo CRM ↔ Hatif contact sync needed. |
| Q-11 | Hatif team | Confirm KSA data residency (PDPL) | Compliance | OPEN | |
| Q-12 | Hatif team | Sandbox phone number we can call/WA in dev | E2E real-traffic tests | ANSWERED | Use Amr's number `+966561868578` for dev/UAT calls. Mark in test fixtures as `DEV_TEST_PHONE`. |
| Q-13 | Amr | Will templates be approved per-brand (Cambridge / NH / Numo Academy) or shared? | Template registry design | OPEN | |
| Q-14 | Amr | Auto-stage progression — opt-in per pipeline or universal? | Risk of misfire on legacy leads | OPEN | |
| Q-15 | Amr | Should we cache recordings to Odoo? | Storage + privacy implications | OPEN | |
| Q-16 | Amr | Are agents organized in teams with team channels, or single-channel-per-brand? | Team↔channel binding | OPEN | |
| Q-17 | Amr | Confirm production hostname and webhook IP egress rules | Hatif side configuration | OPEN | |
| Q-18 | Amr | Should the bridge subscribe to numo_crm classify events? | Tight integration vs loose coupling | OPEN | |
| Q-19 | Amr | Sentiment thresholds for auto-progression (e.g. positive + duration > 60s → Qualified) — exact rules | Avoid false promotions | OPEN | |
| Q-20 | Amr | Won/lost auto-template names + parameters | Need template list to wire hooks | OPEN | |
| Q-21 | Hatif team | Are there language/region-specific TTS voices beyond Male/Female? | IVR localization | OPEN | |
| Q-22 | Hatif team | Concurrent webhook delivery rate? | Worker capacity sizing | ANSWERED-PARTIAL | Apidog L5088 confirms retry policy: **5 attempts, exp backoff 2/4/8/16/32 min** (62-min total window). Concurrency rate NOT documented. Defaults adopted: assume at-least-once + unordered delivery; design for 50 req/s burst per workspace (Twilio-class default); respond <5s with 200 then async-process; idempotency by event `id`; gate state transitions by `creationTime` not arrival order. |
| Q-23 | Amr | Do we need WhatsApp click-to-WhatsApp ad attribution support in v1? | Phase 8 scope | OPEN | |
| Q-24 | Amr | Are existing leads' phone numbers in E.164 format already? | Migration script needed | OPEN | |
| Q-25 | Amr | OK to add fields to res.partner directly, or use linking model only? | Schema strategy | OPEN | |
| Q-26 | Hatif team | Are `/v1/metrics/general`, `/v1/metrics/voice`, `/v1/metrics/team` accessible via service-account token? Apidog example uses `{{user_access_token}}` | P8 metrics dashboard feasibility | OPEN | |
| Q-27 | Hatif team | Response schema of each metrics endpoint? | Dashboard widget design | OPEN | |
| Q-28 | Hatif team | When will AI agent config / knowledge base / handoff API publish? | P11 deferred until then | OPEN | |
| Q-29 | Amr | Confirm outbound dominates sales calls vs inbound? | Feature priority | ANSWERED | YES — outbound dominant |
| Q-30 | Amr | Speech analytics — Claude API budget OK (~$0.001/transcript) or local embeddings? | P10 design | OPEN | |
| Q-31 | Amr | AI auto-assignment scope when AI API ready — after-hours only, or also Cold-stage chasing? | P11 design | DEFERRED | |

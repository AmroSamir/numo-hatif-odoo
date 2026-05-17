# HTF Call Center — Master Planning Document

**Version:** 0.1.0-DRAFT
**Last updated:** 2026-05-06
**Owner:** Amr Afifi
**Status:** PLANNING — awaiting confirmation before code

---

## 1. Project Goal

Integrate the Hatif/Voxa BPaaS (telephony + WhatsApp Business API) deeply into the existing Numo Odoo 19 Enterprise deployment so that every interaction (calls, WA messages) becomes a first-class object inside Odoo's CRM, contacts, and chatter — without requiring agents to use a separate tool for context.

Live calling itself stays in Hatif's web/mobile app; Odoo is the **system of record** for every interaction afterwards.

## 2. Scope (in)

- Vendor wrapper module `htf_call_center` (telephony + WA API + webhooks)
- Bridge module `numo_crm_htf` (CRM-specific automation)
- Phone widget override on `res.partner` and `crm.lead` (deep-link to Hatif app + WA composer)
- Webhook receivers (calls, WA) with HMAC verification
- Auto-posting calls/WA to chatter on the right `res.partner` / `crm.lead`
- Auto-create contacts from inbound interactions
- Outbound WhatsApp from chatter (text + template)
- res.users ↔ Hatif workspace user mapping
- DNC list + opt-out keyword listener
- 24h Meta-window enforcement
- Admin Settings panel for credentials, channels, secrets, mapping
- Numo CRM enrichment: AI summary card, sentiment trend, auto-stage progression, daily digest, won/lost hooks, classify wizard integration

## 3. Scope (out)

- Replacing Odoo telephony for live calls (Hatif owns this)
- IVR + bulk campaigns entirely — owned by Hatif portal, not Odoo (decided 2026-05-18)
- Live softphone in Odoo
- WA template management/approval (Hatif portal owns; Odoo only registers approved names)
- Bulk broadcast UI in v1 (deferred to v1.1)
- Custom reporting menus (reports embed in existing CRM analytics, no new menu)
- Editing the `numo_crm` module directly — all extension via inheritance in `numo_crm_htf`

## 4. Architecture One-Pager

```
┌──────────────────────────────────────────────────────┐
│ Existing Odoo modules (UNTOUCHED)                    │
│   numo_crm, sale, account, crm, helpdesk             │
└──────────────┬───────────────────────────────────────┘
               │ extended via _inherit + xpath views only
               ▼
┌──────────────────────────────────────────────────────┐
│ numo_crm_htf  (bridge)                               │
│   Numo-specific CRM automation                       │
│   Subscribes to htf signals                          │
└──────────────┬───────────────────────────────────────┘
               │ public Python API only
               ▼
┌──────────────────────────────────────────────────────┐
│ htf_call_center  (vendor wrapper)                    │
│   HTTP client, auth, webhooks, raw models, settings  │
└──────────────┬───────────────────────────────────────┘
               │ raw HTTPS
               ▼
        Hatif/Voxa API (api.voxa.sa)
```

**Golden rule:** the bridge talks to the wrapper only via documented public services / signals. The bridge never imports vendor internals.

## 5. Naming Convention (LOCKED)

| Concern | Convention |
|---|---|
| Folder names | `htf_call_center`, `numo_crm_htf` |
| Models | `htf.config`, `htf.channel`, `htf.call`, `htf.message`, `htf.conversation`, `htf.tag`, `htf.contact.link`, `htf.user.link`, `htf.dnc` *(htf.message.template removed per Q-13; htf.ivr.run removed per P5-skip decision)* |
| Custom fields on existing models | `x_htf_*` (e.g. `res.partner.x_htf_contact_id`, `res.users.x_htf_user_id`) |
| Webhook routes | `/htf/webhook/call`, `/htf/webhook/whatsapp` *(IVR route removed)* |
| Security groups | `htf_call_center.group_user`, `htf_call_center.group_admin` |
| Signals (registry pattern) | `htf.call.received`, `htf.call.missed`, `htf.wa.inbound`, `htf.wa.outbound`, `htf.wa.status`, `htf.wa.optout`, `htf.contact.synced` *(htf.ivr.result removed)* |
| User-facing UI labels | "Call", "WhatsApp", or "Hatif Call" / "Hatif WA" — keep "Hatif" only in labels for ops clarity, never in identifiers |

## 6. Phase Index

| # | Phase | Module | Goal | Doc |
|---|-------|--------|------|-----|
| P0 | Foundation | `htf_call_center` | Auth, HTTP client, settings, HMAC verify, scaffolding | [P0_FOUNDATION.md](./P0_FOUNDATION.md) — **✅ SHIPPED** |
| ~~P0.5~~ | ~~UI Skeleton + Mock Data~~ | — | **SKIPPED — live UAT against real Hatif workspace covered the gate** | — |
| P1 | Channels + Contacts + Users | `htf_call_center` | Channel sync, contact mapping, user mapping wizard | [P1_CHANNELS_CONTACTS.md](./P1_CHANNELS_CONTACTS.md) — **✅ SHIPPED** |
| P2 | WhatsApp Inbound | `htf_call_center` | Webhook → chatter, status updates, opt-out | [P2_WHATSAPP_INBOUND.md](./P2_WHATSAPP_INBOUND.md) — **▶️ NEXT** |
| P3 | WhatsApp Outbound | `htf_call_center` | Chatter composer, template send (Hatif owns approval), phone widget | [P3_WHATSAPP_OUTBOUND.md](./P3_WHATSAPP_OUTBOUND.md) |
| P4 | Calls Webhook | `htf_call_center` | Call log, audio player, transcription/summary ingest | [P4_CALLS.md](./P4_CALLS.md) |
| ~~P5~~ | ~~Outbound IVR (slim)~~ | — | **SKIPPED — IVR + bulk campaigns owned by Hatif portal, not Odoo (decision 2026-05-18)** | — |
| P5 | Conversations Sync | `htf_call_center` | Cron poll, conversation snapshot (was P6) | [P6_CONVERSATIONS.md](./P6_CONVERSATIONS.md) |
| P6 | CRM Enrichment | `numo_crm_htf` | Lead form widgets, smart buttons, classify glue (was P7) | [P7_CRM_ENRICHMENT.md](./P7_CRM_ENRICHMENT.md) |
| P7 | Reporting + Differentiators | both | DNC, cost tracking, Arabic prompts, won-back, dashboard tiles (was P8) | [P8_DIFFERENTIATORS.md](./P8_DIFFERENTIATORS.md) |
| P8 | Outbound Sales Acceleration | bridge | Pre-call brief, post-call wrap-up, daily call queue (was P9 — first-class given 99% outbound) | P9_OUTBOUND_ACCELERATION.md *(to be written)* |
| P9 | Speech Analytics | bridge | Hatif transcript + Summary + sentiment → n8n LLM → CRM stage + agent scorecards (was P10, simplified) | P10_SPEECH_ANALYTICS.md *(to be written)* |
| ~~P10~~ | ~~Voice AI Agent Integration~~ | — | **DEFERRED — Hatif AI agent API not published (Q-28)** | — |

Cross-cutting docs:
- [USER_SCENARIOS.md](./USER_SCENARIOS.md) — narrative walkthroughs
- [DATA_MODEL.md](./DATA_MODEL.md) — every model + field
- [API_CONTRACT.md](./API_CONTRACT.md) — public Python API exposed by vendor wrapper
- [SIGNAL_BUS.md](./SIGNAL_BUS.md) — event registry + payload shapes
- [SECURITY.md](./SECURITY.md) — secrets, HMAC, record rules, access groups
- [TESTING.md](./TESTING.md) — unit, integration, E2E strategy + coverage gates
- [DEPLOYMENT.md](./DEPLOYMENT.md) — staging → prod, upgrade order, rollback
- [RISK_REGISTER.md](./RISK_REGISTER.md) — full risk table with mitigations
- [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md) — what we still need from Hatif team / Amr
- [STATUS.md](./STATUS.md) — live progress tracker (updated per phase)

## 7. Phase Sequence + Estimates

```
Done:    P0 ────► P1 ────►
Now:     ─────► P2 ────► P3 ────► P4 ────►
Next:    ─────► P5 ────► P6 ────► P7 (optional) ────►
Later:   ─────► P8 ────► P9 ────►
```

| Phase | Effort (dev hrs) | Status |
|---|---|---|
| P0  | 6–10  | ✅ SHIPPED |
| P1  | 8–12  | ✅ SHIPPED |
| P2  | 8–10  | ▶️ NEXT |
| P3  | 10–14 | |
| P4  | 10–14 | |
| P5  | 8–10  | (was P6) |
| P6  | 16–22 | (was P7) |
| P7  | 16–24 | (was P8, optional) |
| P8  | 12–16 | Outbound acceleration (was P9) |
| P9  | 10–14 | LLM via n8n (was P10, simplified) |
| **Total core (P0–P6)** | **66–92 dev hrs** | |
| Plus QA + UAT + buffer | +30–40 hrs | |

## 8. Critical Decisions (LOCKED)

| Decision | Choice | Rationale |
|---|---|---|
| Module split | 2 modules (vendor wrapper + bridge) | Vendor swap-readiness, clean separation, numo_crm stays untouched |
| Live calling | Hatif app/mobile only | Hatif is the softphone; Odoo logs after the fact |
| IVR + bulk campaigns | Hatif portal — Odoo does NOT touch these | Decision 2026-05-18: Numo runs all IVR scripts and campaign blasts on app.hatif.io directly. P5 (IVR module) removed from the roadmap. |
| Per-agent auth | Single service token, mapped users | Hatif API is service-account scoped |
| Bridge edits to numo_crm | Forbidden | Inheritance only, no fork |
| Naming | `htf` everywhere in code | Vendor name kept out of identifiers |
| UI for normal users | Embedded in existing forms (no new menus) | Native feel; less training |
| Admin UI | Single Settings panel | Credentials, channels, mappings, secrets |
| Webhook auth | HMAC required | Spoofing protection |
| Channel ↔ Team binding | 1:N today (multi-channel-per-team allowed), reassignable via admin wizard | 5+ Hatif channels mapped to specific Numo sales teams; design must allow easy rebinding |
| Outbound channel resolution | Lead.team → Partner.team → Partner override → User.team → Workspace fallback | Agents never pick channel manually for default cases |
| Inbound routing | Channel.team owns; route by team's strategy (lead_owner / round_robin / least_busy) | Inbound on channel X always lands in team X first |

## 9. Critical Decisions (OPEN — see [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md))

- Hatif sandbox availability for staging testing
- Webhook IP allowlist
- HMAC secret rotation cadence
- Single workspace vs per-brand workspaces (Numo Academy / Cambridge / NH)
- Recording retention — Hatif side or mirror to Odoo
- WA template approval workflow with Hatif team
- Sandbox phone number for E2E tests

## 10. Acceptance Criteria (project-level)

The project is considered shippable when:

1. Inbound call to a Numo line auto-creates `htf.call` row + posts to lead chatter within 10s of webhook arrival
2. Inbound WA message threads on res.partner chatter and triggers correct CRM stage progression
3. Agent can send WA template from a lead form in ≤3 clicks
4. Missed call auto-creates a "Phone Call" activity assigned to lead owner
5. Sentiment + AI summary visible on lead form for any answered call
6. DNC list blocks outbound WA pre-send with clear UX warning
7. 24h-window indicator visible on every WA conversation
8. Admin Settings page has `Test Connection` button that succeeds against real Hatif token
9. Agents see only their own assigned conversations (record rules enforced)
10. All webhook routes reject requests with invalid HMAC signature
11. Module pair installs cleanly on staging (`erp.numo.sa` staging) and uninstalls cleanly without residue
12. 80%+ test coverage on both modules
13. No edits to `numo_crm` source

## 11. Deferred (revisit when blockers cleared)

| Item | Blocker | Revisit when |
|---|---|---|
| Voice AI Agent Integration | Hatif AI API surface incomplete (only assignment exposed; no config/training/handoff endpoints) | Hatif publishes AI agent management API |
| Real-time agent assist (live during call) | No streaming/WebSocket/SSE in Hatif API | Hatif exposes call-state events |

## 12. Out-of-Scope — Won't Build (record for future v2)

- Live softphone in Odoo
- IVR script designer
- WA template approval inside Odoo
- Multi-tenant workspace support
- Voice biometric auth
- Predictive dialer
- Speech analytics dashboards
- Real-time agent assist / next-best-action coaching
- Voice AI agent (separate Hatif feature, not Odoo's job)

## 13. Process Rules

- All planning lives under `htf_call_center/docs/planning/` and is committed alongside code
- Each phase doc owns its own status section — updated as tasks complete
- Each phase ends with a code review pass + UAT on staging before next phase starts
- Risks added to RISK_REGISTER.md as discovered, never hidden in commit messages
- Open questions tracked in OPEN_QUESTIONS.md with `STATUS: OPEN | ANSWERED | DEFERRED`
- TDD per phase — write tests first, target 80%+ coverage
- Every phase has explicit acceptance criteria, written before the phase starts
- Production deploy only after staging UAT signed off by Amr
- numo_crm source: read-only — touch one line and CI fails

---

**Next step:** read [USER_SCENARIOS.md](./USER_SCENARIOS.md), [DATA_MODEL.md](./DATA_MODEL.md), [API_CONTRACT.md](./API_CONTRACT.md), then phase docs in order. Status of each phase tracked in [STATUS.md](./STATUS.md).

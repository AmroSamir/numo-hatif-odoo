# NEXT SESSION — start here

Last updated: **2026-05-19** (end of day) — P0-P4 all live on
`erp.amro.pro` after a full UAT round. Session closed cleanly.

---

## 30-second TL;DR

The Hatif↔Odoo bridge `htf_call_center` is **production-shape** on
the staging ERP (`https://erp.amro.pro`, db `numo`). Real-world
inbound + outbound flows are verified across calls + WhatsApp.

| Phase | Status |
|---|---|
| P0 Foundation | ✅ live |
| P1 Channels + Contacts + Users | ✅ live |
| P2 WhatsApp Inbound | ✅ live |
| P3 WhatsApp Outbound | ✅ live |
| P4 Calls Webhook | ✅ live |
| ★ **P8 Outbound Sales Acceleration** | approved, **NEXT** |
| ★ P9 Speech Analytics via n8n | approved, after P8 |
| ★ P5 Conversations Sync | approved, lower priority |

GitHub: https://github.com/AmroSamir/numo-hatif-odoo
Latest commit: `2bfe333` (or whatever's on `main` when you sit down).
Test scoreboard: **274/274** across 6 suites locally
(dropped one stale P1 assertion that required a `Bind Channels Wizard`
top-level submenu — that menu lives as a header button now).

---

## 🗒️ Amr's approved queue (priority order)

### 1. ★ P8 — Outbound Sales Acceleration (NEXT)

Lives in `numo_crm_htf` bridge module (sibling repo dir,
not started yet). ~12-16h. Highest ROI because 99% of Numo's calls
are outbound (Q-29 ANSWERED).

**What it ships:**

| Task | What |
|---|---|
| T8.1 | Daily Call Queue list view per agent. Priority order from CRM activity + lead score + last touch |
| T8.2 | Click-to-call from the queue → opens Hatif app via `tel:` deep-link (or Hatif outbound API if Hatif publishes one) |
| T8.3 | Pre-call Brief side panel — last calls (transcripts, summaries, sentiment from P4) + last WA thread + CRM activity + partner tags, all in one screen |
| T8.4 | Post-call Wrap-up wizard — auto-opens on `htf.call.received` signal. Outcome / Next step / Notes form writes to crm.lead + creates `mail.activity` |
| T8.5 | Agent Scorecard widget — calls today/week/month, connect rate, avg duration, avg sentiment, conversion |

**P8 pre-build questions Amr needs to answer before T8.1 starts:**

- (a) **Outcome enum:** Interested / Not interested / Voicemail /
  Wrong number / Reschedule / ... — additions or removals?
- (b) **Next step options:** which templates to surface? Schedule
  callback / Move stage / Won / Lost / others?
- (c) **Wrap-up wizard:** mandatory (blocking until filled) or
  skippable?
- (d) **Daily queue priority rule:** default proposal is
  `(activity deadline overdue) > (lead score) > (days since last touch)`.
  Want a Numo-specific rule instead?

### 2. ★ P9 — Speech Analytics via n8n (after P8)

`numo_crm_htf` bridge. ~8h. Q-19 + Q-30 ANSWERED with n8n routing.

Now that Hatif sends transcripts + summaries + sentiment for calls
≥30s (verified live), ship the n8n bridge:
- Post each completed `htf.call` to an n8n webhook (HMAC-signed)
- n8n calls LLM (Claude/GPT/whatever) with structured prompt
- n8n PUSHES back `{stage, confidence, agent_score, notes}` via
  Odoo JSON-RPC to `/htf/internal/llm/result` (HMAC-signed)
- Bridge writes stage to `crm.lead`, creates `htf.agent.scorecard`

Depends on P8 because the wrap-up form should show LLM suggestions
inline ("LLM thinks: move to Qualified, confidence 0.84").

### 3. ★ P5 — Conversations Sync (later)

`htf_call_center` wrapper. ~6h. Live UAT shows webhooks flowing
reliably so this is insurance, not urgent.

Cron-poll Hatif `/v1/conversations` every 15 min and reconcile any
missing events into `htf.message` + `htf.call`. Catches the rare
case where Hatif's webhook delivery silently drops.

### 4. Send Hatif support email (5 min)

Draft is ready at:
`htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md`

Asks 7 questions: webhook signing status, source IPs, secret
distribution, post-call re-fire timing, status=8 enum, per-channel
analytics toggle, and the apidog/actual implementation gap.

### 5. T4.5 — Transcript click-to-seek widget (3h)

OWL polish: clicking a word in the transcript seeks the embedded
audio player. The data is already there (`transcription_words_json`
on `htf.call`). Needs browser-based verification — defer until
you're at a machine with Chrome.

---

## Reference

### Environments

| Env | URL | DB | Container | Path |
|---|---|---|---|---|
| Local (empty) | `localhost:8069` | `odoo` | `odoo-app` (OrbStack) | bind-mount `~/numo-hatif-odoo/` |
| Local (full) | same | `test` | same | same |
| **Staging** | `https://erp.amro.pro` | `numo` | `web-erp-amro-pro` | `/opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/` |
| Prod | `https://erp.numo.sa` | `numo` | TBD | not deployed yet |

### Credentials

In the workspace `.env` file at
`/Users/amro/Downloads/Claude/odoo-modules/extra-addons/custom/call center modules/.env`.

For erp.amro.pro: `ODOO_USERNAME=a.afifi@numo.sa` + `ODOO_API_KEY` (XML-RPC works for inspection).

### Suite runner

```bash
python3 /tmp/htf_e2e_check.py     # P0  → 59/59
python3 /tmp/htf_p1_check.py      # P1  → 73/73
python3 /tmp/htf_p2_check.py      # P2  → 63/63
python3 /tmp/htf_p3_check.py      # P3 backend → 24/24
python3 /tmp/htf_p3_ui_check.py   # P3 UI → 17/17
python3 /tmp/htf_p4_check.py      # P4  → 39/39
```

Each suite's source is also under `htf_call_center/tools/htf_*_check.py`.

### Deploy to staging

```bash
ssh root@<server>  # vmi3095315
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/
git pull origin main

docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml stop web
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml run --rm web \
    odoo -d numo -u htf_call_center --stop-after-init --no-http --log-level=warn 2>&1 | tail -10
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml up -d web
sleep 6
docker logs --tail 30 web-erp-amro-pro
```

---

## Hatif live-UAT findings (critical knowledge)

Captured 2026-05-19 against the real Numo workspace + Numo's two
channels (أكاديمية نمو + الدعم الفني). Reality differs from the
apidog spec in several places — keep this list handy for any future
phase that touches Hatif data.

### Webhooks

1. **Hatif does NOT sign webhooks** despite the apidog spec claiming
   HMAC-SHA256 in `X-Voxa-Signature`. Live captures show
   `signature_headers={}` — no signature at all.
   - Workaround: `htf.config.dev_mode_skip_hmac=True` on every env.
   - Long-term: get Hatif to enable signing (support email
     drafted).

2. **Source IP observed:** `8.213.48.16` (single IP so far).
   Use for Nginx allowlist if going defense-in-depth before signing
   is fixed.

3. **Composite event-id idempotency** (`<callId|messageId>:<status>:<direction>`)
   is critical because Hatif reuses the same ID across the
   lifecycle (Active → Completed for calls; Pending → Sent →
   Delivered → Read for WA messages).

### Call payload behaviour

4. **Hatif sends `status=8`** ~1 second before `status=2` (Missed).
   We map 8 → 'ringing'. Undocumented in apidog.

5. **Analytics threshold ~30s.** Calls < 30s get a transcript only
   (sometimes), no summary, no sentiment, no evaluationCriteriaResult.
   Hatif's own UI shows the warning
   *"This call is too short to analyse"*.

6. **Analytics arrive in the FIRST webhook** for calls ≥30s
   completed. We have NOT observed re-fired webhooks after enrichment
   — calls 5 + 6 (32s and 50s completed) had null analytics in
   their original webhook. Could be intermittent / per-channel
   config. Question (e) in the support email asks about this.

7. **Hatif's `Missed` status doesn't mean "nobody answered"** — it
   means "the intended human agent didn't pick up". The call CAN
   have `pickup_time` + duration + recording (auto-responder / IVR
   / unmapped agent answered). Our `pickup_kind` computed field
   (human/system/none) is what reports should bucket on.

8. **Extra fields Hatif sends that aren't in apidog:**
   `csatRating`, `csatMethod`, `csatCollectedAt`, `isAiCall`, `callId`.
   All captured on `htf.call`.

### WhatsApp payload behaviour

9. **`messageId` is null on first inbound** sometimes — we synthesise
   a dedupe key from `conversationId + creationTime` to keep
   idempotency working.

10. **Same `messageId` reused** across the outbound STATUS lifecycle
    (Sent → Delivered → Read → Failed). Composite event-id splits
    them.

### Phone matching

11. **Saudi phone formats vary wildly:** `+966 56 ...`, `0561...`,
    `966056...`, `+966-56-...`. The `utils.phone.normalize_e164`
    KSA-aware wrapper handles them all; use it at every boundary.

### Hatif user mapping

12. **Hatif user emails ≠ Odoo logins** on Numo's workspace.
    Fuzzy Arabic-name matching is the practical default (شموس Hatif
    ↔ شموس Odoo with prefix-of name). `wizards/map_users.py:_suggest_user`
    implements two-stage: email-on-login → email-on-partner.email →
    fuzzy normalised name tokens.

### PII

13. Amr's real phone scrubbed from code+docs and replaced with
    `+966XXXXXXXXX` placeholder. Git history still has older
    commits with the number. **Never paste a real customer number
    into committed code/docs** — use the placeholder.

---

## Re-entry sequence (when you sit down)

1. Read this file first (you're doing it now).
2. Confirm staging is healthy:
   ```bash
   curl -I https://erp.amro.pro/web/login 2>&1 | head -3
   ```
3. Check git status / pull anything new:
   ```bash
   cd ~/numo-hatif-odoo && git status && git pull origin main
   ```
4. Run the local suites to confirm baseline still green:
   ```bash
   for s in e2e p1 p2 p3 p3_ui p4; do python3 /tmp/htf_${s}_check.py | tail -2; done
   ```
5. Ask Amr for the 4 P8 pre-build questions OR pick a different
   approved item from the queue.

---

## Where things are in the repo

```
htf_call_center/                       (vendor wrapper, fully shipped)
├── __manifest__.py
├── models/                            P0+P1+P2+P3+P4 models
├── controllers/                       webhook_whatsapp + webhook_call
├── services/                          auth, http, hmac, channels, tags,
│                                      workspace, contacts, contact_properties,
│                                      whatsapp_inbound, whatsapp, channel_resolver,
│                                      chatter, dnc_listener, calls
├── wizards/                           bind_channels, map_users, import_vcards,
│                                      send_whatsapp
├── views/                             htf_message_views, htf_call_views,
│                                      htf_channel_views, htf_tag_views,
│                                      htf_user_link_views, htf_contact_link_views,
│                                      htf_webhook_event_views, res_partner_views,
│                                      crm_lead_views, res_users_views, crm_team_views,
│                                      wizard_views, menus, res_config_settings_views
├── static/src/views/fields/phone/     htf_phone OWL widget (Call + WhatsApp btns)
├── tools/
│   ├── replay_webhook.py              CLI replay tool
│   ├── signal_smoke.py                signal bus harness
│   ├── htf_p2_check.py                63 assertions
│   ├── htf_p3_check.py                24 assertions
│   ├── htf_p3_ui_check.py             17 assertions
│   ├── htf_p4_check.py                39 assertions
│   ├── fixtures/                      P2 webhook fixtures
│   └── pylint_htf_no_internal_import.py
└── docs/
    ├── planning/ (12 phase docs + STATUS.md, OPEN_QUESTIONS.md, RISK_REGISTER.md)
    ├── HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md   ← send-ready
    ├── hatif_apidog_export.json
    └── Hatif api.md

numo_crm_htf/                          (bridge — NOT YET CODED)
└── (empty — this is where P6+ work goes)
```

---

Welcome back. Don't skip THE DRILL (`/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md`).
Pick an item from the approved queue (P8 is #1) and start.

— end of NEXT_SESSION.md (clean handoff 2026-05-19)

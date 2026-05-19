# NEXT SESSION — start here

Last updated: **2026-05-19** — after live UAT confirmed P4 backend
+ Hatif analytics flowing (full Arabic summary + sentiment for
calls ≥ 30s) + fuzzy Arabic-name user mapping working.

---

## 🗒️ Amr's "do these later" queue (priority order)

All three big phases below are **approved by Amr** for build. Order is
priority — finish each before starting the next unless explicitly
re-prioritised. Open the corresponding planning docs for the spec.

1. **★ P8 — Outbound Sales Acceleration** ✅ APPROVED
   - Daily call queue per agent, click-to-call, pre-call brief panel,
     post-call wrap-up wizard auto-opens on htf.call.received,
     agent scorecard dashboard
   - ~12-16h, lives in `numo_crm_htf` bridge module
   - **Highest ROI** given 99% outbound reality — every Numo sales
     agent's daily workflow happens here
   - Pre-build questions (need answers before T8.1 starts):
       (a) What 'Outcome' options? (Interested / Not interested /
           Voicemail / Wrong number / Reschedule / …)
       (b) What 'Next step' options? (Send template — which? /
           Schedule callback / Move stage / Won / Lost / …)
       (c) Should the wrap-up wizard be MANDATORY or skippable?
       (d) Daily queue priority rule — default I proposed:
           `(activity deadline overdue) > (lead score) > (days since last touch)`.
           Want a Numo-specific rule instead?

2. **★ P9 — Speech Analytics via n8n** ✅ APPROVED
   - Now that transcripts + summaries are landing for calls ≥30s,
     ship the n8n bridge: post each completed htf.call to an n8n
     webhook → n8n calls LLM (Claude/GPT/whatever Numo picks) →
     n8n PUSHES back stage progression + agent score via JSON-RPC
   - Q-19 ANSWERED, Q-30 ANSWERED with n8n routing path
   - ~8h, lives in `numo_crm_htf` bridge
   - Depends on P8 being live so the wrap-up form can show LLM
     suggestions inline.

3. **★ P5 — Conversations Sync** ✅ APPROVED
   - Polling backfill insurance against missed webhooks; cron-polls
     Hatif `/conversations` and reconciles into htf.message + htf.call
   - Lower priority than P8/P9 since live UAT shows webhooks are
     flowing reliably so far; promote if/when we see lost events
   - ~6h, lives in htf_call_center wrapper

4. **Send Hatif support email**
   - Draft at `htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md`
   - Asks about (a) webhook signing, (b) source IP allowlist,
     (c) post-call webhook re-fire timing, (d) status=8 enum,
     (e) per-channel analytics toggle
5. **T4.5 transcript click-to-seek widget**
   - OWL polish — clicking a word in the transcript seeks the
     embedded audio player. ~3h. Browser-verify required.

---

## Morning checklist (in order)

### 1. Pull + upgrade on erp.amro.pro

```bash
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/
git pull origin main
# expect: de0f29b..de16663 (or later)

docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml stop web
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml run --rm web \
    odoo -d numo -u htf_call_center --stop-after-init --no-http --log-level=warn 2>&1 | tail -10
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml up -d web
sleep 6
```

### 2. Register Post-call Webhook URL on Hatif portal

For each channel at `https://app.hatif.io/en/settings/api-connect`:

- **Post-call Webhook URL:** `https://erp.amro.pro/htf/webhook/call`

(Same pattern as the WA webhook URL you already set yesterday. The
secret slot stays blank — Hatif still doesn't sign webhooks, so the
controller relies on `dev_mode_skip_hmac=True` which is already on
from yesterday's session.)

### 3. Place a test call

Call your phone → **+966 11 500 1591** (أكاديمية نمو). Let it ring,
either answer or miss. Either way Hatif sends a Post-call webhook
when the call ends.

### 4. Verify in Odoo

`https://erp.amro.pro/odoo` →

- **Hatif → Calls** menu (new today!) → your call should appear at
  the top with status (Completed / Missed / Failed), direction,
  duration, sentiment badge
- **Open the call row** → notebook tabs show Summary / Transcript /
  QA Rubric — all populated by Hatif's analytics
- **Open the partner** (auto-created or matched by phone) → chatter
  has a 📞 bubble with duration, recording link, summary preview
- **Smart buttons** on the partner form: `Calls` count, `WhatsApp`
  count — click either to drill into the filtered list

### 5. If it works → sign off P4 backend

Tell me "P4 live ✓" and I'll start either:
- P4 UI polish (T4.4 audio player + T4.5 click-to-seek transcript OWL
  widgets) — needs browser verification, defer if you're not in a
  testing mood
- P5 Conversations Sync — polling backfill insurance against missed
  webhooks
- Or just start P6 CRM Enrichment (the bridge module)

---

## What was shipped overnight

7 commits between the late-night signoff and this report:

```
de0f29b  docs: P2+P3 live-UAT session wrap-up + Hatif support note
637f823  feat(htf-call): P4 backend (T4.1 + T4.2 + T4.3 + T4.6)
de16663  test(htf-call): P4 E2E (39/39) + smart buttons on res.partner (T4.8)
<this>   docs(handoff): refresh after overnight P4 ship
```

Plus a few from the live-UAT session earlier today:
```
664a5e4  fix(outbound): proper E.164 canonicalization + PII scrub
738e33c  fix(outbound): canonicalize phones for whitelist comparison
aef4f14  fix(webhook): honor dev_mode_skip_hmac
ced6a98  debug(webhook): verbose HMAC failure diagnostics
77775a7  fix(ui): bind Bind-Channels wizard to ⚙ Actions menu
cdf83c8  feat(channels-ux): disable manual create + add Sync action
```

---

## Where we are

| Phase | Status |
|---|---|
| P0 Foundation | ✅ live on erp.amro.pro |
| P1 Channels + Contacts + Users | ✅ live (2 channels, 7 users, 1 tag) |
| P2 WhatsApp Inbound | ✅ **LIVE-UAT'd** — real phone → Odoo chatter |
| P3 WhatsApp Outbound | ✅ **LIVE-UAT'd** — Odoo wizard → real phone |
| P4 Calls Webhook | ✅ **backend shipped + tested**, live UAT pending step 3 above |
| P5 Conversations Sync | — |
| P6 CRM Enrichment | — |
| P7 Reporting + Differentiators | — |
| P8 Outbound Sales Acceleration | — |
| P9 Speech Analytics via n8n | — |

E2E scoreboard:
- P0 → 59/59
- P1 → 73/73
- P2 → 63/63
- P3 backend → 24/24
- P3 UI → 17/17
- P4 → 39/39
- **Total local: 275/275**

GitHub: https://github.com/AmroSamir/numo-hatif-odoo (branch `main`)

---

## P4 — what the model captures

`htf.call` is 33 fields covering Hatif's full Call Webhook payload:

| Group | Fields |
|---|---|
| Routing | direction (inbound/outbound), status (8-way enum), channel_id, partner_id, handler_user_id |
| Phones | caller_number, callee_number, contact_number |
| Timing | created_at, pickup_time, hangup_time, duration_seconds (auto), call_length_raw |
| Analytics | recording_url, transcription_text, transcription_words_json, summary, sentiment, evaluation_criteria_json |
| Hatif IDs | htf_call_id (unique), workspace_uuid, contact_uuid, ai_agent_uuid |
| Audit | chatter_message_id (back-ref), raw_payload |

Signal dispatch:
- `status=completed` → `htf.call.received`
- `status in {missed, no_answer, rejected_by_callee, cancelled}` → `htf.call.missed`
- `status=failed` → `htf.call.failed`
- `status=active` → no signal (call still in flight)

---

## Notes for live UAT verification

### What to expect from Hatif's analytics on a real call

Per the Hatif Call Webhook spec, when a call completes Hatif POSTs us:

```json
{
  "id": "<call-uuid>",
  "workspaceId": "...",
  "channelId": "3a20ffce-cc80-7229-8300-a394d13725a4",
  "status": 1,   // Completed
  "type": 1,     // Inbound
  "callerNumber": "+966XXXXXXXXX",
  "calleeNumber": "+966115001591",
  "pickupTime":  "2026-05-19T08:30:00Z",
  "hangupTime":  "2026-05-19T08:35:32Z",
  "callLength":  "00:05:32",
  "userId":      "<hatif-user-uuid>",   // agent who picked up
  "userName":    "سامي العنزي",
  "contactId":   "<hatif-contact-uuid>",
  "contactNumber": "+966XXXXXXXXX",
  "recordingUrl": "https://cdn.hatif/calls/...mp3",
  "transcription": {
    "text": "Full transcript ...",
    "words": [{"text":"...","start":0.0,"end":0.4,"type":"word","speaker":"agent"}, ...]
  },
  "summary": "AI-generated summary ...",
  "sentiment": 1,   // Positive
  "evaluationCriteriaResult": [{"id":"...","description":"Greeted properly","value":"Yes","rationale":"..."}, ...],
  "creationTime": "2026-05-19T08:30:00Z"
}
```

If any field is missing on a real call, that's a Hatif analytics gap
(not our bridge). Note it and we'll handle the falsy case gracefully —
the dispatcher already does `(payload.get('field') or False)` on
everything optional.

### Likely first-call observations

- **Status starts as Active (0)** when the call connects. Hatif may
  send a webhook for this BEFORE the call ends. Our dispatcher will
  create the htf.call row with status='active' and no analytics
  fields populated, then UPDATE it in-place when the post-call
  payload arrives. Single row across the lifecycle.
- **First inbound from a new caller creates a placeholder partner**
  named `Hatif Contact <short-uuid>` if Hatif's contactId is new.
  Once Hatif's contact-sync polling catches up (P1 cron), the name
  + phone get backfilled. You can also manually rename to the real
  customer once you know who they are.
- **handler_user_id may be empty** if the Hatif userId hasn't been
  mapped to an Odoo user via the Map Users wizard. The hatif_user_name
  string still shows so chatter is readable.

### What if a real call shows up weird

Paste the offending row's `raw_payload` field (Audit tab on the call
form) — that's the exact bytes Hatif sent. I can reverse-engineer
any field shape mismatch and ship a fix in minutes.

---

## Still-deferred items

| Task | Why deferred |
|---|---|
| T4.4 audio player OWL widget | Needs browser verification (Playwright Chrome not installed locally) |
| T4.5 click-to-seek transcript OWL widget | Same OWL constraint |
| T4.10 missed-call activity creator | Belongs in `numo_crm_htf` bridge (P6) |
| T3.4 full chatter composer patch | Lite header button covers main UX; full patch is heavy OWL work |
| Nginx IP allowlist for Hatif source IPs | Defense-in-depth follow-up to the unsigned-webhook reality |
| Email Hatif support about webhook signing | Draft ready at `htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md` — just send it |

---

## Suite-runner reference

```bash
python3 /tmp/htf_e2e_check.py     # P0  → 59/59
python3 /tmp/htf_p1_check.py      # P1  → 73/73
python3 /tmp/htf_p2_check.py      # P2  → 63/63
python3 /tmp/htf_p3_check.py      # P3 backend → 24/24
python3 /tmp/htf_p3_ui_check.py   # P3 UI → 17/17
python3 /tmp/htf_p4_check.py      # P4  → 39/39
```

All six must stay green. They use the same shared HMAC secret
(`p2-test-secret`) so they can run in sequence without
ormcache-invalidation races on the running worker.

---

## How the bridge is laid out (refresher)

```
htf_call_center/
├── __manifest__.py
├── models/
│   ├── htf_config.py       singleton config (params)
│   ├── htf_webhook_event.py idempotency
│   ├── htf_channel.py
│   ├── htf_message.py     WA messages (P2)
│   ├── htf_call.py        ← NEW (P4)
│   ├── htf_user_link.py
│   ├── htf_contact_link.py
│   ├── htf_tag.py
│   ├── res_partner.py     +x_htf_* extension + smart buttons (T4.8)
│   ├── res_users.py
│   ├── crm_team.py
│   └── res_config_settings.py
├── controllers/
│   ├── webhook_whatsapp.py
│   └── webhook_call.py    ← NEW (P4)
├── services/
│   ├── auth.py
│   ├── http_client.py
│   ├── hmac_verify.py
│   ├── channels.py
│   ├── tags.py
│   ├── workspace.py
│   ├── contacts.py
│   ├── contact_properties.py
│   ├── whatsapp_inbound.py
│   ├── whatsapp.py        outbound + retry
│   ├── channel_resolver.py
│   ├── chatter.py         +post_call (T4.6)
│   ├── dnc_listener.py
│   └── calls.py           ← NEW (P4 T4.3)
├── views/
│   ├── htf_message_views.xml
│   ├── htf_call_views.xml ← NEW (P4 T4.1)
│   ├── res_partner_views.xml (+smart buttons xpath)
│   ├── crm_lead_views.xml
│   ├── wizard_views.xml
│   ├── menus.xml          +Calls menu under Hatif
│   └── ... (channel, tag, user_link, etc.)
├── wizards/
│   └── send_whatsapp.py
├── tools/
│   ├── replay_webhook.py    can drive /htf/webhook/whatsapp too
│   ├── htf_p2_check.py
│   ├── htf_p3_check.py
│   ├── htf_p3_ui_check.py
│   ├── htf_p4_check.py     ← NEW
│   ├── signal_smoke.py
│   └── fixtures/ (P2 only so far)
└── docs/
    ├── planning/ (10+ phase docs)
    ├── hatif_apidog_export.json
    └── HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md  ← draft email
```

---

Welcome back. Don't skip THE DRILL. Have a coffee, do the 4-step
morning checklist, watch a real call land in Odoo.

— end of NEXT_SESSION.md

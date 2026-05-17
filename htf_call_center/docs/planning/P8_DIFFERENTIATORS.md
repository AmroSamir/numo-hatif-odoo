# Phase P8 — Differentiators (optional)

**Modules:** `htf_call_center` + `numo_crm_htf`
**Effort:** 16–24 dev hrs (optional, post-MVP)
**Depends on:** P0–P7 complete
**Blocks:** none

## Goal

Polish features that distinguish this from a basic vendor wrapper. Optional. Each subphase ships independently.

---

## Sub-phase P8.A — DNC + opt-out keyword listener (3h)

### Tasks
- T8.A.1 `htf.dnc` model per DATA_MODEL.md
- T8.A.2 `services/dnc.py` with `is_blocked`, `block`, `unblock`, `opt_out_keywords`
- T8.A.3 In bridge `handle_wa_inbound`: regex match against opt_out keywords (Arabic + English) → auto-DNC + signal `htf.dnc.added`
- T8.A.4 Auto-set `partner.x_htf_opted_out = True`
- T8.A.5 Pre-flight check in `whatsapp.send_*` raises `HtfDncBlockedError`
- T8.A.6 Admin UI: list, manual add, manual unblock with reason audit
- T8.A.7 Tests: each keyword variant, unblock, override

### Acceptance
- Customer texts "STOP" → next outbound blocked
- Customer texts "إلغاء الاشتراك" → blocked
- Manual unblock requires admin role
- Audit trail on partner chatter

---

## Sub-phase P8.B — Cost tracking + reporting (3h)

### Tasks
- T8.B.1 Per-message `meta_category` already on htf.message; ensure all sends tag correctly
- T8.B.2 Daily aggregation cron → `numo_crm_htf.daily_cost_summary`
- T8.B.3 Dashboard tile in numo_crm 3D analytics: today's WA cost by category, by channel, by team
- T8.B.4 Monthly export CSV
- T8.B.5 Tests

### Acceptance
- Marketing send shows $0.024 estimate
- Service window send shows $0
- Daily summary matches sum of htf.message rows

---

## Sub-phase P8.C — PII redaction (2h)

### Tasks
- T8.C.1 Regex library: Saudi NID `\b\d{10}\b`, IBAN `\bSA\d{22}\b`, credit card Luhn-checked, KSA mobile patterns
- T8.C.2 `services/pii_redactor.py` with `redact(text)`
- T8.C.3 Apply to call transcription on persistence (configurable `htf.config.redact_transcripts`, default False)
- T8.C.4 Apply to AI summary when `redact_summaries=True`
- T8.C.5 Audit field `htf.call.transcription_was_redacted`
- T8.C.6 Tests with realistic samples

### Acceptance
- Saudi NID in transcript → masked as `XXX-XXX-XXX`
- IBAN masked
- Credit card masked (last 4 visible)
- Toggle off → no redaction

---

## Sub-phase P8.D — Arabic IVR prompts library (2h)

### Tasks
- T8.D.1 Pre-recorded WAV files (8kHz mono pcm_s16le) for common phrases
- T8.D.2 Upload via `services/audio.upload()` once at install time
- T8.D.3 Store URLs in `numo_crm_htf.ivr_action_config` (welcome_url, success_url, failed_url)
- T8.D.4 Document content of each prompt in MARKDOWN under data/audio_library/

### Acceptance
- Each common config_key has Arabic welcome/success/failed prompts
- Replaces TTS for higher voice quality
- Library updateable by admin

---

## Sub-phase P8.E — Won-back campaigns (3h)

### Tasks
- T8.E.1 Cron `numo_crm_htf.cron.won_back` daily
- T8.E.2 Find leads where: stage_id.is_won=False AND active=False AND lost_at older than 30/60/90 days
- T8.E.3 Send template `winback-30d` / `winback-60d` / `winback-90d` (admin-configurable mapping)
- T8.E.4 Stop after first reply or first new activity
- T8.E.5 Track in `numo_crm_htf.won_back_log`
- T8.E.6 Tests

### Acceptance
- Lead lost 30 days ago → receives template tomorrow
- Reply → stops further nudges
- Audit trail visible per lead

---

## Sub-phase P8.F — Schedule callback widget (2h)

### Tasks
- T8.F.1 OWL component "Schedule callback" on missed-call activity
- T8.F.2 Date+time picker → creates `mail.activity` of type "Phone Call" with deadline
- T8.F.3 At deadline + 5 min, cron fires Hatif IVR notify-agent OR creates urgent task
- T8.F.4 Tests

### Acceptance
- Agent sees missed call activity → click "Schedule callback" → set future date → activity rescheduled
- Past-due → reminder fires

---

## Sub-phase P8.G — Reports dashboard tile (3h)

### Tasks
- T8.G.1 `numo_crm_htf` adds tiles to numo_crm 3D analytics:
  - "Calls today" with answer rate
  - "WA Sent / Read" funnel
  - "Avg sentiment" gauge
  - "Top tags" bar
- T8.G.2 OWL components inside existing dashboard
- T8.G.3 Tests

### Acceptance
- Tiles render correctly
- Data refreshes hourly
- Mobile-friendly

---

## Sub-phase P8.H — Recording cache to attachment (2h)

### Tasks
- T8.H.1 Setting `htf.config.cache_recordings_on_play`
- T8.H.2 First play → download to ir.attachment, replace recording_url with /web/content URL
- T8.H.3 Cron purges cached recordings older than retention setting (default 90 days)
- T8.H.4 Tests

### Acceptance
- First play populates cache
- Subsequent plays use Odoo URL
- Purge cron respects retention
- Permission: only users who can see the call can stream

---

## Done definition

For each sub-phase that ships:
- Tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p8-<letter>-done`

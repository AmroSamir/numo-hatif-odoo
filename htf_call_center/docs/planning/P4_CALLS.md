# Phase P4 — Calls Webhook

**Module:** `htf_call_center`
**Effort:** 10–14 dev hrs
**Depends on:** P0, P1, P2 (chatter helper)
**Blocks:** P5 partial, P7 CRM enrichment

## Goal

Every call (inbound or outbound, answered or missed) becomes a record in Odoo, posted to the right partner/lead chatter with audio, transcription, AI summary, sentiment, and QA scorecard. Live calling stays in Hatif's app.

## Blocked-by

- Q-06 (recording retention + URL expiry) — informs T4.9 cache strategy
- Q-12 (sandbox phone for E2E) — for UAT

## Mitigates

- R-04 (Hatif API breaking change) → T4.2 fixture-vs-live drift test
- R-11 (recording URL expiry) → T4.9 cache option

## Acceptance criteria

- [ ] `POST /htf/webhook/call` accepts valid HMAC, rejects invalid
- [ ] Idempotent on retries
- [ ] `htf.call` row persisted with all fields from payload
- [ ] Auto-link to `res.partner` via E.164 phone match
- [ ] Caller-unknown → auto-create partner + lead
- [ ] Missed call → auto-create `mail.activity` of type "Phone Call"
- [ ] Audio player widget renders in chatter card
- [ ] Transcription view supports word-level click-to-seek
- [ ] AI summary card visible
- [ ] Sentiment badge with color
- [ ] Evaluation criteria as QA rubric table
- [ ] Signals fire correctly: `htf.call.received`, `htf.call.missed`, `htf.call.failed`

## Tasks

### T4.1 — `htf.call` model (1h)
- Per DATA_MODEL.md
- Status enum mapping (int → string)
- Direction enum mapping (1=in, 2=out)
- Sentiment enum mapping (1–5)
- Computed `name` and `duration_seconds`
- View: list + form (admin debug)

### T4.2 — Webhook controller (1.5h)
- `controllers/webhook_call.py`
- Route `POST /htf/webhook/call` `csrf=False auth='public'`
- HMAC verify
- Idempotency via `htf.webhook.event` with `(callId or webhookId, 'call')`
- Parse + dispatch to handler
- Tests: HMAC fail, dup, schema variants

### T4.3 — Call dispatcher service (2h)
- `services/calls.py`:
  - `handle_webhook(payload)`:
    - Persist `htf.call` (or update if exists)
    - Lookup channel by `channelId` → channel.team_id
    - Resolve partner: lookup_partner by callerNumber (inbound) or calleeNumber (outbound)
    - If not found AND inbound → auto-create partner with phone, name=phone, **team_id=channel.team_id** (so future leads inherit team)
    - Resolve handler_user via htf.user.link
    - For inbound + auto-create scenario: also auto-create crm.lead with team_id=channel.team_id, source="Hatif Inbound — <channel.display_name>"
    - For inbound + missed scenario without existing lead: route to channel.team_id using channel.team.x_htf_routing_strategy (lead_owner / round_robin / least_busy)
    - Post chatter (T4.6)
    - Fire signal:
      - status=Completed (1) → `htf.call.received`
      - status in [Missed=2, NoAnswer=5, RejectedCallee=4, Cancelled=6] → `htf.call.missed`
      - status=Failed (7) → `htf.call.failed`
- Phone normalization via utils.phone
- Tests: each status path + auto-create + signal payload

### T4.4 — Audio player widget (1.5h)
- `static/src/components/HatifAudioPlayer/`
- Wraps HTML5 `<audio controls>` with seekbar enhanced
- Accepts URL prop
- Uses Odoo session for auth-less stream (recordingUrl is signed by Hatif)
- Tests: snapshot

### T4.5 — Transcription widget (2h)
- `static/src/components/HatifTranscript/`
- Renders chat-style speaker bubbles (agent / user / unknown)
- Each word clickable → emit `seek(time)` event consumed by audio player
- Collapsed by default, expand toggle
- Search-within-transcript box
- Tests: rendering, click-to-seek event

### T4.6 — Chatter post for calls (1.5h)
- Extend `services/chatter.py`:
  - `post_call(htf_call)`:
    - Header line: 📞 [Inbound|Outbound] • duration • handler
    - Subject: derived
    - Body: QWeb template renders audio player + transcript + AI summary + sentiment + QA
    - author = handler_user_id (or service-account user)
    - Post to partner.message_ids; if `lead_id`, also post to lead chatter (Odoo natively cascades chatter; verify behavior)
- Tests: rendering + author resolution + lead duplication-vs-cascade

### T4.7 — Phone widget call-button wired (0.5h)
- 📞 button on phone widget triggers Hatif app deep-link
- Optional: also calls `htf_call_center.services.calls.notify_outbound_starting()` to pre-create a stub `htf.call` row for tracking — only if Hatif supports it; otherwise wait for webhook
- Tests: deep-link URL format

### T4.8 — Lead form smart buttons (1h)
- `views/res_partner_views.xml` adds smart button "Calls" (count) → opens filtered list
- Same for crm.lead (in P7 bridge for Numo-specific styling, or basic version here)
- View: `htf_call_views.xml` — list, form, kanban, search filters

### T4.9 — Recording cache option (1h)
- Optional setting `htf.config.cache_recordings_on_play = bool`
- When user clicks play first time and setting on → `services/calls.cache_recording(call)` downloads to `ir.attachment`, replaces URL on next play
- Cron prunes recordings older than X days
- Tests: cache hit/miss

### T4.10 — Missed call activity creator (1h)
- Bridge subscribes to `htf.call.missed` (in P7) — but for v1, also do a basic activity creation in vendor wrapper (only if no bridge installed) gated by `htf.config.basic_missed_call_activity = True`
- Default behavior: do NOT create activity in vendor; let bridge handle. Vendor-only fallback only when bridge missing.
- Tests: activity created with correct type, deadline=today, assigned_to=lead.user_id or partner.user_id

## P4 UAT checklist

1. [ ] Hatif team replays a completed-call webhook → chatter post within 5s on the right partner/lead
2. [ ] Audio plays from chatter without re-fetching
3. [ ] Click a transcript word → audio seeks to that timestamp
4. [ ] AI summary card visible + readable
5. [ ] Sentiment shown as colored badge
6. [ ] QA rubric table renders evaluationCriteriaResult correctly
7. [ ] Missed-call webhook → activity created on lead
8. [ ] Caller-unknown number → new partner + new lead created
9. [ ] Spoofed POST → 401, no rows
10. [ ] Two near-simultaneous webhooks for same call (Hatif retry) → exactly one chatter post

## Files delivered

```
htf_call_center/
├── models/
│   └── htf_call.py
├── controllers/
│   └── webhook_call.py
├── services/
│   └── calls.py
├── static/src/
│   └── components/
│       ├── HatifAudioPlayer/
│       └── HatifTranscript/
├── views/
│   ├── htf_call_views.xml
│   └── res_partner_views.xml
└── tests/
    ├── test_webhook_call.py
    ├── test_calls_service.py
    ├── test_audio_widget.py
    ├── test_transcript_widget.py
    └── fixtures/
        ├── webhook_call_completed.json
        ├── webhook_call_missed.json
        └── webhook_call_failed.json
```

## Risks specific to P4

- recordingUrl signed by Hatif may have short TTL → cache option for permanence
- Transcription word timing edge cases (overlap, silence) → graceful fallback to plain text
- Auto-create partner spam if attacker spoofs many unknown numbers → HMAC + rate limiter
- Lead matching ambiguity when partner has many open leads → pick most-recent + assigned-to-handler

## Done definition

- All tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p4-done`

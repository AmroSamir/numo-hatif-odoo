# Phase P2 — WhatsApp Inbound

**Module:** `htf_call_center`
**Effort:** 8–10 dev hrs
**Depends on:** P0, P1
**Blocks:** P3 (composer needs the inbound model + thread context)

## Goal

Inbound WhatsApp messages flow into Odoo's chatter on the matching res.partner — automatically — within seconds of the customer hitting send.

## Acceptance criteria

- [ ] `POST /htf/webhook/whatsapp` accepts valid HMAC, rejects invalid
- [ ] Webhook idempotent (duplicate event_id → no-op)
- [ ] `htf.message` row persisted per inbound message
- [ ] Unknown phone → auto-create `res.partner`
- [ ] Known phone → match existing partner
- [ ] mail.message posted to partner chatter with correct body, attachments, author
- [ ] Status updates (delivered, read, failed) update existing `htf.message` row, do NOT post duplicate chatter messages
- [ ] `partner.x_htf_last_inbound_at` updated → 24h-window opens
- [ ] Signal `htf.wa.inbound` fires with full payload
- [ ] Media (image/video/audio/document/sticker) attached to chatter via `ir.attachment`
- [ ] Location messages render with map link or coords
- [ ] Contact card messages render with vCard preview

## Tasks

### T2.1 — `htf.message` model (1h)
- Per DATA_MODEL.md
- Computed `name` (e.g. `[Inbound] +966… → Channel: Cambridge`)
- `_sql_constraints` unique htf_message_id
- View: list + form (admin debug)

### T2.2 — Webhook controller (2h)
- `controllers/webhook_whatsapp.py`
- Route `POST /htf/webhook/whatsapp` `csrf=False auth='public'`
- HMAC verify header → 401 on fail
- Idempotency: insert into `htf.webhook.event` with `(messageId, 'whatsapp')` UNIQUE → if conflict, return 200 immediately
- Parse payload schema (see API doc)
- Call dispatcher: inbound (Direction=Inbound) vs outbound status update
- Tests: HMAC fail, dup, schema variants

### T2.3 — Dispatcher: inbound messages (1.5h)
- `services/whatsapp_inbound.py`
- For each messageType:
  - Text: persist body
  - Image/Video/Audio/Document/Sticker: download `mediaUrl` (via Hatif fetch API or direct if URL public), create `ir.attachment` with `mimeType`, link
  - Location: persist lat/lon
  - Contact: persist body as vCard text
  - Template/Interactive: persist body as preview
- Match contactId → partner via `htf.contact.link`; if missing, auto-create partner
- Persist `htf.message` row
- Update `partner.x_htf_last_inbound_at = now`
- Post mail.message to partner chatter (see T2.4)
- **Fire signal `htf.wa.inbound` with payload per SIGNAL_BUS.md** (includes `is_opt_out_keyword` flag derived in T2.5b)
- Tests: each message type + auto-create partner + 24h window updates + signal payload shape

### T2.5b — Opt-out keyword detector (0.5h)
- `services/dnc_listener.py`:
  - `is_opt_out(text: str) -> bool` — case-insensitive whole-message match against keyword list (default: STOP, UNSUBSCRIBE, إلغاء, إلغاء الاشتراك, الغاء)
  - Keyword list from `htf.config.dnc_keywords` (configurable, comma-separated)
- Inbound dispatcher calls this on Text messages → sets `is_opt_out_keyword=True` in signal payload
- Bridge subscriber (P8.A) acts on it: creates `htf.dnc` row + flips `partner.x_htf_opted_out=True`
- Tests: each default keyword + Arabic variants + false-positive guard ("Stop, that's right" should NOT match — strict whole-message)

### T2.4 — Chatter posting helper (1.5h)
- `services/chatter.py`:
  - `post_inbound_wa(partner, htf_message)` → mail.message
  - `post_outbound_wa(partner, htf_message, sender_user)`
  - `post_call(partner, htf_call)` (used in P4)
- Body templating in QWeb (`data/mail_templates.xml`):
  - WA inbound bubble: avatar, time, body, attachments inline, status icons
  - WA outbound bubble: aligned right, sender name, status icons
- `htf_message.chatter_message_id = mail_message.id` for back-ref
- Tests: chatter post created, attachments visible, author_id correct

### T2.5 — Status update handler (1h)
- Hatif also delivers status webhooks (Sent/Delivered/Read/Failed) via the same endpoint with `direction=outbound`
- For outbound status: lookup `htf.message` by `messageId` (or `conversationEventId`), update `state` + error fields
- Update existing chatter mail.message body to refresh status icons (re-render)
- Fire signal `htf.wa.status` with old + new state
- Tests: each transition + missing-message-id graceful skip

### T2.6 — Signal subscription smoke test (0.5h)
- Register a dummy subscriber in tests
- Assert payload shape per SIGNAL_BUS.md

### T2.7 — UAT helpers (0.5h)
- Admin command-line helper script under `htf_call_center/tools/replay_webhook.py` to POST a JSON fixture to local server with valid HMAC
- Doc in DEPLOYMENT.md

## P2 UAT checklist

1. [ ] Hatif team replays a real text webhook → chatter post on the right partner ≤ 5s
2. [ ] Send image from Hatif portal → attachment visible in chatter
3. [ ] Repeat send (Hatif retry) → exactly one chatter post (idempotency)
4. [ ] Spoofed POST without HMAC → 401, no chatter post
5. [ ] Inbound from unknown number → new partner created, chatter exists
6. [ ] Status updates flow: customer sends, agent reads → ✓ then ✓✓ then ✓✓-blue without new chatter posts
7. [ ] 24h-window indicator on partner form shows green after inbound

## Files delivered

```
htf_call_center/
├── models/
│   └── htf_message.py
│   └── htf_webhook_event.py
├── controllers/
│   └── webhook_whatsapp.py
├── services/
│   ├── whatsapp_inbound.py
│   └── chatter.py
├── data/
│   └── mail_templates.xml
├── tools/
│   └── replay_webhook.py
└── tests/
    ├── test_webhook_whatsapp.py
    ├── test_whatsapp_inbound.py
    ├── test_chatter.py
    └── fixtures/
        ├── webhook_wa_inbound_text.json
        ├── webhook_wa_inbound_image.json
        ├── webhook_wa_status_delivered.json
        └── webhook_wa_status_read.json
```

## Risks specific to P2

- Media URL may be short-lived → cache asap to ir.attachment
- Sticker/Contact rendering may look ugly in standard chatter; OK for v1
- Replay attacks if timestamp window too wide → test with ±5 min
- Big media may exceed Odoo attachment limit → log + post text fallback

## Done definition

- All tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p2-done`

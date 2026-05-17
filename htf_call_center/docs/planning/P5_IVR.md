# Phase P5 — Outbound IVR (slim)

**Module:** `htf_call_center` (vendor) + `numo_crm_htf` (bridge wires action mapping)
**Effort:** 4–6 dev hrs
**Depends on:** P0, P1
**Blocks:** none

## Goal

Trigger a Hatif IVR call against a contact / lead from inside Odoo, without building any IVR-script editor in Odoo. Hatif's portal owns the script. Odoo just calls the API and reacts to the result webhook.

## Acceptance criteria

- [ ] `IvrService.trigger()` works end-to-end against Hatif sandbox
- [ ] `htf.ivr.run` row persisted per trigger with `external_id` for idempotency
- [ ] IVR result webhook received, persisted, signal fired
- [ ] Bulk action "Trigger Hatif IVR" on partner/lead list view
- [ ] Bridge maps digits → server actions per `ivr_action_config` data row
- [ ] Re-running same external_id is no-op

## Tasks

### T5.1 — `htf.ivr.run` model (1h)
- Per DATA_MODEL.md
- View: list + form (admin debug)

### T5.2 — `services/ivr.py` (1h)
- `IvrService(env)`:
  - `trigger(...)` per API_CONTRACT.md
    - Build payload from kwargs OR from `numo_crm_htf.ivr_action_config[config_key]` if `config_key` provided
    - POST `/v1/outbound-ivr` with auth
    - Persist `htf.ivr.run` row (status=initiated, external_id supplied or generated UUID)
    - Return record
- Idempotency: if same external_id already exists → return existing row, do not POST
- Tests: idempotency + payload shape + each kwarg variant

### T5.3 — Webhook controller (1h)
- `controllers/webhook_ivr.py`
- Route `POST /htf/webhook/ivr` `csrf=False auth='public'`
- HMAC verify
- Idempotency on `(id, 'ivr')`
- Lookup run by `htf_ivr_id` or `externalId`
- Update fields from payload
- Fire signal `htf.ivr.result`
- Tests: HMAC fail, dedup, status transitions

### T5.4 — Bulk action (0.5h)
- `data/server_actions.xml`: action "Trigger Hatif IVR" on res.partner + crm.lead
- When invoked: opens wizard `wizards/trigger_ivr.py`
  - Field: config_key (Selection from `ivr_action_config` rows)
  - For each selected record → call `IvrService.trigger(config_key=..., partner=..., lead=...)`
- Tests: bulk loop + per-record idempotency

### T5.5 — Bridge: ivr_action_config data + handler (1h)
- In `numo_crm_htf/data/ivr_action_config.xml`:
  - `appointment-confirm` (digit 1 → confirm, 2 → cancel)
  - `payment-reminder` (digit 1 → confirm received, 2 → request agent)
  - additional cases per Numo team
- In `numo_crm_htf/models/htf_event_handler.py`:
  - Subscribe to `htf.ivr.result`
  - Look up config_key → digit_to_action_map_json → call mapped Python method (e.g. `_action_confirm_appt`, `_action_cancel_appt`)
  - Update lead fields, create activities, change stage as needed
- Tests: each digit path

### T5.6 — Audio uploader helper (0.5h)
- `services/audio.py`:
  - `upload(file_bytes, mime)` POST `/v1/support/upload-audio` → returns hosted URL
- Used when admin wants Odoo-hosted audio (rare; mostly uses Hatif's internal recordings)
- Tests: success + size limit

## P5 UAT checklist

1. [ ] Trigger one-off IVR via wizard from a partner — Hatif dials, plays TTS
2. [ ] Press digit 1 on phone → webhook fires → lead has `x_htf_appt_confirmed=True` + activity completed
3. [ ] Press digit 2 → lead moves to lost stage
4. [ ] No-input → activity "Manual reminder" scheduled
5. [ ] Bulk-select 5 leads → action "Trigger Hatif IVR" → 5 runs, 5 webhooks, 5 outcomes
6. [ ] Re-run same external_id → no duplicate dial, idempotent
7. [ ] Spoofed webhook → 401

## Files delivered

```
htf_call_center/
├── models/
│   └── htf_ivr_run.py
├── services/
│   ├── ivr.py
│   └── audio.py
├── controllers/
│   └── webhook_ivr.py
├── wizards/
│   └── trigger_ivr.py
├── data/
│   └── server_actions_ivr.xml
└── tests/
    ├── test_ivr_service.py
    ├── test_webhook_ivr.py
    └── fixtures/
        ├── webhook_ivr_digit_pressed.json
        └── webhook_ivr_no_input.json

numo_crm_htf/
├── data/
│   └── ivr_action_config.xml
├── models/
│   └── htf_event_handler.py    (digit→action mapping methods)
└── tests/
    └── test_ivr_action_handlers.py
```

## Risks specific to P5

- Hatif `Options` enum (`*` and `#` valid) edge cases — test
- Concurrent triggers same number → Hatif may queue or reject; test
- TTS pronunciation of Arabic names → fallback to audio file URL when name needed
- Audio upload size limit 10MB → enforce client-side

## Done definition

- All tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p5-done`

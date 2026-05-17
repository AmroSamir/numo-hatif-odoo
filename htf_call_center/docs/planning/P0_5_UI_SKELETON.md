# Phase P0.5 — UI Skeleton with Mock Data

**Module:** `htf_call_center` (vendor) + `numo_crm_htf` (bridge — partial scaffold)
**Effort:** 12–16 dev hrs
**Depends on:** P0
**Blocks:** P1 onward (skeleton must be UAT-signed before backend wiring starts)

## Goal

Ship the entire UI surface — every model, view, OWL widget, wizard, menu, smart button, chatter post format — populated with realistic seed data and exercised by a webhook replay tool. Amr clicks through everything, gives feedback, signs off. Real Hatif backend wiring starts only after that gate.

**Why before P1+:** UI feedback is cheap to apply now, expensive once real services are wired in. Catches UX bugs without burning Hatif sandbox quota or risking real customer interactions.

## Acceptance criteria

- [ ] Both modules install + uninstall cleanly on staging
- [ ] All 16 models from DATA_MODEL.md exist (schema only, no real service logic)
- [ ] All views render: list, form, kanban, search per model
- [ ] All OWL components (7) render with seed data
- [ ] All wizards (5) work end-to-end with mock services
- [ ] Phone widget swap visible on res.partner + crm.lead phone fields
- [ ] Chatter posts (call card + WA bubbles) render correctly with sample data
- [ ] Send WA wizard writes htf.message + chatter post (no real Hatif call)
- [ ] Replay Webhook tool fires sample JSON payloads through real handler → chatter posts appear
- [ ] Smart buttons show counts on partner/lead
- [ ] Pipeline filters work (sentiment, channel, last contact age)
- [ ] Settings page renders all sections (creds, channels, tags, mapping, DNC, secrets)
- [ ] Daily digest manual-trigger button generates plausible email preview
- [ ] CI rule: `services/_mocks/` never imported outside `_mocks/` and tests
- [ ] All mock services tagged with `# REPLACE IN P{N}: <real call>` comment

## Tasks

### T0.5.1 — All models scaffolded (3h)
Create model files for every entity in DATA_MODEL.md. Schema only, no business methods (placeholders return `True` or empty recordsets).

Files in `htf_call_center/models/`:
- htf_config.py (already in P0)
- htf_channel.py
- htf_tag.py
- htf_user_link.py
- htf_contact_link.py
- htf_conversation.py
- htf_conversation_event.py
- htf_call.py
- htf_message.py
- htf_message_template.py
- htf_ivr_run.py
- htf_dnc.py
- htf_webhook_event.py
- res_partner.py (extension fields)
- res_users.py (extension fields)
- crm_team.py (extension fields)

Files in `numo_crm_htf/models/`:
- crm_lead.py (extension fields per DATA_MODEL.md)
- res_partner.py (bridge-side extensions)
- htf_event_handler.py (placeholder AbstractModel — subscribes nothing yet)
- numo_crm_htf_daily_digest_log.py
- numo_crm_htf_ivr_action_config.py

All `__init__.py` files. Security CSVs stub (allow all to admin, restricted to user group for visible models).

### T0.5.2 — All views (3h)
Per DATA_MODEL.md, ship list + form (+ kanban where useful) for every model:

`htf_call_center/views/`:
- htf_channel_views.xml (list editable + form + search)
- htf_tag_views.xml
- htf_user_link_views.xml
- htf_contact_link_views.xml
- htf_conversation_views.xml (kanban grouped by status, list, form)
- htf_conversation_event_views.xml (list inside conversation form)
- htf_call_views.xml (list + form + search)
- htf_message_views.xml (list + form + search)
- htf_message_template_views.xml (list + form)
- htf_ivr_run_views.xml (list + form)
- htf_dnc_views.xml (list + form)
- htf_webhook_event_views.xml (list, admin-only)
- res_partner_views.xml (Hatif tab + smart buttons + phone widget)
- res_users_views.xml (Hatif user link field, admin-only)
- res_config_settings.xml (Settings → Hatif page with all tabs)
- crm_team_views.xml (Hatif Channels tab + routing strategy)
- menus.xml (admin menus only)

`numo_crm_htf/views/`:
- crm_lead_views.xml (AI summary card + sentiment trend + channel badge + smart buttons)
- crm_pipeline_views.xml (filters: sentiment, channel, last contact age)
- res_partner_views.xml (CRM-specific extensions)

### T0.5.3 — OWL components (3h)
All 7 reusable widgets, working with seed data:

`htf_call_center/static/src/components/`:
- `HatifPhoneField/` — extends phone widget, adds 📞 deep-link + 💬 wizard trigger
- `HatifAudioPlayer/` — HTML5 audio with seekbar, accepts URL prop
- `HatifTranscript/` — speaker-labeled chat bubbles, click-to-seek event
- `HatifChatterComposer/` — chatter composer extension with WA toggle + channel picker

`numo_crm_htf/static/src/components/`:
- `AiSummaryCard/` — markdown render of `lead.x_htf_pinned_summary`
- `SentimentTrend/` — sparkline chart from `lead.x_htf_sentiment_history_json`
- `ChannelBadge/` — last channel icon + last contact time chip

Asset bundles registered. Snapshot tests on each.

### T0.5.4 — All wizards (1.5h)
- `wizards/send_whatsapp.py` (vendor)
- `wizards/map_users.py` (vendor)
- `wizards/import_vcards.py` (vendor)
- `wizards/bind_channels.py` (vendor)
- `wizards/trigger_ivr.py` (vendor)
- `wizards/bulk_send_wa.py` (bridge — mock pre-flight panel)

Each wizard's submit handler calls a mock service, persists local rows, posts chatter, returns success — no real Hatif HTTP.

### T0.5.5 — Mock services (1.5h)
Under `htf_call_center/services/_mocks/`:
- `mock_whatsapp.py` — `send_text` and `send_template` write `htf.message`, post chatter, fake `conversationEventId`
- `mock_calls.py` — `lookup_partner` works (real local lookup), `cache_recording` is no-op
- `mock_ivr.py` — `trigger` writes `htf.ivr.run`, returns synthetic response
- `mock_contacts.py` — `upsert_from_partner` mirrors locally only
- `mock_channels.py` — `sync_from_htf` returns hardcoded channel list
- `mock_workspace.py` — `list_users` returns hardcoded workspace users
- `mock_tags.py` — local CRUD only
- `mock_audio.py` — `upload` returns fake URL

`htf.config.get_service('<name>')` returns mock implementation when `htf.config.dev_mode_use_mocks=True` (default in P0.5, flipped to False in P1+).

### T0.5.6 — Seed data fixtures (1h)
`htf_call_center/data/demo/`:
- `demo_channels.xml` — 5 channels (matching real Numo numbers, fake UUIDs)
- `demo_teams.xml` — bind channels to existing crm.team rows
- `demo_tags.xml` — 8 tags (VIP, Cold, Hot, Cambridge, NH, etc.)
- `demo_workspace_users.xml` — 4 fake Hatif users + 1 AI agent

`numo_crm_htf/data/demo/`:
- `demo_leads.xml` — 10 leads in various stages with x_htf fields populated
- `demo_calls.xml` — 30 fake `htf.call` rows linked to leads (mix of inbound/outbound, completed/missed/answered, with sample transcripts + AI summaries + sentiment)
- `demo_messages.xml` — 50 fake `htf.message` rows (text + template, mix of states)
- `demo_conversations.xml` — 15 conversations with timeline events

Seed data only loads when module installed with `--demo` flag (Odoo standard).

### T0.5.7 — Replay Webhook tool (1h)
`htf_call_center/tools/replay_webhook.py` + admin form:
- Settings → Hatif → Replay Webhook
- Dropdown of sample payload fixtures (call_completed, call_missed, wa_inbound_text, wa_inbound_image, wa_status_delivered, wa_status_read, ivr_digit_pressed, ivr_no_input)
- Editable JSON textarea (pre-filled from selected fixture)
- "Replay" button → POSTs to `/htf/webhook/<route>` locally with **DEV mode** flag set (skips HMAC)
- Result panel shows: status code, created records, chatter posts, signal fires

Same fixture set as `tests/fixtures/` from P0 — single source.

### T0.5.8 — DEV mode flag (0.5h)
`htf.config`:
- `dev_mode_skip_hmac = Boolean(default=False)` — only togglable when `debug_log_enabled=True` AND admin-only
- Webhook controllers honor flag: skip HMAC, accept any payload
- Settings page banner if dev mode on (red strip "DEV MODE — webhooks unsigned")
- Tests: flag must be FALSE in production checklist

### T0.5.9 — Mock-import lint rule (0.5h)
Custom pylint rule: `services/_mocks/*` may only be imported by `services/_mocks/`, `tests/`, `htf_config._get_service_factory`. Any other import fails CI.

### T0.5.10 — UAT walkthrough script (1h)
`docs/planning/P0_5_UAT_CHECKLIST.md`:
1. Install both modules with demo data
2. Visit res.partner — verify Hatif tab + smart buttons
3. Click 📞 next to phone → deep-link triggers (verify URL)
4. Click 💬 next to phone → Send WA wizard opens, channel pre-picked
5. Submit Send WA wizard → chatter post bubble appears, message row exists
6. Visit crm.lead — verify AI summary card, sentiment trend, channel badge
7. Click smart buttons (Calls, WA, IVR Runs) — verify filtered lists
8. Settings → Hatif → Replay Webhook → fire `call_completed` fixture → chatter post + activity created
9. Settings → Hatif → Channels → list 5 channels, edit team binding inline
10. Settings → Hatif → Bind Channels wizard — change a binding, verify Save
11. Settings → Hatif → Map Users wizard — auto-match by email
12. Settings → Hatif → Templates list — create one, see it in Send WA wizard dropdown
13. Pipeline → filter "Negative last sentiment" — verify subset
14. Pipeline → kanban with sentiment dot — visible
15. Replay missed-call webhook → activity scheduled, kanban card highlights
16. Bulk select 5 leads → action "Send Hatif WA Template" → preflight panel + send → 5 message rows + 5 chatter posts
17. Bulk select 3 leads → action "Trigger Hatif IVR" → 3 ivr runs + chatter posts
18. Settings → Hatif → DNC list — add a phone, try sending WA to it → blocked
19. Daily Digest manual-trigger button → email preview rendered
20. Uninstall both modules → DB clean, no residue, no Hatif connection attempted at any point

## P0.5 UAT outcomes

**Pass:** Amr signs off → next session starts P1 backend wiring on top of skeleton.

**Fail (any item):** logged in `STATUS.md`, fixed in skeleton revision, re-UAT, before P1.

## Files delivered

```
htf_call_center/
├── models/                  (15 files, schema only)
├── views/                   (16 view files)
├── static/src/components/   (4 OWL widgets)
├── wizards/                 (5 wizards, mocked)
├── services/
│   └── _mocks/              (8 mock services + factory wiring in htf_config)
├── data/
│   └── demo/                (4 demo XML files)
├── tools/
│   └── replay_webhook.py
└── tests/
    ├── test_views_render.py
    ├── test_components_snapshot.py
    └── test_mocks_isolated.py

numo_crm_htf/
├── models/                  (5 files, schema + extensions)
├── views/                   (3 view files)
├── static/src/components/   (3 OWL widgets)
├── wizards/                 (1 mock bulk wizard)
├── data/
│   └── demo/                (4 demo XML files)
└── tests/
    ├── test_pipeline_filters.py
    └── test_lead_smart_buttons.py
```

## Risks specific to P0.5

| Risk | Mitigation |
|---|---|
| Mock service drift from real API contract | Same fixtures used in P0 unit tests + here; API_CONTRACT.md is single source |
| "Looks done" perception | Settings banner + watermark on chatter posts: `[DEV MOCK]` prefix when in mock mode |
| Demo data leaks to prod | Demo XML loaded only with `--demo`; production install uses `--without-demo` |
| OWL components not future-proof for real data | Components consume model fields, not hardcoded JSON; swapping mock→real is data-only |
| Skipping P0.5 to save time | Insertion is non-negotiable per Amr's request; phase docs + STATUS.md gate enforce |

## Done definition

- All 10 tasks complete + tested + reviewed
- All 20 UAT items signed off by Amr
- `dev_mode_skip_hmac` documented + tested OFF before P1
- Mock import lint rule passing
- STATUS.md updated
- Tag `htf-p0.5-done`
- After sign-off, P1 task list reduces by ~15% (UI exists)

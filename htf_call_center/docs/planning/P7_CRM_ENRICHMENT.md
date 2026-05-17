# Phase P7 — CRM Enrichment (bridge)

**Module:** `numo_crm_htf`
**Effort:** 16–22 dev hrs
**Depends on:** P0–P6 of vendor wrapper, existing `numo_crm`
**Blocks:** P8 partial

## Goal

Make Numo CRM rich with Hatif data. AI summary, sentiment trend, auto-stage progression, classify integration, won/lost hooks, daily digest, bulk actions — without touching the `numo_crm` module's source code.

## Acceptance criteria

- [ ] Bridge module installs cleanly, depends on htf_call_center + numo_crm + crm
- [ ] All bridge changes via inheritance / xpath / signal subscriptions only
- [ ] Pylint custom rule pass (no internal imports of htf_call_center.services.*)
- [ ] CRM lead form shows: AI summary card, sentiment trend mini-chart, channel badge, smart buttons (Calls / WA / IVR)
- [ ] Auto-link inbound calls/WA to most-relevant open lead
- [ ] Auto-stage progression rules (configurable, feature-flagged)
- [ ] Classify wizard (numo_crm) integrates with htf signals
- [ ] Won/lost hooks fire correct WA template
- [ ] Daily digest cron sends per-user email
- [ ] Bulk WA send + bulk IVR trigger from CRM list view
- [ ] CTWA attribution captures inbound WA referrals
- [ ] Filters added to Pipeline analysis (sentiment, channel, last contact)

## Tasks

### T7.1 — Bridge module scaffolding (1h)
- Create `numo_crm_htf/` skeleton
- `__manifest__.py` with version-constrained dependency:
  ```python
  'depends': ['htf_call_center', 'numo_crm', 'crm'],
  # version constraint enforced via runtime check in __init__.py:
  # raises if htf_call_center version < 19.0.1.0.0 or > 19.0.2.x.y
  ```
- `__init__.py` files (vendor version compatibility check on import)
- `security/ir.model.access.csv` (ACLs for new bridge models — no new groups, reuses htf_call_center groups)

### T7.2 — Event handler (subscribes to vendor signals) (2h)
- `models/htf_event_handler.py` (`_name='numo_crm_htf.event_handler'`, AbstractModel)
- `_register_hook()` subscribes to all relevant signals:
  - `htf.call.received` → handle_call_received
  - `htf.call.missed` → handle_call_missed
  - `htf.wa.inbound` → handle_wa_inbound
  - `htf.wa.outbound` → handle_wa_outbound
  - `htf.wa.status` → handle_wa_status (for delivery icons)
  - `htf.ivr.result` → handle_ivr_result
  - `htf.contact.synced` → handle_contact_synced
- Each handler gets full payload, decides bridge action
- Tests per handler

### T7.3 — Most-relevant lead resolver (1h)
- `services/lead_resolver.py` (note: bridge has services too, but they call vendor services via env, never import internals)
- `resolve_lead_for_partner(partner, channel=None, handler_user=None) -> crm.lead | None`
- Logic:
  - `crm.lead` records where partner_id=partner AND active=True AND stage_id.is_won=False AND active=True
  - Tiebreaker: assigned-to-handler-user, then most-recent activity, then most-recent create_date
  - If empty → return None
- Tests: ties, no match, multiple matches, won/lost excluded

### T7.4 — Lead auto-link from call (1h)
- In `handle_call_received` and `handle_call_missed`:
  - Resolve best lead via T7.3
  - Set `htf.call.lead_id = lead.id`
  - Update lead denorm fields (last_call_id, last_sentiment, total_talk_seconds, sentiment_history_json, pinned_summary)
  - Smart-button counter increments
- Tests: each call status → correct lead update

### T7.5 — Lead auto-link from WA (1h)
- Same as T7.4 but for `handle_wa_inbound` and `handle_wa_outbound`
- Updates last_message_id, message_count
- Tests

### T7.6 — Missed-call activity creator (0.5h)
- In `handle_call_missed`:
  - Create `mail.activity` of activity_type `numo_crm_htf.activity_phone_call`
  - Assigned to lead.user_id (or fallback to channel.team_id default user)
  - Deadline today, summary "Missed call — please call back"
- Activity type added in `data/activity_types.xml`
- Tests: activity created with correct fields, no duplicate when same call retried

### T7.7 — AI summary card widget (1.5h)
- `static/src/components/AiSummaryCard/`
- Shows `lead.x_htf_pinned_summary` if present
- Click → expand to full transcript + audio player
- Apply via xpath in `views/crm_lead_views.xml`
- Tests: widget renders + handles empty state

### T7.8 — Sentiment trend mini-chart (1.5h)
- `static/src/components/SentimentTrend/`
- Reads `lead.x_htf_sentiment_history_json` (last 10)
- Sparkline (Chart.js) with colors per sentiment value
- Tooltip shows date + interaction
- Apply via xpath
- Tests: chart renders, empty state, data updates

### T7.9 — Channel badge widget (0.5h)
- `static/src/components/ChannelBadge/`
- Shows last channel icon (📞 / 💬) + last contact time
- Apply on lead card kanban + form

### T7.10 — Smart buttons (0.5h)
- crm.lead form: Calls (x_htf_call_count), WhatsApp (x_htf_message_count), IVR Runs (x_htf_ivr_run_count)
- Each opens filtered list

### T7.11 — Auto-stage progression (2h)
- `data/automation_rules.xml`:
  - Rule "First positive call → Qualified": triggered on `htf.call` create where sentiment=positive AND duration>=60s AND lead.stage_id.sequence < Qualified — moves stage
  - Rule "Negative + 3 missed calls → Suggest lost": triggered on missed call count, surfaces a server action button
- Feature flag: `numo_crm_htf.enable_auto_stage` (default True)
- Tests: each rule fires with right pre-conditions, opt-out feature flag respected

### T7.12 — Classify wizard integration (1.5h)
- Subscribe to numo_crm classify wizard's existing extension hook (or call its method via env)
- After classify decision (e.g. "Hot Lead"), bridge fires WA template `welcome-academy` via `whatsapp.send_template`
- Configurable mapping: classify_outcome → template name (data XML + admin override)
- Tests: each outcome → correct template

### T7.13 — Won/Lost hooks (1.5h)
- Override `crm.lead.action_set_won_rainbowman` (Odoo standard) via `_inherit`:
  - On Won → fire WA template `thanks-onboarding` if lead has WA channel + 24h-allowed-template
  - Cancel any pending IVRs (`htf.ivr.run` where lead_id=this AND status=initiated)
- On Lost (write `stage_id.is_won=False AND active=False`):
  - Add to DNC if user-confirmed (toast suggestion, opt-in)
  - Cancel pending IVRs
- Tests: each path

### T7.14 — Bulk WA send wizard (2h)
- `wizards/bulk_send_wa.py` (extends or wraps htf_call_center's send_whatsapp wizard)
- Recipients: from selected records (via context active_ids)
- Per-recipient param mapping: dropdown variables → field paths (`partner.name`, `lead.x_program_interest`, etc.)
- Pre-flight panel:
  - DNC excluded count
  - 24h-window-violation count → forces template
  - Total est cost
- Submit → loops, calls `whatsapp.send_template` per recipient, persists results
- Progress bar (server-streamed via `bus.bus`)
- Tests: per-recipient looping, DNC excludes, partial failure handling

### T7.15 — Bulk IVR trigger (0.5h)
- Reuses `wizards/trigger_ivr.py` from P5 vendor module
- Bridge adds CRM-specific config_keys to dropdown

### T7.16 — Daily digest cron + email (2h)
- `data/mail_template.xml`: digest template
- Cron `numo_crm_htf.cron.daily_digest` runs each morning per user:
  - Yesterday's missed calls assigned to user
  - Unread WA replies on user's leads
  - Leads silent > 7d with positive last sentiment (re-engagement nudges)
- Sends mail via `mail.template.send_mail()`
- Heartbeat `numo_crm_htf.daily_digest_log` row per send
- Feature flag: `numo_crm_htf.enable_daily_digest` (default True)
- Tests: each section, no empty-content sends

### T7.17 — Pipeline analysis filters (1h)
- xpath addition to `crm.crm.report.view.search`
- Filters: avg sentiment (positive/neutral/negative), last channel (call/WA), last contact age (<24h/<7d), inside 24h window
- Group-bys: sentiment, last channel
- Tests: search domain returns expected sets

### T7.18 — CTWA attribution (1h)
- In `handle_wa_inbound`:
  - If payload includes `referral` (Click-to-WhatsApp Ads metadata) → set `lead.x_htf_lead_source_ctwa=True`, `x_htf_ctwa_metadata_json=referral`
  - Update `lead.source_id` to "Hatif CTWA" (auto-create if missing)
- Tests: with referral, without referral

### T7.19 — Lead form template wiring (1h)
- `views/crm_lead_views.xml` xpath additions:
  - AI summary card under header
  - Sentiment trend mini-chart in stats area
  - Channel badge near phone field
  - Smart buttons in header bar
  - Pinned summary tab in notebook
- Validate against existing numo_crm form layout

### T7.20 — Won-back campaigns (deferred to P8 by default)

## P7 UAT checklist

1. [ ] Inbound call → lead chatter posts AI summary + sentiment + audio
2. [ ] Missed call → activity scheduled
3. [ ] Lead form shows AI summary card + sentiment trend
4. [ ] First positive call → stage advances to Qualified
5. [ ] Classify wizard → outcome → WA template fires
6. [ ] Mark Won → thank-you template sent + IVRs cancelled
7. [ ] Mark Lost → DNC suggestion toast
8. [ ] Bulk send WA to 10 leads → 9 sent (1 DNC), report visible
9. [ ] Bulk trigger IVR appointment-confirm → calls placed, results tabulated
10. [ ] Daily digest email lands at 8am with correct sections
11. [ ] CTWA-sourced inbound WA → lead has source=Hatif CTWA + referral metadata
12. [ ] Pipeline filter "Negative last sentiment" returns matching leads
13. [ ] All tests pass, no edits to numo_crm source

## Files delivered

```
numo_crm_htf/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── crm_lead.py
│   ├── res_partner.py
│   └── htf_event_handler.py
├── services/
│   └── lead_resolver.py
├── wizards/
│   ├── bulk_send_wa.py
│   └── classify_with_htf.py
├── data/
│   ├── activity_types.xml
│   ├── automation_rules.xml
│   ├── ivr_action_config.xml
│   ├── mail_template.xml
│   └── ir_cron.xml             (daily digest)
├── views/
│   ├── crm_lead_views.xml
│   ├── crm_pipeline_views.xml
│   └── res_partner_views.xml
├── static/src/
│   └── components/
│       ├── AiSummaryCard/
│       ├── SentimentTrend/
│       └── ChannelBadge/
├── security/
│   └── ir.model.access.csv
└── tests/
    ├── test_event_handlers.py
    ├── test_lead_resolver.py
    ├── test_auto_stage.py
    ├── test_classify_integration.py
    ├── test_won_lost_hooks.py
    ├── test_bulk_send_wa.py
    ├── test_daily_digest.py
    ├── test_ctwa_attribution.py
    └── test_no_internal_imports.py     (lints bridge)
```

## Risks specific to P7

- Coupling drift — bridge accidentally imports internals → mitigated by pylint rule (CI fails)
- Auto-stage misfires on legacy leads → feature flag + opt-in per pipeline
- Daily digest spam → only sends if any section has content
- Classify integration version drift if numo_crm wizard changes → integration tests
- Bulk send blocked by Hatif rate limit → throttle + retry logic

## Done definition

- All tasks complete + tested + reviewed
- numo_crm source untouched (CI verifies)
- UAT signed off
- STATUS.md updated
- Tag `htf-p7-done`

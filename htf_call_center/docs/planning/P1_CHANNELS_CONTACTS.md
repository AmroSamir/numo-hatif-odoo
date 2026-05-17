# Phase P1 — Channels, Contacts, Users

**Module:** `htf_call_center`
**Effort:** 8–12 dev hrs
**Depends on:** P0
**Blocks:** P2, P3, P4

## Goal

Make Odoo aware of: which Hatif channels exist, which res.partners map to which Hatif contacts, and which res.users map to which Hatif workspace users.

## Blocked-by

- Q-05 (single workspace vs per-brand) — drives T1.1c team binding strategy
- Q-13 (templates per-brand or shared) — informs T1.7 contact properties scope

## Mitigates

- R-07 (user mapping drift) → T1.3 daily sync cron
- R-13 (multi-brand channels) → T1.1b binding wizard

## Acceptance criteria

- [ ] Admin can sync channels from Hatif → list shows in Settings
- [ ] Admin can sync tags
- [ ] Admin can sync workspace users
- [ ] User mapping wizard auto-matches by email + allows manual override
- [ ] res.partner gets `x_htf_contact_id` field
- [ ] res.users gets `x_htf_user_id` field
- [ ] Idempotent re-sync on every endpoint
- [ ] vCard bulk import wizard works
- [ ] phonenumbers lib normalizes Saudi numbers correctly

## Tasks

### T1.1 — `htf.channel` model + sync (2h)
- Model per DATA_MODEL.md (multi-team-aware)
- `services/channels.py`:
  - `sync_from_htf()` calls `/v1/channels/service-account`, upserts by `htf_channel_id`
  - Marks remote-deleted channels as `state=archived` (no hard delete)
  - Preserves `team_id`, `display_name`, `default_for_outbound_*`, `notes`, `color`, `sequence` across re-sync
  - Returns recordset
- Cron: nightly sync
- View: `htf_channel_views.xml`:
  - Editable list view (inline edit team_id, display_name, defaults, brand, color)
  - Drag-handle for sequence
  - Search filters by team / brand / channel_type / state
  - Form with all fields + reverse view of recent calls/messages
- Menu: Settings → Hatif → Channels
- Tests: idempotent re-sync preserves admin overrides; archive on remote-delete; default-flag uniqueness per team

### T1.1b — Channel-to-Team binding wizard (1h)
- Wizard `wizards/bind_channels.py`:
  - Single screen: table of all active channels × all crm.teams
  - Editable: team picker per channel, default-WA + default-call radio per team
  - Validation: each channel must have team; each team must have exactly one default-WA + default-call (if it has any WA/call channel)
  - Save → batch update
- Quick-access button on Settings → Hatif → Channels → "Bind Channels to Teams"
- Tests: validation, batch save, idempotent re-open

### T1.1c — Team extension fields + computed defaults (1h)
- crm.team `_inherit` adds `x_htf_channel_ids` (One2many), computed default_outbound_*_channel_id, `x_htf_routing_strategy`
- View extension on crm.team form: new "Hatif Channels" tab listing channels + routing strategy selector
- Tests: computed fields, multi-channel-per-team, no-channel team gracefully (no Hatif features)

### T1.2 — `htf.tag` model + sync (1h)
- Model per DATA_MODEL.md
- `services/tags.py`:
  - `sync_from_htf()` from `/v1/tags/service-account`
  - `create()`, `update()`, `delete()` mirror to Hatif
- View: list + form (admin), color picker
- Menu: Settings → Hatif → Tags

### T1.3 — `htf.user.link` model + sync + wizard (2h)
- Model per DATA_MODEL.md
- `services/workspace.py`:
  - `list_users()` from `/v1/workspaces/users`
  - `sync_users()` upserts `htf.user.link` rows
  - `match_by_email()` returns suggestions
- Wizard: `wizards/map_users.py`:
  - Pull live users via `sync_users()`
  - Render table: email | display_name | matched_res_user (auto) | dropdown override
  - Save button writes `res.users.x_htf_user_id`
  - Re-running idempotent
- res.users extension: add `x_htf_user_id`, `x_htf_user_email`, `x_htf_role`
- View: settings → Hatif → User Mapping (admin only)
- Tests: auto-match, manual override, idempotent, missing email handling, AI agent flagged separately

### T1.4 — `htf.contact.link` model + service (2h)
- Model per DATA_MODEL.md
- `services/contacts.py`:
  - `upsert_from_partner(partner)` creates Hatif contact via `POST /v1/contacts` if missing, else `PUT /v1/contacts/{id}`
  - `sync_from_htf(htf_contact_id)` pulls Hatif contact, upserts partner
  - `delete(partner)` removes link + Hatif contact
  - `search_by_property(property_def_id, operator, value)` POST `/v1/contacts/search` with body
  - `set_property(partner, property_id, value)` PUT `/v1/contacts/{id}/properties/{property_id}`
  - `unset_property(partner, property_id)` DELETE same
- res.partner extension: `x_htf_contact_id`, `x_htf_synced_at`, `x_htf_last_inbound_at`, `x_htf_24h_window_open` computed
- E.164 normalization helper (`utils/phone.py` using `phonenumbers`)
- Tests: round-trip, dedupe by phone, partial property updates, normalization edge cases (Saudi mobile prefixes 050/052/053/054/055/056/058/059)

### T1.5 — Cron: contacts poll (1h)
- Cron `htf.cron.poll_contacts` (every 30 min, configurable)
- Calls `/v1/contacts?SkipCount=0&MaxResultCount=100` paginated
- Upserts via `contacts.sync_from_htf()` for any with `lastModificationTime` newer than `htf.config.last_contacts_poll_at`
- Tests: pagination, incremental update, no-op when nothing changed

### T1.6 — vCard bulk import wizard (1.5h)
- Wizard `wizards/import_vcards.py`:
  - Upload CSV or paste vCards
  - Preview list of parsed records
  - Submit → POST `/v1/contacts/import/vcards`
  - Display per-row results (created / updated / errors)
- View XML
- Menu under Settings → Hatif → Import vCards (admin)
- Tests: parsing variants (Arabic names, BIZ-NAME field, phones with/without country code)

### T1.7 — Contact Properties (custom fields) (1h)
- `services/contact_properties.py`:
  - `list_definitions()` GET `/v1/contact-property-definitions`
  - `create_definition(name, type, options)`
  - `update_definition(id, ...)`
  - `delete_definition(id)`
- Admin view: list of definitions + form (Settings → Hatif → Contact Properties)
- res.partner extension: `htf.contact.link.custom_properties_json` snapshot for fast display
- Tests: each CRUD path

### T1.8 — Settings page wiring (0.5h)
- Add navigation: Channels / Tags / User Mapping / Import vCards / Contact Properties
- All under Settings → Hatif (group_admin only)

## P1 UAT checklist

1. [ ] Sync channels — verify all 5+ channels appear in list
2. [ ] Bind each channel to a sales team via wizard — sub-second saves
3. [ ] Re-sync from Hatif → admin's team binding + display_name + defaults preserved
4. [ ] Try setting two default-WA channels for same team → validation blocks save
5. [ ] Open crm.team form → Hatif Channels tab shows correct channels
6. [ ] Switch a channel to a different team via wizard → all bindings update
7. [ ] Sync tags — verify list matches portal
8. [ ] Run user mapping wizard — verify email auto-match correctness
9. [ ] Open existing res.partner with phone — verify `x_htf_contact_id` populates after first sync
10. [ ] Edit a res.partner email/phone — verify it pushes to Hatif
11. [ ] Modify a Hatif contact remotely — verify next poll syncs back
12. [ ] Import vCards: upload sample file, verify per-row outcomes
13. [ ] Add a Contact Property "Test" of type Select — verify it appears in Hatif portal
14. [ ] Set property value for a contact via API — verify both sides see it

## Files delivered

```
htf_call_center/
├── models/
│   ├── htf_channel.py
│   ├── htf_tag.py
│   ├── htf_user_link.py
│   ├── htf_contact_link.py
│   ├── res_partner.py
│   └── res_users.py
├── services/
│   ├── channels.py
│   ├── tags.py
│   ├── workspace.py
│   ├── contacts.py
│   └── contact_properties.py
├── utils/
│   ├── __init__.py
│   └── phone.py
├── models/crm_team.py        (extension)
├── wizards/
│   ├── bind_channels.py
│   ├── map_users.py
│   └── import_vcards.py
├── data/
│   ├── ir_cron.xml         (channels nightly, contacts every 30 min)
│   └── default_config.xml
├── views/
│   ├── htf_channel_views.xml
│   ├── htf_tag_views.xml
│   ├── htf_user_link_views.xml
│   ├── res_partner_views.xml
│   └── menus.xml
└── tests/
    ├── test_channels.py
    ├── test_tags.py
    ├── test_workspace.py
    ├── test_contacts.py
    └── test_phone_utils.py
```

## Done definition

- All tasks done, reviewed, tested
- E.164 fixtures cover Saudi prefixes, leading zero, missing country code, double-zero international
- UAT signed off
- STATUS.md updated
- Tag `htf-p1-done`

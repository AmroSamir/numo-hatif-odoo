# Phase P6 — Conversations Sync

**Module:** `htf_call_center`
**Effort:** 8–10 dev hrs
**Depends on:** P0, P1, P2, P4
**Blocks:** none

## Goal

Mirror Hatif's conversation+timeline view into Odoo so that admins/managers can see the entire stream per channel (across calls + WA + assignments) without leaving Odoo. End users still rely on chatter on their own records — this is the manager view.

## Acceptance criteria

- [ ] Cron polls conversations per active channel every N minutes (configurable, default 15)
- [ ] `htf.conversation` rows persisted with all metadata
- [ ] `htf.conversation.event` rows persisted from timeline
- [ ] Smart button "Conversation" on partner/lead opens snapshot
- [ ] Filters: assignee, tags, contact, phone, date range (UTC+3 → UTC), IsLost
- [ ] List view + kanban view (Open / Closed swimlanes)
- [ ] Assign user XOR AI agent (mutex enforced)
- [ ] Re-poll idempotent

## Tasks

### T6.1 — `htf.conversation` + `htf.conversation.event` models (1.5h)
- Per DATA_MODEL.md
- Resolve foreign keys: partner_id from contactId, lead_id from bridge, channel_id from htf.channel, assignee_user_id from htf.user.link
- Computed fields for display
- Indexes: `htf_conversation_id` UNIQUE, `htf_conversation_event_id` UNIQUE

### T6.2 — `services/conversations.py` (2h)
- Methods per API_CONTRACT.md:
  - `get_or_create(...)` POST `/v2/conversations/.../create`
  - `assign(...)` POST `/v2/conversations/{id}/assign` — enforce user XOR ai mutex client-side too
  - `list_for_channel(channel_id, **filters)` GET — UTC+3 conversion for date filters
  - `get_timeline(conversation, ...)` GET timeline
- Tests: each method, UTC+3 conversion, mutex

### T6.3 — Polling cron (1.5h)
- Cron `htf.cron.poll_conversations` every 15 min:
  - For each active channel (channel_type in [whatsapp, both]):
    - Page through `list_for_channel(channel_id, from_date=last_poll, to_date=now)` — UTC+3 normalized
    - Upsert each conversation row
    - For each conversation, page through `get_timeline(...)` since last event
    - Upsert events
- Update `htf.config.last_conversations_poll_at`
- Tests: pagination, idempotency, per-channel iteration

### T6.4 — Views (1.5h)
- `htf_conversation_views.xml`:
  - List with filters
  - Kanban grouped by Status
  - Form with timeline events expandable
- `htf_conversation_event_views.xml`:
  - List inside conversation form
- Search filters: assignee, tags, contact, phone, date range, IsLost

### T6.5 — Smart button on res.partner + crm.lead (1h)
- "Conversations (count)" → opens filtered list
- Default scope: latest 20 conversations
- View: `res_partner_views.xml`, `crm_lead_views.xml` (lead changes go in P7 bridge though)

### T6.6 — Assign action (0.5h)
- Button on conversation form: "Assign to me" / "Reassign" wizard
- Calls `conversations.assign()`
- Tests: mutex, signal `htf.user.mapping.changed` not fired here

### T6.7 — Manager-only menu (0.5h)
- Settings → Hatif → Conversations (manager + admin groups)
- Hidden from regular agents (record rules already restrict their view)

## P6 UAT checklist

1. [ ] Manager opens Conversations view → sees Open/Closed kanban
2. [ ] Filter to one channel → list narrows
3. [ ] Click a conversation → see full timeline (call rows + WA rows)
4. [ ] Date filter today/yesterday → boundary correctness with UTC+3
5. [ ] Assign conversation to user → Hatif portal reflects assignment
6. [ ] Polling cron runs → new conversations appear without manual sync
7. [ ] Spoofed timeline (DB tampered) corrected by next poll
8. [ ] Agent in regular group doesn't see Conversations menu

## Files delivered

```
htf_call_center/
├── models/
│   ├── htf_conversation.py
│   └── htf_conversation_event.py
├── services/
│   └── conversations.py
├── data/
│   └── ir_cron.xml          (poll_conversations)
├── views/
│   ├── htf_conversation_views.xml
│   ├── htf_conversation_event_views.xml
│   └── menus.xml             (additions)
└── tests/
    ├── test_conversations_service.py
    ├── test_poll_conversations.py
    └── test_assign_conversation.py
```

## Risks specific to P6

- UTC+3 conversion off-by-one on DST → tests cover March/October boundaries
- High-volume channels → pagination + rate limit + incremental polling required
- Conversation reassignment in Hatif portal not picked up until next poll → acceptable, document
- AI agent reassignment overlap with user → mutex enforcement client + server

## Done definition

- All tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p6-done`

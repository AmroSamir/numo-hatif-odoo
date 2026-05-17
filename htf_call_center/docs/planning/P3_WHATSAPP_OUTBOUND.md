# Phase P3 — WhatsApp Outbound

**Module:** `htf_call_center`
**Effort:** 10–14 dev hrs
**Depends on:** P0, P1, P2
**Blocks:** P7 (bridge bulk send)

## Goal

Agents send WhatsApp from inside Odoo: free-form text inside the 24h window, or template messages anytime. Sends originate from chatter composer or a dedicated wizard.

## Acceptance criteria

- [ ] Phone widget on res.partner / crm.lead replaced with HTF widget showing 📞 (deep-link to Hatif app) + 💬 (open WA composer)
- [ ] Chatter composer extended with WA toggle (text mode)
- [ ] Send Template wizard from chatter button + from Action menu on partner/lead
- [ ] DNC pre-check blocks send with clear message
- [ ] 24h-window pre-check blocks free-form text outside window (force template)
- [ ] Template registry CRUD admin UI (since Hatif has no template API)
- [ ] Sent messages persisted as `htf.message` and posted to chatter
- [ ] Optimistic UI: bubble shows immediately, status updates as webhook arrives
- [ ] Errors surfaced as actionable toasts

## Tasks

### T3.1 — Template registry model (1h)
- `htf.message.template` per DATA_MODEL.md
- Admin form: name, language, category, channel_ids, header_type, body_variables_count + labels JSON, buttons_json, sample_payload_json, state
- Validation: variable count matches labels keys; buttons follow SubType+Index rules; sample renders without errors
- Menu: Settings → Hatif → Templates
- Tests: validation rules + import from JSON

### T3.1b — Channel resolver helper (0.5h)
- `services/channel_resolver.py`:
  - `resolve_outbound_wa(*, partner=None, lead=None, sender_user=None) -> htf.channel`
  - Resolution chain (first match wins):
    1. `lead.team_id.x_htf_default_outbound_wa_channel_id` if lead given
    2. `partner.team_id.x_htf_default_outbound_wa_channel_id` if partner has team
    3. `partner.x_htf_default_channel_id` (per-partner override)
    4. `sender_user.sale_team_id.x_htf_default_outbound_wa_channel_id`
    5. workspace-wide fallback (admin sets one in Settings)
    6. raise `HtfChannelNotFoundError` with helpful message
  - Same logic for `resolve_outbound_call` (deep-link target)
- Tests: each step in resolution chain, fallback gracefulness

### T3.2 — `services/whatsapp.py` (outbound) (2h)
- `WhatsAppService(env)`:
  - `send_text(channel_id, to_number, text, *, partner, lead, sender_user)`
    - If `channel_id` is None → call channel_resolver.resolve_outbound_wa(...)
    - Verify resolved channel.team_id matches sender_user (if user has team) → log warning if cross-team send
    - DNC check → raise HtfDncBlockedError
    - 24h window check on partner → raise HtfWindowExpiredError if expired
    - POST `/v1/whatsapp/service-account/sendText` with auth Bearer
    - Persist `htf.message` (state=pending → sent on success)
    - Post chatter (call services.chatter.post_outbound_wa)
    - Fire signal `htf.wa.outbound`
    - Return `htf.message` record
  - `send_template(channel_id, to_number, template_name, language, parameters, *, partner, lead, sender_user)`
    - DNC check
    - No window check (templates always allowed)
    - POST `/v1/whatsapp/.../sendTemplate`
    - Same persistence + chatter + signal flow
  - Helper builders: `build_body_parameter`, `build_header_image`, `build_header_video`, `build_header_document`, `build_header_text`, `build_url_button`, `build_quick_reply_button`
- Tests: each helper + happy path + DNC blocked + window expired + API error → state=failed

### T3.3 — Phone widget OWL component (2.5h)
- `static/src/components/HatifPhoneField/`
- Extends Odoo's standard phone widget
- Renders: `+966… [📞] [💬]`
- 📞 button: opens deep-link `tel:+966...` (or Hatif-specific scheme if Hatif team confirms)
- 💬 button: opens Send WA wizard with phone pre-filled
- Field attribute `widget="htf_phone"` activates it
- Apply on `res.partner.phone`, `res.partner.mobile`, `crm.lead.phone`, `crm.lead.mobile`
- Fallback to native widget if `htf.config` not configured
- Tests: snapshot + interaction

### T3.4 — Chatter composer extension (2.5h)
- `static/src/components/HatifChatterComposer/`
- Extends mail composer to add WA toggle + channel picker
- WA toggle disabled if 24h window expired (with tooltip explaining)
- Send button POSTs to `/web/dataset/call_kw` invoking `htf_call_center.services.whatsapp.send_text` (via wrapping ORM call)
- Optimistic bubble appears immediately with state=pending
- Webhook status update later refreshes status icons
- Tests: OWL snapshot + behavior

### T3.5 — Send Template wizard (2h)
- `wizards/send_whatsapp.py`
- Fields: channel_id (from partner default), template_id (filtered by channel), parameter binding rows (auto-generated from template body_variable_labels), header media upload, button params
- Live preview pane (mock WhatsApp bubble)
- Pre-flight panel: DNC status, 24h window status, est cost
- Submit → call `whatsapp.send_template`
- Tests: param binding logic, preview correctness, DNC block

### T3.6 — Failed-send retry cron (0.5h)
- Cron `htf.cron.retry_failed_messages`: every 5 min for `state=failed_pending`, retry up to 30 min total then mark `failed_final`
- Tests: state transitions + final timeout

### T3.7 — Logging + cost estimation hook (0.5h)
- Hardcoded local cost estimates per category (configurable via `htf.config`):
  - marketing: $0.024
  - utility: $0.0224
  - authentication: $0.0265
  - service: $0
- Stored on `htf.message.meta_cost_estimate`
- Tests: each category

## P3 UAT checklist

1. [ ] Open partner with phone — widget shows 📞 + 💬
2. [ ] Click 📞 — phone app or Hatif app opens with number
3. [ ] Click 💬 — Send WA wizard opens, channel pre-picked, template optional
4. [ ] Send free-form text inside 24h window → bubble appears in chatter, state goes pending → sent → delivered
5. [ ] Send free-form text outside window → blocked with clear error toast
6. [ ] Send template from wizard with body params → bubble has correct text on Hatif portal
7. [ ] Add a number to DNC → try to send → blocked
8. [ ] Send template with image header → image attaches correctly on customer side
9. [ ] Network failure mid-send → state=failed_pending, cron retries, eventually state=sent
10. [ ] Coverage: both Cambridge channel and Numo Academy channel work independently

## Files delivered

```
htf_call_center/
├── models/
│   └── htf_message_template.py
├── services/
│   └── whatsapp.py
├── controllers/
│   (no new — webhook_whatsapp also handles outbound status)
├── wizards/
│   └── send_whatsapp.py
├── static/src/
│   └── components/
│       ├── HatifPhoneField/
│       └── HatifChatterComposer/
├── views/
│   ├── htf_message_template_views.xml
│   ├── send_whatsapp_views.xml
│   └── chatter_composer_assets.xml
└── tests/
    ├── test_whatsapp_send.py
    ├── test_send_wa_wizard.py
    └── test_phone_widget.py
```

## Risks specific to P3

- Phone widget conflict with other modules (asterisk_click2dial, native VoIP) → conditional registration
- OWL composer extension version drift on Odoo upgrades → pin Odoo 19.0
- Template list grows large → search box + pagination
- Cost estimates inaccurate (Meta changes pricing) → externalize to config

## Done definition

- All tasks complete + tested + reviewed
- UAT signed off
- STATUS.md updated
- Tag `htf-p3-done`

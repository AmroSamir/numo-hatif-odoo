# NEXT SESSION — start here

Last updated: **2026-05-20** (end of session) — P7 fully shipped + 25
follow-up polish commits. Hatif Discuss-conversation surface is live
on `erp.amro.pro` with curated Arabic translations and the Hatif logo
branding throughout.

---

## 30-second TL;DR

The Hatif↔Odoo bridge `htf_call_center` is **P0-P7 live** on
`https://erp.amro.pro` (db `numo`). Real-world inbound + outbound
flows are verified across calls + WhatsApp. The Discuss popup is
the Hatif conversation surface, in Arabic UI for Numo agents.

| Phase | Status |
|---|---|
| P0 Foundation | ✅ live |
| P1 Channels + Contacts + Users | ✅ live |
| P2 WhatsApp Inbound | ✅ live |
| P3 WhatsApp Outbound | ✅ live |
| P4 Calls Webhook | ✅ live |
| **P7 Discuss as Hatif conversation surface** | ✅ live, polished, AR-translated |
| ⏳ P7.8 OWL ChatWindow "Call via Hatif" header button | deferred — JS+XML patches still commented out in manifest |
| ★ **P8 Outbound Sales Acceleration** | approved, **NEXT** (still blocked on 4 pre-build questions) |
| ★ P9 Speech Analytics via n8n | approved, after P8 |
| ★ P5 Conversations Sync | approved, lower priority |

GitHub: https://github.com/AmroSamir/numo-hatif-odoo
Latest commit on `main`: `8853031` fix(p7-i18n): use اتصال in call labels…
Module version: `19.0.1.6.0`
Test scoreboard: **300/300** local (e2e 59, p1 72, p2 63, p3 24, p3_ui 17, p4 39, p7 26).

---

## P7 — what shipped + how it ended up

**Mirror surface:** every Hatif customer has one auto-provisioned
`discuss.channel`. Every WA message + every call becomes a `mail.message`
in that channel. Voice recordings render as native Discuss voice notes.
Bottom-right Discuss popup IS the conversation. Top-left rail lists all
Hatif customer channels with the Hatif logo as the channel icon.

**Outbound override:** typing in a Hatif Discuss channel fires
`htf.whatsapp.send_text`. 24h-window closed → bilingual UserError
matching Hatif's portal wording. Voice-recording UI fires duplicate
message_post → 8-second dedup guard prevents 8-WhatsApp-sends bug.

**Branding:**
- Hatif logo on `base.public_partner` (migration 19.0.1.1.0)
- Hatif logo on every `discuss.channel.image_128` for Hatif channels (19.0.1.2.0)
- Hatif logo on every customer `res.partner.image_1920` with a Hatif channel (19.0.1.4.0, only sets when empty so CRM photos preserved)
- Hatif logo as the module icon `static/description/icon.png` (commit 22a8d68)

**Naming:**
- Channel names use partner display_name (no "Hatif Contact 3a210a15…" or 📞 prefix)
- Placeholder partner.name renamed to phone number when available (migration 19.0.1.5.0)
- Partners without a phone show just the contactId-short (no "Hatif Contact " prefix)

**i18n (the right way):**
- All visible strings English source wrapped in `_()`
- `htf_call_center/i18n/ar.po` holds curated Arabic translations
- 35 Python entries + 4 OWL/JS entries
- English Odoo users → English UI
- Arabic Odoo users → Arabic UI
- Lesson learned: each .po entry needs THREE comments — `#. module:`, `#. odoo-python` (or `#. odoo-javascript`), AND a `#: code:addons/...:0` reference. Without all three, Odoo's PoFileReader silently yields 0 rows.

**RTL handling:**
- `/*rtl:ignore*/` annotation on `direction: ltr !important` rules so Odoo's rtlcss bundle compiler doesn't flip them
- `.o-mail-Message-author`, `.o-mail-Message-date`, `.o-mail-ChatWindow-header .text-truncate.fw-bold`, `.o-mail-VoicePlayer .text-muted` all forced LTR even in AR locale → phone numbers + durations render correctly

**Voice player width:**
- Default `.o-mail-AttachmentContainer` is `width: 13em` (208px) — too narrow
- Overridden for `[data-mimetype^="audio/"]` to grow
- Responsive: chat-window popup gets `min-width: 0` so it doesn't overflow

---

## All migrations shipped (idempotent, safe to re-run)

| Version | Migration | What it does |
|---|---|---|
| 19.0.1.1.0 | post-set-public-avatar | Hatif logo on `base.public_partner` |
| 19.0.1.2.0 | post-rebrand-channels | Strip 📞 prefix + set Hatif logo on every Hatif channel |
| 19.0.1.3.0 | post-retranslate-mirror-bubbles | Re-render bubbles using current renderer + reattribute "Public user" duplicates |
| 19.0.1.4.0 | post-brand-customer-partners | Hatif logo on partner.image_1920 + reattribute OdooBot/Public-user mirror msgs |
| 19.0.1.5.0 | post-rename-placeholder-partners | Rename "Hatif Contact X…" placeholder partners to their phone |
| 19.0.1.6.0 | post-relocalize-mirror-bubbles | Re-render every bubble under `lang=ar_001` for Arabic ar.po wording |

---

## Open items / deferred

1. **P7.8 — OWL ChatWindow header patch (deferred)**
   - Files exist but disabled in `__manifest__.py:64-65` (commented out)
   - Goal: hide native voice/video icons for Hatif channels + add a green "Call via Hatif" anchor opening `app.hatif.io/ar/inbox?conversationId=<id>`
   - Previous xpath approach broke the asset bundle. Researcher's notes (in Ruflo) say the right approach is `patch(Thread.prototype, { allowCalls() {...} })` + `registerThreadAction`.
   - When to do: after the user UATs the current state and decides they want the header button.

2. **OWL `_to_store_defaults` field push**
   - `_to_store_defaults` override in `discuss_channel.py:124` pushes `x_htf_partner_id` and `x_htf_last_conversation_id` to the OWL store, gated by `discuss_ui_override` flag
   - Currently unused because the OWL patches are disabled. Will become live when P7.8 ships.

3. **"Hatif Contact dddddddd…" → phone migration ran on `odoo` local DB but not on `numo`** (different data). Will run automatically on the next module upgrade on amro.pro because of the migration system.

4. **Send WhatsApp wizard — `string=""` overrides removed in revert**
   - Wizard view now uses model field default `string` attributes (English)
   - All Arabic translations live in ar.po
   - If anything reads wrong in EN UI, the fix is editing the field's `string=` in the model `wizards/send_whatsapp.py`

---

## 🗒️ Amr's approved queue (priority order, unchanged)

### 1. ★ P8 — Outbound Sales Acceleration (NEXT)

**Still blocked on these 4 pre-build questions:**
- (a) Outcome enum options (Interested / Not interested / Voicemail / Wrong number / Reschedule / ...)
- (b) Next-step options (Schedule callback / Move stage / Won / Lost / ...)
- (c) Wrap-up wizard: mandatory or skippable?
- (d) Daily queue priority rule (default proposal: overdue activity > lead score > days since last touch)

Lives in `numo_crm_htf` bridge module (sibling repo dir, not yet started). ~12-16h.

### 2. ★ P9 — Speech Analytics via n8n
After P8. ~8h.

### 3. ★ P5 — Conversations Sync
After P9. ~6h, insurance.

### 4. Send the Hatif support email
5 min. Draft is ready at:
`htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md`

---

## Re-entry sequence (when you sit down)

1. Read this file first (you're doing it now).
2. Confirm staging is healthy:
   ```bash
   curl -I https://erp.amro.pro/web/login 2>&1 | head -3
   ```
3. Check git status / pull anything new:
   ```bash
   cd ~/numo-hatif-odoo && git status && git pull origin main
   ```
4. Confirm local Docker is running:
   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}" | head -5
   ```
   If not: `docker compose -f /Users/amro/Downloads/Claude/ai-dnd-builder/odoo-local/docker-compose.yml up -d`
5. Run the local suites:
   ```bash
   for s in e2e p1 p2 p3 p3_ui p4 p7; do
     echo -n "$s: ";
     python3 /tmp/htf_${s}_check.py 2>&1 | grep -E "(passed|RESULT)" | tail -1
   done
   ```
   Expect 300/300.
6. Decide: P8 (answer 4 questions) OR P7.8 (re-enable OWL header button) OR something else from the queue.

---

## Deploy commands for amro.pro (reusable)

```bash
ssh root@vmi3095315
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/
git pull origin main

docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml stop web
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml run --rm web \
    odoo -d numo -u htf_call_center --stop-after-init --no-http --log-level=warn 2>&1 | tail -10
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml up -d web
sleep 8
```

### Tools (env var required for amro.pro)

```bash
# Container override needed because amro.pro container is web-erp-amro-pro
export HTF_CONTAINER=web-erp-amro-pro

# UAT-stage bulk-invite agents to existing Hatif channels
python3 htf_call_center/tools/grant_htf_discuss_members.py numo

# Enable / disable P7 feature flags
python3 htf_call_center/tools/enable_p7_discuss.py numo
python3 htf_call_center/tools/disable_p7_discuss.py numo

# Initial-or-additional backfill of htf.* into Discuss channels
python3 htf_call_center/tools/backfill_htf_discuss.py numo

# Last-resort destructive cleanup (DELETE mirror messages + archive channels)
python3 htf_call_center/tools/unbackfill_htf_discuss.py numo --commit
```

---

## Revert toolkit (5 escalation tiers)

| Tier | Action | Time | Reversible? |
|---|---|---|---|
| L1 | Toggle master flag `htf_call_center.discuss_mirror_enabled` → False in Settings | 30s | yes |
| L2 | Toggle a sub-flag (inbound/calls/outbound_route/ui_override) | 30s | yes |
| L3 | `python3 tools/disable_p7_discuss.py numo` — flags off + archive channels | 2m | yes (enable_p7_discuss.py) |
| L4 | `git revert <p7-commit-sha>` + upgrade module | 10m | yes |
| L5 | `python3 tools/unbackfill_htf_discuss.py numo --commit` — destructive | 5m | partial (original chatter rows untouched) |

Full runbook: `htf_call_center/docs/P7_REVERT_RUNBOOK.md`.

---

## Hatif live-UAT findings (still relevant)

(Unchanged from 2026-05-19 — 13 behavioural discrepancies between
apidog spec and Hatif's actual webhook behaviour, all documented in
the previous session's NEXT_SESSION.md history. Key ones:)

- Hatif does NOT sign webhooks — `htf.config.dev_mode_skip_hmac=True` required everywhere
- `status=8` is undocumented (mapped to 'ringing')
- Analytics arrive only for calls ≥30s
- Saudi phone formats vary wildly — `utils.phone.normalize_e164` handles them
- Hatif user emails ≠ Odoo logins; fuzzy Arabic-name matching is the default user mapper
- Composite event-id idempotency essential (Hatif reuses the same ID across the lifecycle)

---

## Where things are in the repo

```
htf_call_center/                       (vendor wrapper, P0-P7 live)
├── __init__.py                        (post_init_hook for avatar)
├── __manifest__.py                    (version 19.0.1.6.0)
├── i18n/
│   └── ar.po                          (35 Python + 4 OWL/JS entries)
├── migrations/                        (6 idempotent post-* migration scripts)
│   ├── 19.0.1.1.0/post-set-public-avatar.py
│   ├── 19.0.1.2.0/post-rebrand-channels.py
│   ├── 19.0.1.3.0/post-retranslate-mirror-bubbles.py
│   ├── 19.0.1.4.0/post-brand-customer-partners.py
│   ├── 19.0.1.5.0/post-rename-placeholder-partners.py
│   └── 19.0.1.6.0/post-relocalize-mirror-bubbles.py
├── models/                            (P0-P7 schema + business logic)
│   ├── discuss_channel.py             (★ P7 mirror entry + outbound override)
│   ├── res_partner.py                 (x_htf_discuss_channel_id back-ref)
│   └── ... 10 other models
├── services/
│   ├── discuss_mirror.py              (★ mirror_inbound_wa / mirror_outbound_wa_from_hatif / mirror_call)
│   ├── whatsapp_inbound.py            (calls discuss_mirror after each WA write)
│   ├── calls.py                       (calls discuss_mirror after each call write)
│   └── ... 8 other services
├── data/
│   └── htf_discuss_mirror.xml         (mt_htf_mirror subtype)
├── static/src/
│   ├── img/hatif-logo.png             (98 KB Hatif brand mark)
│   ├── description/icon.png           (same Hatif logo for Apps grid)
│   ├── views/fields/phone/            (htf_phone widget — Call + WhatsApp buttons)
│   └── discuss/
│       ├── htf_voice_player.scss      (voice player width + LTR + RTL flipper bypass)
│       ├── thread_model_patch.js      (DISABLED in manifest — P7.8)
│       └── chat_window_patch.xml      (DISABLED in manifest — P7.8)
├── tools/
│   ├── htf_e2e_check.py + htf_p1_check.py + ... + htf_p7_check.py (300 asserts)
│   ├── backfill_htf_discuss.py
│   ├── disable_p7_discuss.py / enable_p7_discuss.py
│   ├── unbackfill_htf_discuss.py
│   ├── grant_htf_discuss_members.py
│   └── replay_webhook.py / signal_smoke.py
└── docs/
    ├── P7_REVERT_RUNBOOK.md           (5-tier rollback procedure)
    ├── HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md  (send-ready)
    ├── hatif_apidog_export.json
    └── Hatif api.md

numo_crm_htf/                          (bridge — NOT YET CODED, P8 lives here)
└── (empty — P8 will populate)
```

---

Welcome back. Don't skip THE DRILL (`/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md`).
Answer the 4 P8 questions OR pick a different approved item and start.

— end of NEXT_SESSION.md (clean handoff 2026-05-20)

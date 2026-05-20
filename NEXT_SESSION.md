# NEXT SESSION — start here

Last updated: **2026-05-20** (end of session)

Massive day. The Hatif↔Odoo bridge `htf_call_center` advanced from
**19.0.1.6.0 → 19.0.1.26.0** with 20+ shipped commits covering i18n,
template registry, partner dedup, channel privacy, and dozens of
quality-of-life fixes. Every change deployed to `erp.amro.pro` (db
`numo`). All 7 regression suites green at session close: **300/300**.

GitHub: https://github.com/AmroSamir/numo-hatif-odoo
Latest commit on `main`: `25440cc fix(htf-discuss): restrict channel membership to authorised agents only`
Module version: `19.0.1.26.0`
Test scoreboard: **300/300** local (e2e 59, p1 72, p2 63, p3 24, p3_ui 17, p4 39, p7 26).

---

## 30-second TL;DR

P0-P7 are LIVE on `erp.amro.pro`. Today's session focused on UAT
polish, security hardening, and shipping the WhatsApp Templates
registry that unblocks template sends. End-to-end verified:
- Customer received a real WhatsApp template send (`welcom_message`)
  at 12:09 PM today.
- Per-customer agent privacy enforced (each Hatif channel now shows
  only customer + admins + assigned salesperson; the InPrivate cross-agent
  visibility test confirms unauthorised agents are out).
- Free-form text gated correctly by Meta's 24h window (live check
  against Hatif timeline API on every wizard open).

---

## What shipped today (20 commits, v19.0.1.7.0 → v19.0.1.26.0)

### i18n (the actual fix that worked this time)
- **v19.0.1.7.0** (`29fe7ae`) — Send WhatsApp wizard finally translates
  to Arabic byte-for-byte. Root cause was wrong PO reference TYPES:
  `code:addons/...:0` only feeds the Python `_()` cache, not view
  arch / fields / selection labels. Rewrote `ar.po` with proper
  `model_terms:ir.ui.view,arch_db:<view_xmlid>`,
  `model:ir.model.fields,field_description:<module>.field_<model>__<field>`,
  and `model:ir.model.fields.selection,name:...` references. Plus
  fixed `discuss_mirror.py` renderer (use `record.env._(...)` not
  bare `_()` from free functions).
- **v19.0.1.8.0** (`bd7964c`) — Teal `<i class="fa fa-phone"
  style="color:#02c7b5"></i>` replacing the 📞 emoji in bubbles.
  Unified "Missed call" wording to "مكالمة واردة (لم يتم الرد)".

### OWL ChatWindow header (P7.8 SHIPPED)
- **v19.0.1.9.0** (`de86a12`) — Hatif teal "Call via Hatif" header
  action. Uses `patch(Thread.prototype, {allowCalls, hatifCallHref})`
  + `registerThreadAction("hatif-call", {...})` — JS-only, no xpath.
  Migration auto-flips `discuss_ui_override` ON.
- **v19.0.1.10.0** (`e795679`) — Paint header icon teal via
  `btnClass` + scss class (not `btnAttrs` which the upstream
  template silently drops).

### Phone widget Call button (lead-form parity with Discuss header)
- **v19.0.1.11.0** (`99813c3`) — `tel:` → `app.hatif.io/ar/inbox?conversationId=...`
- **v19.0.1.12.0** (`0612a2a`) — Restored short "Call" label after
  "Call via Hatif" wrapped awkwardly in RTL; added
  `related='partner_id.x_htf_last_conversation_id'` on `crm.lead`
  for lead-form deep-linking.
- **v19.0.1.13.0** (`5b06c7b`) — Phone fallback when no
  conversation_id yet: `app.hatif.io/ar/inbox?phone=<E.164>`.

### Conversation ID backfill from Hatif API
- **v19.0.1.14.0** (`c379858`) — Migration walks partners with
  empty `x_htf_last_conversation_id` and queries
  `GET /v2/conversations/service-account/channels/{channelId}?PhoneNumber=…`
  to find the latest conversation. Idempotent. Rate-limited.
  Bounded by `HTF_BACKFILL_LIMIT` env for staged rollouts.

### Map Users wizard — channel multi-select per agent
- **v19.0.1.15.0** (`57d2b63`) — `htf.map.users.wizard.line` gets a
  `channel_ids` Many2many; pre-filled from `htf.channel.user_ids`;
  `action_apply` syncs add/remove diff so admins can set channel
  membership for every mapped agent in one screen.

### Hatif error visibility (broke open the 400 debugging)
- **v19.0.1.16.0** (`87d6763`) — Outbound failures now store Hatif's
  response body in `htf.message.error_reason` + `raw_payload._error`
  (was previously just `str(exc)` which dropped the body). Both first
  attempt AND cron retry path. Two helpers: `_format_error_reason`
  (one-line for the column) and `_serialise_api_error` (JSON-safe for
  the audit trail).

### Approved WhatsApp Templates registry (new model)
- **v19.0.1.17.0** (`2ca3c21`) — New `htf.template` model + menu
  "Hatif → WhatsApp Templates". Fields: name, channel_id, language,
  category, status (Approved/Pending/...), body_preview,
  parameter_count, parameter_hint. Unique(name, channel_id,
  language). Wizard's new `template_id` Many2one dropdown filters
  to approved templates on the wizard's channel OR on a channel the
  current user has access to. Onchange auto-fills template_name /
  language / category / channel_id.

### Wizard channel-field UX (single field, readonly)
- **v19.0.1.18.0** (`5a9aa2f`) — Hide resolved-channel display when
  channel_id is set (no more side-by-side duplicate field).
- **v19.0.1.19.0** (`fc1e8ed`) — Pre-resolve channel in `default_get`
  so wizard always opens with a value populated; drop the
  resolved-display field from the view entirely.
- **v19.0.1.20.0** (`09ef90d`) — Channel field is now `readonly="1"
  force_save="1"`. Source of truth is the resolver — agents can't
  override.

### Pre-send validation (catch Meta #132000 locally)
- **v19.0.1.21.0** (`b832cc6`) — Stop auto-filling `template_body_params`
  from `parameter_hint` (the hint is example data, not real values).
  New `_validate_template_param_count`: refuse to send when the
  Body Variables pipe-split count doesn't match
  `template_id.parameter_count`. Wizard now catches the #132000
  mismatch BEFORE hitting Hatif.

### Live 24h-window check
- **v19.0.1.22.0** (`d2567ca`) — `default_get` calls
  `services/conversations.refresh_window_from_hatif(env, partner)`
  which queries
  `GET /v2/conversations/service-account/{conversationId}/timeline`,
  finds the most recent `Direction == 1` (inbound) event, compares
  to `now() - 24h`, writes `x_htf_24h_window_open` +
  `x_htf_last_inbound_at` on the partner. Best-effort: Hatif outages
  fall back to cached flag. Wizard becomes authoritative on window
  state regardless of webhook reliability.

### Outbound bubble author attribution
- **v19.0.1.23.0** (`983f97b`) — `_resolve_outbound_author` no longer
  falls back to the customer's partner when sender_user is unknown.
  New chain: sender's partner → env.user.partner_id → OdooBot.
  Customer partner is intentionally skipped. PLUS dedup improvement
  in `_process_outbound_status`: webhook now also matches by
  `conversation_event_id` (not just `htf_message_id`), so the
  wizard's pre-existing row gets UPDATED instead of duplicated.

### Partner dedup (forward) + merge tool (backfill)
- **v19.0.1.24.0** (`6a6293b`) — `_resolve_partner` in
  `whatsapp_inbound.py` now calls Hatif `GET /v1/contacts/{id}`
  before creating a placeholder; if the contact's phone matches an
  existing res.partner, reuses that partner and creates the
  `htf.contact.link`. No more duplicate partners spawning on first
  webhook. **Plus `tools/merge_duplicate_partners.{py,sh}`** —
  reparents htf.message / htf.call / htf.contact.link / crm.lead /
  x_htf_* fields onto a chosen primary, archives duplicates. Two
  safety guards: (1) refuses to merge two non-placeholder records
  (probably distinct people sharing a phone); (2) skips partners
  backing active `res.users`.

### Duplicate-send fix
- **v19.0.1.25.0** (`a3981ae`) — `http_client.post(retry=False)`
  parameter. `services/whatsapp._send` passes `retry=False` because
  WhatsApp send is NOT idempotent (no Idempotency-Key header in
  Hatif's API). Stops the "single Send → 3 copies on WhatsApp"
  bug caused by ReadTimeout retries. Belt-and-suspenders: dedup
  window in `discuss_channel.py` widened 8s → 30s.

### Per-customer agent routing (privacy)
- **v19.0.1.26.0** (`25440cc`) — Hatif Discuss channels now restrict
  membership to exactly:
    1. The customer's partner
    2. Every user in `htf_call_center.group_admin`
    3. Every user who is the salesperson on a `crm.lead` linked to
       the customer
  `_ensure_htf_discuss_channel` seeds new channels with this set
  (no more wide-open visibility). `crm.lead.write()` hook resyncs
  membership when `user_id` / `partner_id` change (re-assignment
  adds the new agent, drops the old). **Plus
  `tools/prune_htf_discuss_members.{py,sh}`** — one-shot cleanup
  for the UAT-era bulk-invite. **Run this on prod after deploy** —
  dry-run preview is already verified to remove 59 unauthorised
  members from each of the 6 existing Hatif channels.

---

## Other repo edits this session

- **`numo_custom_odoo`** repo (`AmroSamir/numo_custom_odoo`):
  added `author = 'Amr Afifi, Numo Group'` + `website = 'https://numo.sa'`
  to the manifest (commit `e455f6d`) to silence the "Missing author key"
  warning in the container logs.
- **`numo_crm`** manifest at
  `/Users/amro/Downloads/Claude/Odoo Implementation/extra-addons/custom/numo_crm/`
  was edited LOCALLY with the same author/website keys but the
  directory isn't a git repo — the change is on local disk only and
  must be copied to prod via scp or manual edit if you want to
  silence that warning too.

---

## Tools shipped (under `htf_call_center/tools/`)

| Tool | Purpose |
|---|---|
| `deploy.sh` | Paste-safe wrapper for `git pull && stop web && -u htf_call_center && up -d web`. Survives terminal line-wrap. |
| `diagnose_window.{py,sh}` | Walks a partner's 24h-window state — `x_htf_last_inbound_at`, the computed window flag, `x_htf_last_conversation_id`, htf.message counts. Flags webhook/field mismatches automatically. |
| `merge_duplicate_partners.{py,sh}` | Reparents children + archives duplicate partner records sharing a normalized phone. Skips non-placeholder dups (different real people) and partners backing active res.users. |
| `prune_htf_discuss_members.{py,sh}` | Removes unauthorised members from existing Hatif Discuss channels. Idempotent. |
| `grant_htf_discuss_members.py` | (LEGACY — UAT shortcut). DO NOT RE-RUN — it bulk-adds everyone, undoing the privacy fix. Keep around only as documentation of the old workflow. |

All tools honor `HTF_DRY_RUN=1` env-var preview mode. All shell
wrappers also honor `HTF_CONTAINER` / `HTF_DB` for non-amro-pro
deployments.

---

## Live UAT state at session close

| Surface | Status |
|---|---|
| Send WhatsApp wizard (Free-form text) | LIVE, validated by Meta 24h window |
| Send WhatsApp wizard (Template) | LIVE, dropdown from `htf.template` |
| Discuss "Call via Hatif" header button | LIVE on Hatif-linked channels |
| Phone widget on partner/lead form | LIVE — opens Hatif portal not `tel:` |
| Discuss channel privacy | **NEEDS PRUNE RUN** — see below |
| Outbound bubble author | Correctly NOT the customer |
| Inbound webhook → partner | Phone-matched, no more duplicates |
| Live 24h-window check | LIVE on every wizard open |
| Hatif error surfacing | Meta response body now in `error_reason` |
| Approved templates registry | LIVE — `welcom_message` confirmed sent |

**ONE STEP STILL PENDING ON PROD:**

```
bash /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/htf_call_center/tools/prune_htf_discuss_members.sh
```

Dry-run already verified on prod (proposed: keep 2 / remove 59 per
channel × 6 channels = 354 unauthorised member removals). User just
needs to drop `HTF_DRY_RUN=1` and run for real.

---

## Re-entry sequence (next session)

1. Read this file first (you're doing it now).
2. Confirm staging is healthy:
   ```bash
   curl -I https://erp.amro.pro/web/login 2>&1 | head -3
   ```
3. Check git status / pull anything new:
   ```bash
   cd ~/numo-hatif-odoo && git status && git pull origin main
   ```
4. Run the 7 local suites:
   ```bash
   for s in e2e p1 p2 p3 p3_ui p4 p7; do
     echo -n "$s: ";
     python3 /tmp/htf_${s}_check.py 2>&1 | grep -E "passed|RESULT" | tail -1
   done
   ```
   Expect 300/300.
5. **First action**: verify the prune ran on prod (Step 5 above) by
   checking an InPrivate browser window. If the other sales agent
   can still see a Hatif channel, the prune wasn't executed — run it.

---

## Approved queue (priority order)

### 1. ★ P8 — Outbound Sales Acceleration (NEXT)

**STILL blocked on these 4 pre-build questions** (same as previous session):

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

## Deploy on amro.pro (reusable)

Two short paste-safe commands:

```bash
ssh root@vmi3095315
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/
git pull origin main && bash htf_call_center/tools/deploy.sh
```

That's it. The `deploy.sh` wrapper handles `cd /opt/odoo-erp-amro-pro`,
`docker compose stop web`, `docker compose run --rm web odoo -u
htf_call_center --stop-after-init`, and `docker compose up -d web`.
Prints stage banners.

After a deploy that fires the channel-membership work, also run:
```bash
bash htf_call_center/tools/prune_htf_discuss_members.sh
```
(idempotent — safe to run after every deploy if you want).

---

## Lessons learned (sticky for next session)

### i18n PO references in Odoo 19 — three reference types, not one

For text in `<form string="...">`, `<group string="...">`,
`placeholder="..."` → `#: model_terms:ir.ui.view,arch_db:<view_xmlid>`.

For auto-derived field labels (Partner, To Number, etc.) →
`#: model:ir.model.fields,field_description:<module>.field_<model>__<field>`.

For Selection option labels → `#: model:ir.model.fields.selection,name:<module>.selection__<model>__<field>__<value>`.

For Python `_()` calls inside .py code → `#. odoo-python` +
`#: code:addons/<module>/path.py:0`.

Each msgid is unique per PO file but can have multiple `#:`
references when the same source string appears in multiple surfaces.

### Free-function `_()` doesn't find env language

`from odoo import _; _('Foo')` reads language from the caller's
`self.env.context['lang']` via stack introspection. If the function
is a module-level free function (no `self`), it can't find a
recordset to introspect → falls back to source string. **Fix**:
inside free functions called with recordset args, use
`record.env._('Foo')` instead. Better yet, wrap the function in a
method or pass `env` explicitly.

### Odoo 19 renames to remember

- `res.groups.users` → `user_ids`
- `res.users.groups_id` → `group_ids`
- `res.partner.mobile` — **REMOVED** entirely
- `res.groups.category_id` / `comment` — removed
- `ir.cron.numbercall` / `nextcall` — removed
- `_sql_constraints` → `models.Constraint(...)`
- `<app data-key="...">` (Odoo 17) → `<app name="...">` (Odoo 19)
- `discuss.channel.create` auto-adds the creating user as a member —
  must skip already-present partner_ids when adding allowed members
  to avoid `(channel_id, partner_id)` unique-constraint violations.

### HTTP retries on non-idempotent POSTs cause duplicate sends

`http_client` retries POSTs by default. WhatsApp `sendText` /
`sendTemplate` are NOT idempotent (no Idempotency-Key header in
Hatif's API). When Hatif takes >30s to respond, a ReadTimeout
triggers an http_client retry → the customer receives the message
multiple times. **Fix**: pass `retry=False` for all non-idempotent
POSTs. The auth-401 → token-refresh → replay path is still safe and
unchanged.

### Outbound author resolution must skip the customer

When an outbound webhook arrives and `senderUserId` doesn't map to
an Odoo user (typical for templates), the old fallback was the
customer's partner — visually identical to inbound bubbles in
Discuss. Skip the customer; fall back to env.user.partner_id or
OdooBot. The customer's avatar should never appear as the author of
an outbound message.

### Partner deduplication needs phone-based forward lookup AND a backfill

The Hatif webhook payload only carries `contactId`, not phone. On
the very first webhook for a customer who already has a CRM-side
partner, the resolver would create a duplicate placeholder. Forward
fix: call `GET /v1/contacts/{id}` to fetch the phone, then look up
existing partner by phone before creating placeholder. Backfill:
walk all partners grouped by normalized phone, merge dups onto the
record with a readable name.

### Channel membership = visibility ACL in Odoo Discuss

`discuss.channel.channel_member_ids` is what controls who sees the
channel. No need for record rules. The pragmatic privacy model for
customer-conversation channels: customer + admins + assigned
salesperson(s) — drive the set from `htf.config.group_admin` +
`crm.lead.user_id`. Hook `crm.lead.write` so re-assignments
auto-sync.

---

Welcome back. Don't skip THE DRILL (`/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md`).

— end of NEXT_SESSION.md (clean handoff 2026-05-20, v19.0.1.26.0)
